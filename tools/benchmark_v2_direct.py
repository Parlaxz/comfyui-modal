from __future__ import annotations

import time

# ── Host boot origin (V2 host submission timeline breakdown) ─────────────
# The FIRST line executed after the stdlib ``time`` import — before the heavy
# import block below — so ``command_start → python_first_line`` measures the
# interpreter boot plus every startup import that precedes this line.
# Benchmark-only instrumentation.
_PYTHON_FIRST_LINE_NS: int = time.time_ns()
# Mono counterpart for same-process deltas.
_PYTHON_FIRST_LINE_MONO_NS: int = time.monotonic_ns()

import argparse
import asyncio
import concurrent.futures
import copy
import json
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from collections.abc import Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Parent-ComfyUI root the plan builder needs: ``build_execution_plan`` lazily
# imports ``execution`` (validation proof) and ``nodes`` (registry fingerprint)
# from the parent ComfyUI tree, which is NOT on this harness's sys.path.  Add
# it when available so the plan carries the same proof payload and registry
# surface the production v2 dispatch builds with.  Env override wins; the
# fallback derives from the repo layout (repo_root.parent.parent).  Fully
# guarded - a wrong/missing root degrades gracefully, never crashes.
_COMFYUI_ROOT_DIR = os.environ.get(
    "COMFYMODAL_V2_COMFYUI_ROOT",
    str(ROOT.parent.parent),
)
try:
    if (
        _COMFYUI_ROOT_DIR
        and os.path.isdir(_COMFYUI_ROOT_DIR)
        and os.path.isfile(os.path.join(_COMFYUI_ROOT_DIR, "execution.py"))
        and _COMFYUI_ROOT_DIR not in sys.path
    ):
        sys.path.insert(0, _COMFYUI_ROOT_DIR)
except Exception:
    pass

from canonical_execution import (
    build_execution_plan,
    execute_plan,
    prompt_sha256,
    resolve_dispatch_workflow_hash,
)
from modal_client import check_active_warmup_profile, set_active_warmup_profile
from comfymodal_runtime.cpu_snapshot_models import diff_unet_runtime_states
from comfymodal_runtime.env import env_flag
from comfymodal_runtime.execution_seed import publish_restore_plan_enabled
from comfymodal_runtime.modal_restore_boundary import (
    extract_restore_begin_from_result,
    parse_modal_restore_begin,
)
from comfymodal_runtime.modal_transport import ModalTransport, HandleCache
from comfymodal_runtime.restore_plan import RemoteRestorePlanPublisher
from comfymodal_runtime.runtime_shape import runtime_shape_config
from comfymodal_runtime.trace import RuntimeTrace, _build_local_submission_breakdown
from production_workflow import normalize_production_options
from tools.v2_waterfall import (
    build_waterfall,
    render_comparison,
    render_waterfall,
    waterfall_to_dict,
)
from tools.variance_report import (
    build_summary,
    build_matrix_summary,
    extract_run_metrics,
    load_runs_from_dir,
    render_variance_report,
    render_matrix_report,
    percentile,
    compute_stats,
    slow_run_rate,
    _num,
)

# Experiment-result persistence is optional: the harness must still run when
# the module cannot be imported (per-run saves are re-imported defensively).
try:
    from comfymodal_runtime.experiment_result_store import (
        build_run_record,
        save_experiment_run,
        write_campaign_manifest,
    )
except Exception as _exp_import_exc:  # noqa: BLE001
    build_run_record = None
    save_experiment_run = None
    write_campaign_manifest = None
    print(
        f"[v2.experiment] experiment_result_store import failed; "
        f"experiment persistence disabled: {_exp_import_exc}",
        flush=True,
    )


WORKFLOW_PATH = ROOT / "latest_benchmark_workflow.json"
WORKSPACES_PATH = ROOT / ".modal_workspaces.json"
APP_NAME = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
CLASS_NAME = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2")
GPU = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")
RUN_COUNT = int(os.environ.get("V2_BENCHMARK_RUNS", "1"))
GAP_SECONDS = float(os.environ.get("V2_BENCHMARK_GAP_SECONDS", "20"))
_ABSENT_STR = "absent"

# ── Experiment-result persistence (V2 A/B campaign) ─────────────────────
# argparse namespace (populated in ``__main__``) and the per-run records
# accumulated across the multi-run loop.  Both are additive: the harness runs
# unchanged when the campaign flags/records are unused.
_EXPERIMENT_ARGS: Any | None = None
_EXPERIMENT_RECORDS: list[dict[str, Any]] = []

# ── Experiment arm → request-origin env translation (V2 A/B campaign) ──
# Request-level experiment arms are applied PER-REQUEST by translating
# --experiment/--arm into the allowlisted request-origin env keys the
# remote runtime consumes (modal_app._apply_request_variance_diagnostics).
# Baseline arms translate to no overrides (deployment defaults apply).
_EXPERIMENT_ORIGIN_OVERRIDES: dict[tuple[str, str], dict[str, str]] = {
    ("unet_transfer", "pinned_staging"): {"unet_pinned_staging": "1"},
    ("vae_overlap", "early_250"): {"vae_early_start_ms": "250"},
    ("vae_overlap", "early_500"): {"vae_early_start_ms": "500"},
    ("vae_overlap", "early_750"): {"vae_early_start_ms": "750"},
    ("vae_overlap", "early_1000"): {"vae_early_start_ms": "1000"},
    ("png_encode", "level1"): {"png_compress_level": "1"},
    ("conditioning_hit", "async_lru"): {"conditioning_async_lru": "1"},
    # ── E28 per-run tuning arms (Targets B/C) ──
    # Loader threads/blocks and the FP32 cast-once experiment travel as
    # request-origin env so the integrated campaign can A/B them per request
    # against one deployment.  Baseline arms apply no override (deployment
    # defaults = the E28 winning production configuration).
    ("e28_clip_loader", "t8_b64"): {"clip_fastsafe_threads": "8",
                                     "clip_fastsafe_block_bytes": str(64 * 1024 * 1024)},
    ("e28_clip_loader", "t8_b32"): {"clip_fastsafe_threads": "8",
                                     "clip_fastsafe_block_bytes": str(32 * 1024 * 1024)},
    ("e28_clip_loader", "t8_b128"): {"clip_fastsafe_threads": "8",
                                      "clip_fastsafe_block_bytes": str(128 * 1024 * 1024)},
    ("e28_clip_loader", "t4_b64"): {"clip_fastsafe_threads": "4",
                                     "clip_fastsafe_block_bytes": str(64 * 1024 * 1024)},
    ("e28_unet_loader", "t8_b256"): {"unet_fastsafe_threads": "8",
                                      "unet_fastsafe_block_bytes": str(256 * 1024 * 1024)},
    ("e28_unet_loader", "t8_b128"): {"unet_fastsafe_threads": "8",
                                      "unet_fastsafe_block_bytes": str(128 * 1024 * 1024)},
    ("e28_unet_loader", "t8_b64"): {"unet_fastsafe_threads": "8",
                                     "unet_fastsafe_block_bytes": str(64 * 1024 * 1024)},
    ("e28_unet_loader", "t4_b256"): {"unet_fastsafe_threads": "4",
                                      "unet_fastsafe_block_bytes": str(256 * 1024 * 1024)},
    ("e28_fp32_cast_once", "on"): {"clip_fp32_cast_once": "1"},
    ("e28_fp32_cast_once", "off"): {"clip_fp32_cast_once": "0"},
}


def _experiment_origin_overrides() -> dict[str, str]:
    """Translate the campaign --experiment/--arm args into request-origin
    env overrides (bounded allowlist keys only; baseline -> {})."""
    args = globals().get("_EXPERIMENT_ARGS")
    if args is None:
        return {}
    experiment = str(getattr(args, "experiment", "") or "")
    arm = str(getattr(args, "arm", "") or "")
    return dict(_EXPERIMENT_ORIGIN_OVERRIDES.get((experiment, arm), {}))

# Plan-carried validation proof collection (plan-validation feature; default
# ON = harness behavior unchanged).  Explicitly disable with
# COMFYMODAL_V2_PLAN_VALIDATION_PROOF=0 when the local node registry cannot
# mirror the container (e.g. custom-node deps missing locally) and the run is
# measurement-only.
_PLAN_VALIDATION_PROOF = env_flag(
    "COMFYMODAL_V2_PLAN_VALIDATION_PROOF", default=True
)

# Bounded budget for joining the transport's post-result persistence drain at
# the end of each benchmark run.  The remote trailing persistence event arrives
# promptly after the result; this budget is ample for that arrival while still
# guaranteeing teardown never blocks indefinitely (timeout -> clean cancel).
_PERSISTENCE_DRAIN_JOIN_TIMEOUT = float(
    os.environ.get("COMFYMODAL_V2_PERSISTENCE_DRAIN_JOIN_TIMEOUT", "15")
)


def _resolve_restore_publisher(transport: ModalTransport, workspace: dict) -> Any | None:
    """Construct the legacy remote restore-plan publisher ONLY when the
    opt-in ``COMFYMODAL_V2_PUBLISH_RESTORE_PLAN`` flag is truthy.

    Default (unset / "0") returns ``None`` so ``execute_plan`` emits
    ``restore_publish_skipped`` and performs EXACTLY ONE Modal submission
    (``run_plan_stream``) with no blocking remote ``publish_restore_plan`` RPC
    in the critical path.  Flag=1 keeps the legacy publisher for diagnostics.
    """
    if publish_restore_plan_enabled():
        return RemoteRestorePlanPublisher(transport, workspace)
    return None


_NODE_REGISTRY_READY = False
# Registry-init boundary stamps (benchmark-only instrumentation): captured on
# the FIRST actual init only — never on the idempotent short-circuit — so
# ``node_registry_init_ms`` measures the full node-registry load cost that the
# (D1-fixed) local_receive → worker_start gap was previously attributed to;
# the registry now preloads once in ``main`` and is reported separately as
# ``node_registry_preload_ms``.
_NODE_REGISTRY_START_NS: int | None = None
_NODE_REGISTRY_END_NS: int | None = None


async def _ensure_full_node_registry() -> bool:
    """Mirror the ComfyUI server startup: load comfy_extras + custom nodes.

    Standalone plan construction needs the same node registry the server has
    (production builds run inside the server).  Called once per process before
    any plan build; never raises — returns readiness.
    """
    global _NODE_REGISTRY_READY, _NODE_REGISTRY_START_NS, _NODE_REGISTRY_END_NS
    if _NODE_REGISTRY_READY:
        return True
    _NODE_REGISTRY_START_NS = time.time_ns()
    try:
        # Bulletproof pre-lock: pin the REAL ComfyUI ``utils`` package into
        # sys.modules by explicit file path, immune to sys.path shadowing.
        # ``import nodes`` itself inserts ``<ComfyUI root>\comfy`` at
        # sys.path[0] (ComfyUI nodes.py:23); after that a plain ``import
        # utils`` resolves to ``comfy\utils.py`` (a module, not the ``utils``
        # package) and every ``utils.install_util`` import fails.  Pinning by
        # path BEFORE ``import nodes`` keeps the real package in sys.modules
        # so even ``import nodes``'s transitive imports and every later node
        # import see it (comfyui-impact-pack / RES4LYF need it).
        import importlib.util as _ilu
        _utils_init = os.path.join(_COMFYUI_ROOT_DIR, "utils", "__init__.py")
        if os.path.isfile(_utils_init):
            _utils_spec = _ilu.spec_from_file_location("utils", _utils_init)
            _utils_mod = _ilu.module_from_spec(_utils_spec)
            sys.modules["utils"] = _utils_mod
            if _utils_spec.loader is not None:
                _utils_spec.loader.exec_module(_utils_mod)
            import utils.install_util  # noqa: F401
        else:
            raise RuntimeError(f"ComfyUI utils package not found at {_utils_init}")
        import nodes
        # Mirror main.py:470 — construct a PromptServer BEFORE loading custom
        # nodes so packs that decorate ``@PromptServer.instance.routes`` at
        # import time (Impact Pack impact_server.py, RES4LYF res4lyf.py,
        # comfyui-manager, etc.) can register.  ``PromptServer.instance`` is
        # only assigned inside ``PromptServer.__init__`` (server.py:205); the
        # real server sets it in main.py:470 before ``nodes.init_extra_nodes``
        # (main.py:476).  Network-free mirror: ``front_end_root`` points at the
        # local web dir so ``FrontendManager.init_frontend`` is skipped
        # (server.py:239-243), manager is disabled, and no socket is bound
        # (the real server binds later via start()).
        import server
        from comfy.cli_args import args as _cli_args
        for _field, _value in (
            ("enable_compress_response_body", False),
            ("enable_cors_header", None),
            ("disable_api_nodes", False),
            ("enable_manager", False),
            ("max_upload_size", 100),
            ("front_end_root", os.path.join(_COMFYUI_ROOT_DIR, "web")),
            ("enable_assets", False),
        ):
            setattr(_cli_args, _field, _value)
        _prompt_server = server.PromptServer(asyncio.get_running_loop())
        print(
            f"[v2.harness] prompt_server_mirror instance_set={server.PromptServer.instance is _prompt_server}",
            flush=True,
        )
        await nodes.init_extra_nodes(init_custom_nodes=True, init_api_nodes=True)
        # Mirror comfyapp's manual registration of the comfyui-modal
        # production output classes (comfyapp.py:18186-18188 — the server
        # registers them after init_extra_nodes; init_extra_nodes never does).
        # We do NOT ``import comfyapp`` here: its module body resolves Modal
        # volumes via ``modal.Volume.from_name(...)`` (comfyapp.py lines
        # 8088/8093/8099/8126 — network/API calls) and builds GPU classes at
        # import time, which is unsafe/heavy in the harness.  Instead extract
        # ONLY the two class statements via AST (their methods are never
        # executed host-side) so ``__module__`` stays ``comfyapp`` for
        # registry-fingerprint parity with the container.
        try:
            # Register a lightweight ``comfyapp`` module stub BEFORE the AST
            # extraction so per-class canonical-identity resolution
            # (comfymodal_runtime.registry_proof) can resolve the module file
            # for the AST-registered production classes.  ``__file__`` points
            # at the repo's real comfyapp.py so the file-content hash used in
            # the canonical identity matches the container's comfyapp.py.
            import sys as _sys
            import types as _types
            if "comfyapp" not in _sys.modules:
                _comfyapp_stub = _types.ModuleType("comfyapp")
                _comfyapp_stub.__file__ = str(Path(ROOT) / "comfyapp.py")
                _sys.modules["comfyapp"] = _comfyapp_stub
            import ast as _ast
            _comfyapp_src = Path(ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
            _comfyapp_tree = _ast.parse(_comfyapp_src)
            _prod_class_names = {
                "ComfyModalProductionOutput",
                "ComfyModalProductionImageComparerOutput",
            }
            _class_stmts = [
                _n for _n in _comfyapp_tree.body
                if isinstance(_n, _ast.ClassDef) and _n.name in _prod_class_names
            ]
            _ns: dict = {"__name__": "comfyapp"}
            for _stmt in _class_stmts:
                exec(
                    compile(_ast.Module(body=[_stmt], type_ignores=[]), "comfyapp.py", "exec"),
                    _ns,
                )
            for _cls_name in sorted(_prod_class_names):
                _cls = _ns.get(_cls_name)
                if _cls is not None:
                    nodes.NODE_CLASS_MAPPINGS[_cls_name] = _cls
            print(
                f"[v2.harness] production_output_registered "
                f"output={'ComfyModalProductionOutput' in nodes.NODE_CLASS_MAPPINGS} "
                f"comparer={'ComfyModalProductionImageComparerOutput' in nodes.NODE_CLASS_MAPPINGS}",
                flush=True,
            )
        except Exception as _reg_exc:
            print(f"[v2.harness] production_output_registration_failed error={_reg_exc}", flush=True)
        _count = len(getattr(nodes, "NODE_CLASS_MAPPINGS", {}) or {})
        _NODE_REGISTRY_READY = True
        _NODE_REGISTRY_END_NS = time.time_ns()
        print(f"[v2.harness] node_registry_initialized classes={_count}", flush=True)
    except Exception as _exc:
        _NODE_REGISTRY_READY = False
        print(f"[v2.harness] node_registry_init_failed error={type(_exc).__name__}: {_exc}", flush=True)
    return _NODE_REGISTRY_READY


def _registry_proof_store_covers(
    workflow: dict,
    *,
    modal_options: dict[str, Any] | None = None,
    production_options: dict[str, Any] | None = None,
) -> bool:
    """True when a persisted registry-proof/validation store entry covers
    *workflow* under the current deploy-frozen identity.

    D1 zero-gap fast path: when covered, plan construction reuses persisted
    fingerprint/proof/validation payloads and the full node-registry import is
    skipped.  When COMFYMODAL_V2_PLAN_VALIDATION_PROOF is disabled the
    validation payload is not required (the proof payload is sufficient).
    Fail-closed: any lookup/mismatch → False (caller falls back to the full
    registry load).

    The lookup key is the DISPATCH workflow hash — the hash the store is
    saved under (``build_execution_plan`` compiles the production workflow,
    so the dispatch hash differs from ``prompt_sha256(source)`` whenever
    production compile rewrites the dict).  Computed via
    ``resolve_dispatch_workflow_hash`` (pure dict work; never imports the
    registry), mirroring the same inputs the plan build receives."""
    try:
        from comfymodal_runtime.registry_proof_store import lookup as _sl
        _lookup_hash = resolve_dispatch_workflow_hash(
            workflow,
            modal_options=modal_options,
            production_options=production_options,
        )
        _entry = _sl(
            workflow_hash=_lookup_hash,
            comfyui_root=str(_COMFYUI_ROOT_DIR or ""),
        )
    except Exception:
        return False
    if not isinstance(_entry, dict):
        return False
    if not (_entry.get("registry_fingerprint") or _entry.get("registry_proof")):
        return False
    if _PLAN_VALIDATION_PROOF and not _entry.get("validation"):
        return False
    return True

# ── Variance-cold mode (opt-in, never the default) ────────────────────────
# Unique shadow app name used ONLY for variance mode.  Normal/production modes
# keep the default APP_NAME identity above; this default is overridable only
# by an explicit environment variable.
VARIANCE_APP_NAME = os.environ.get(
    "COMFYMODAL_V2_VARIANCE_APP_NAME", "stable-modal-comfy-v2-variance-shadow"
)
# Fixed one-request-at-a-time gap for true-cold scaledown between runs.
VARIANCE_COLD_GAP_SECONDS = float(
    os.environ.get("V2_VARIANCE_COLD_GAP_SECONDS", "25")
)
# Number of variance-cold runs (defaults to the shared run count).
VARIANCE_RUN_COUNT = int(os.environ.get("V2_VARIANCE_RUN_COUNT", "0")) or RUN_COUNT

# ── Variance-cold MATRIX (four-condition round-robin) ──────────────────────
# Conditions: (diagnostics, pretouch) for each of the four cells.
MATRIX_CONDITIONS: list[tuple[int, int]] = [(0, 0), (0, 1), (1, 0), (1, 1)]
# Continue attempts until >= this many valid cold runs per condition.
MATRIX_TARGET_COLD_PER_CONDITION = int(
    os.environ.get("V2_MATRIX_TARGET_PER_CONDITION", "6")
)
# Safety cap on total attempts across all conditions.
MATRIX_MAX_TOTAL_ATTEMPTS = int(os.environ.get("V2_MATRIX_MAX_TOTAL_ATTEMPTS", "200"))
# ONE explicit fixed slow threshold (ms) applied across ALL conditions.
# It is a NONZERO default (never derived from condition medians).  A cold
# request normally takes tens of seconds; 60s separates pathological outliers.
MATRIX_SLOW_THRESHOLD_MS = float(
    os.environ.get("V2_VARIANCE_SLOW_THRESHOLD_MS", "60000") or 60000
)
# Fixed slow classification flags (ms), independent of any threshold.
MATRIX_RESTORE_SLOW_MS = 3000.0
MATRIX_UNET_ACTIVATION_SLOW_MS = 3000.0
MATRIX_CONDITION_LABEL = lambda diag, pretouch: f"diag{int(diag)}_pt{int(pretouch)}"

# ── Mounted-Volume raw sequential-read benchmark (opt-in; never default) ────
# Pure volume read speed of a mounted model file.  No graph execution, no
# model loading, no GPU work, no hashing, no /tmp writes.
VOLUME_READ_MODE = "volume_read"
VOLUME_READ_RUN_COUNT = int(os.environ.get("V2_VOLUME_READ_RUN_COUNT", "3"))
VOLUME_READ_GAP_SECONDS = float(
    os.environ.get("V2_VOLUME_READ_GAP_SECONDS", "25")
)
VOLUME_READ_FILENAME = os.environ.get(
    "V2_VOLUME_READ_FILENAME", "z_image_turbo_bf16.safetensors"
)
VOLUME_READ_CHUNK_BYTES = int(
    os.environ.get("V2_VOLUME_READ_CHUNK_BYTES", str(8 * 1024 * 1024))
)
VOLUME_READ_PASS_LABELS = ("primary_mounted_volume", "warm_cache")

# ── UNET-absent snapshot restore-only benchmark (opt-in; never default) ────
# Six valid reused-snapshot restore-only probes against a deployment whose
# CPU snapshot was constructed with COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1.
# Each probe is a single remote call to the no-op
# ``run_snapshot_restore_only_probe`` method; every probe is a candidate
# (no beautification probes), invalid/DNF probes never count toward the
# target, and the loop hard-stops as soon as EXACTLY ``RESTORE_ONLY_RUN_COUNT``
# valid probes are collected (bounded by a total-attempt safety cap).
RESTORE_ONLY_MODE = "snapshot_restore_only"
RESTORE_ONLY_APP_NAME = os.environ.get(
    "COMFYMODAL_V2_RESTORE_ONLY_APP_NAME",
    "stable-modal-comfy-v2-restore-only-shadow",
)
RESTORE_ONLY_RUN_COUNT = int(os.environ.get("V2_RESTORE_ONLY_RUN_COUNT", "6"))
RESTORE_ONLY_MAX_ATTEMPTS = int(os.environ.get("V2_RESTORE_ONLY_MAX_ATTEMPTS", "40"))
RESTORE_ONLY_GAP_SECONDS = float(
    os.environ.get("V2_RESTORE_ONLY_GAP_SECONDS", "30")
)
RESTORE_ONLY_RESTORING_BANNER = "Restoring Function from memory snapshot."


def _load_workspace() -> dict[str, Any]:
    data = json.loads(WORKSPACES_PATH.read_text(encoding="utf-8"))
    active_id = data.get("active_workspace_id")
    for workspace in data.get("workspaces", []):
        if workspace.get("id") == active_id:
            if not workspace.get("token_id") or not workspace.get("token_secret"):
                raise RuntimeError("active Modal workspace has no credentials")
            os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
            os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])
            return workspace
    raise RuntimeError("active Modal workspace was not found")


def _load_workflow() -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    payload = snapshot.get("payload", snapshot)
    workflow = payload.get("prompt", payload)
    modal_options = payload.get("modal_options", {})
    if not isinstance(workflow, dict):
        raise RuntimeError("workflow prompt must be an object")
    if not isinstance(modal_options, dict):
        modal_options = {}
    return workflow, modal_options


def _apply_unique_prompt_suffix(workflow: dict[str, Any], suffix: str) -> int:
    """Append a unique token to every literal prompt-text source so the
    exact-conditioning cache key is unique per run (deterministic miss).

    Mutates ``workflow`` in place.  Only text-bearing leaf inputs are
    touched: ``PrimitiveStringMultiline.inputs.value`` and any
    ``*TextEncode*`` node's LITERAL ``inputs.text`` string.  A node-link
    list (e.g. ``["80", 0]``) is not a literal string and is left
    untouched, so wire-fed encodes (CLIPTextEncode -> JoinStrings ->
    PrimitiveStringMultiline) are covered once at the primitive source.
    Loader/model nodes and all other inputs are never modified.  Returns
    the number of text sources modified (0 when the suffix is empty).
    """
    suffix = str(suffix or "").strip()
    if not suffix:
        return 0
    modified = 0
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        inputs = node.get("inputs")
        if not isinstance(class_type, str) or not isinstance(inputs, dict):
            continue
        if class_type == "PrimitiveStringMultiline":
            value = inputs.get("value")
            if isinstance(value, str):
                inputs["value"] = f"{value} {suffix}"
                modified += 1
        elif "TextEncode" in class_type:
            text = inputs.get("text")
            if isinstance(text, str):
                inputs["text"] = f"{text} {suffix}"
                modified += 1
    return modified


def _conditioning_cache_nonce_arg() -> str:
    """The active ``--conditioning-cache-nonce`` value ('' when unused).

    Read from the module-level ``_EXPERIMENT_ARGS`` namespace (populated in
    ``__main__``) exactly like ``_experiment_origin_overrides`` — the
    established pattern for reaching CLI args from deep call sites.  Safe
    under module import (namespace is None -> '').
    """
    args = globals().get("_EXPERIMENT_ARGS")
    if args is None:
        return ""
    return str(getattr(args, "conditioning_cache_nonce", "") or "").strip()


def _resolve_nonce_target_app() -> str:
    """Resolve the deployment a conditioning-cache-nonce measurement targets.

    The nonce is a request-scoped, semantic-neutral cache-isolation token.  It
    only yields a meaningful cold measurement against the D1-primed deployment
    recorded in ``.deployed_state.json`` (the deployment whose snapshot /
    identity / proof store were established).  The transport resolves the
    handle by ``COMFYMODAL_V2_APP_NAME`` and, when unset, falls back to the
    legacy default app (``stable-modal-comfy-v2-shadow``) — the D10 failure
    class: a nonce-carrying request silently targeted an OLD deployment whose
    baked runtime predates the nonce key isolation, so the fresh nonce never
    entered the cache key and a warm canonical entry served
    ``exact_hit/encode_calls=0``.

    Behavior:
      * nonce inactive                    -> '' (no-op; legacy behavior unchanged)
      * env app unset + primed identity   -> set ``COMFYMODAL_V2_APP_NAME`` to the
        primed app_name and return it (fail closed against the legacy default)
      * env app set + == primed           -> return it
      * env app set + != primed           -> raise (fail closed: a nonce against
        a different deployment is not a valid measurement)
      * no primed identity available      -> raise (fail closed: cannot know
        which deployment the nonce measurement is authorized against)

    Request-scoped: only runs when a nonce is active; never touches
    workflow/prompt/seed/model inputs; no global sticky state.
    """
    if not _conditioning_cache_nonce_arg():
        return ""
    primed = ""
    try:
        from comfymodal_runtime.registry_proof_store import deployed_state_path
        import json as _json

        _state = _json.loads(deployed_state_path().read_text(encoding="utf-8"))
        primed = str((_state or {}).get("app_name", "") or "").strip()
    except Exception:
        primed = ""
    if not primed:
        raise RuntimeError(
            "[v2.nonce_target] conditioning-cache nonce requires a D1-primed "
            "deployment identity (.deployed_state.json app_name); none found"
        )
    _env_app = os.environ.get("COMFYMODAL_V2_APP_NAME", "").strip()
    if _env_app and _env_app != primed:
        raise RuntimeError(
            f"[v2.nonce_target] COMFYMODAL_V2_APP_NAME={_env_app!r} does not match "
            f"the D1-primed deployment {primed!r}; refusing a nonce measurement "
            "against the wrong deployment"
        )
    if not _env_app:
        os.environ["COMFYMODAL_V2_APP_NAME"] = primed
        print(f"[v2.nonce_target] app={primed} source=d1_primed_identity", flush=True)
    return primed


def _benchmark_origin_extra(
    unique_prompt_suffix: str, conditioning_cache_nonce: str
) -> dict[str, Any] | None:
    """Request-origin extras for the default benchmark loop.

    Merges the two semantic vehicles onto one origin dict; empty values add
    no keys, so the request origin is byte-identical when neither option is
    used.  ``conditioning_cache_nonce`` is a semantic-neutral cache-key
    isolation token (never touches the workflow), while ``unique_prompt_suffix``
    keeps its existing semantics unchanged.
    """
    extra: dict[str, Any] = {}
    if unique_prompt_suffix:
        extra["unique_prompt_suffix"] = str(unique_prompt_suffix)
    if conditioning_cache_nonce:
        extra["conditioning_cache_nonce"] = str(conditioning_cache_nonce)
    return extra or None


# ── D6 fast-path deploy-profile validation (atomic opt-in gate) ─────────
# ``deploy_and_run_v2_single.bat`` force-sets these 8 values under
# ``V2_D6_FASTPATH_VALIDATION=1`` (1/true/yes/on).  ``--verify-d6-profile``
# compares the EFFECTIVE values — read from ``modal_app._runtime_env()``, the
# exact dict the deployment bakes — against the profile's expected map,
# aborting the launcher BEFORE ``modal deploy`` when they drift.  These maps
# MUST match the launcher profile block and the test suite.
D6_FASTPATH_PROFILE: dict[str, str] = {
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "1",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "1",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "1",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
}
# The launcher pins these when the profile is absent (production/default
# behavior unchanged) — the ``--verify-d6-profile`` gate is a trivial no-op
# PASS in that mode.
D6_PRODUCTION_DEFAULTS: dict[str, str] = {
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
}
# D10 integration-validation profile (Phase-D integration batch):
# identical to the D6 fast-path profile EXCEPT
# COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA=0.  The D6 run's SYNC_CUDA=1
# installs a global torch.cuda.synchronize wrapper plus a CUDA-event realize
# around every ModelPatcher.load/partially_load — INTRUSIVE on the request
# critical path (D10 Part-1 measurement-integrity audit).  D10 keeps the
# structural diagnostics (state checkpoints, hydration events, cast
# counters/histograms) while leaving synchronization to production semantics
# only.  MUST match the launcher profile block and the test suite.
D10_FASTPATH_PROFILE: dict[str, str] = {
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "1",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "1",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
}

E19_FINAL_COLD_LOADER_PROFILE_NAME = "E19_FINAL_COLD_LOADER"
E19_FINAL_COLD_LOADER_SELECTOR = "V2_E19_FINAL_COLD_LOADER"

E22_PREFETCH_OFF_SELECTOR = "V2_E22_PREFETCH_OFF"
E22_PREFETCH_ON_SELECTOR = "V2_E22_PREFETCH_ON"
E22_A_B_EXEMPT_KEYS: frozenset[str] = frozenset({"COMFYMODAL_V2_CHECKPOINT_PREWARM"})
E22_ARM_ALLOWED_PREWARM_VALUES: frozenset[str] = frozenset({"0", "1"})
E19_FINAL_COLD_LOADER_PROFILE: dict[str, str] = {
    "COMFYMODAL_V2_ATOMIC_PROFILE": E19_FINAL_COLD_LOADER_PROFILE_NAME,
    "COMFYMODAL_V2_ENV_PROFILE": "inherit",
    "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "1",
    "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "1",
    "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "clip_vae",
    "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
    "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "1",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM": "1",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "8",
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "1",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "1",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "1",
    "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "1",
    "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
    "COMFYMODAL_V2_C9QD_EXTRAS": "0",
    "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
    "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
}

# ── E25 whole-critical-path-compression validation profile ──────────────
# Atomic opt-in selector ``V2_E25_VALIDATION`` (1/true/yes/on).  Inherits the
# proven E19 final cold-loader architecture EXACTLY (E19 selector must be
# active) and changes ONLY the E25 validation flags:
#   * speculative CLIP hydration ON (COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION=1)
#   * proven-ready GPU fast return ON (COMFYMODAL_V2_GPU_FAST_RETURN=1)
#   * optimization diagnostics ON (COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1)
# E26 correction: the VAE early activation (sampling_end/250) is NO LONGER a
# production default — the selector uses the canonical late/safe mode.  The
# experiment remains available behind the explicit flags.  Run count is
# hard-gated to 1 (see _e25_validate_run_count).
E25_VALIDATION_SELECTOR = "V2_E25_VALIDATION"
E25_VALIDATION_PROFILE_NAME = "E25_VALIDATION"
E25_VALIDATION_PROFILE: dict[str, str] = {
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "1",
    "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
    "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "1",
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
}


# ── E26 concrete cold-wins validation profile ──────────────────────────
# Atomic opt-in selector ``V2_E26_VALIDATION`` (1/true/yes/on).  Inherits the
# proven E19 final cold-loader architecture EXACTLY (E19 selector must be
# active) and sets the E26 flags:
#   * E26 speculative CLIP hydration with frozen-manifest absolute paths ON
#   * proven-ready GPU fast return — production-enabled (default ON)
#   * checkpoint prewarm ON (coordinated CLIP-first/UNET-second schedule)
#   * UNET fastsafetensors ON, snapshot-excluded UNET ON, D15 ON
#   * VAE early activation OFF — canonical late/safe production mode
#   * optimization diagnostics ON
# Run count is hard-gated to exactly 1 per run (see _e26_validate_run_count);
# a cycle uses two separate runs on the same deployment.
E26_VALIDATION_SELECTOR = "V2_E26_VALIDATION"
E26_VALIDATION_PROFILE_NAME = "E26_VALIDATION"
E26_VALIDATION_PROFILE: dict[str, str] = {
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "1",
    "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
    "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "1",
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM": "1",
}


def _e26_profile_active() -> bool:
    raw = os.environ.get(E26_VALIDATION_SELECTOR, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


# ── E28 critical-path implementation validation profile ──────────────────
# Atomic opt-in selector ``V2_E28_VALIDATION`` (1/true/yes/on).  Inherits the
# proven E19 final cold-loader architecture EXACTLY (E19 selector must be
# active) and adds the E28 production optimizations:
#   * earliest restore-time CLIP lane (speculative CLIP ON)
#   * tuned direct-GPU loader configs — CLIP T8/B64MiB and UNET T8/B256MiB
#     are now the CODE DEFAULTS (E27 Follow-Up A first-touch winners), so no
#     extra env is required; the env keys are verified as present with the
#     default values
#   * multi-window readable Gantt + E27 forensics telemetry ON
#   * FP32 cast-once OFF (experimental; opt-in per request via the
#     e28_fp32_cast_once experiment arm)
# Run count is hard-gated to exactly 1 per run (see _e28_validate_run_count);
# a cycle uses two separate runs on the same deployment.
E28_VALIDATION_SELECTOR = "V2_E28_VALIDATION"
E28_VALIDATION_PROFILE_NAME = "E28_VALIDATION"
E28_VALIDATION_PROFILE: dict[str, str] = {
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "1",
    "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
    "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "1",
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM": "1",
    "COMFYMODAL_V2_GANTT_TELEMETRY": "1",
    "COMFYMODAL_V2_E27_FORENSICS": "1",
}
E28_LOADER_PROFILE: dict[str, str] = {
    "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "8",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": str(64 * 1024 * 1024),
    "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": str(512 * 1024),
    "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "8",
    "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": str(256 * 1024 * 1024),
    "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": str(512 * 1024),
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
}


def _e28_profile_active() -> bool:
    raw = os.environ.get(E28_VALIDATION_SELECTOR, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _e28_validate_run_count() -> None:
    """Hard single-run guard for the E28 validation selector.

    When the E28 selector is active, both the explicit ``--run-count`` AND
    ``V2_BENCHMARK_RUNS`` must resolve to exactly ``1`` and a conditioning
    nonce must be present (fresh-cache requirement).  Refuses paid execution
    otherwise, BEFORE any Modal invocation.  A validation cycle runs exactly
    two separate requests (--run-count 1 twice) on the same deployment.
    """
    if not _e28_profile_active():
        return
    _runs = os.environ.get("V2_BENCHMARK_RUNS", "").strip()
    if _runs != "1":
        print(
            "=== ERROR: E28 validation requires V2_BENCHMARK_RUNS=1, "
            f"got {_runs!r}; refusing paid execution ===",
            flush=True,
        )
        sys.exit(1)
    _nonce = os.environ.get("COMFYMODAL_V2_CONDITIONING_NONCE", "").strip()
    if not _nonce:
        print(
            "=== ERROR: E28 validation requires a fresh conditioning nonce "
            "(V2_E28_CONDITIONING_NONCE); refusing paid execution ===",
            flush=True,
        )
        sys.exit(1)


def verify_e28_validation_profile() -> tuple[bool, dict[str, Any]]:
    """Fail-fast local check of the E28 validation profile.

    Requires the E19 selector active (exact E19 base) plus the E28
    validation flags equal to ``E28_VALIDATION_PROFILE`` and the E28 loader
    defaults equal to ``E28_LOADER_PROFILE``.  Fails closed on any conflict
    (D6/D10/E10) or mismatch.  Reads the effective values from
    ``_runtime_env()`` — the exact dict the deployment bakes.
    """
    if not _e28_profile_active():
        return False, {
            "profile": E28_VALIDATION_PROFILE_NAME,
            "active": False,
            "validation": "FAIL",
            "error": f"{E28_VALIDATION_SELECTOR} is not active",
        }
    if not _e19_profile_active():
        return False, {
            "profile": E28_VALIDATION_PROFILE_NAME,
            "active": True,
            "validation": "FAIL",
            "error": f"E28 validation requires {E19_FINAL_COLD_LOADER_SELECTOR}=1",
        }
    if _d6_profile_active() or _d10_profile_active() or _e10_profile_active():
        return False, {
            "profile": E28_VALIDATION_PROFILE_NAME,
            "active": True,
            "validation": "FAIL",
            "error": "E28 validation cannot combine with D6/D10/E10 atomic profiles",
        }
    details: dict[str, Any] = {
        "profile": E28_VALIDATION_PROFILE_NAME,
        "active": True,
    }
    ok = True
    try:
        from comfymodal_runtime.modal_app import _runtime_env
        effective = _runtime_env()
    except Exception as exc:  # noqa: BLE001 - fail closed
        for _key in (tuple(E28_VALIDATION_PROFILE) + tuple(E28_LOADER_PROFILE)
                     + tuple(E19_FINAL_COLD_LOADER_PROFILE)):
            details[_key] = "unavailable"
        details["validation"] = "FAIL"
        details["error"] = f"{type(exc).__name__}: {exc}"
        return False, details
    # E19 base must be exact.
    for _key, _expected in E19_FINAL_COLD_LOADER_PROFILE.items():
        _got = _d6_normalize(effective.get(_key))
        details[_key] = _got
        if _got != _expected:
            ok = False
    # E28 validation flags must be exact.
    for _key, _expected in E28_VALIDATION_PROFILE.items():
        _got = _d6_normalize(effective.get(_key))
        details[_key] = _got
        if _got != _expected:
            ok = False
    # E28 loader defaults must be exact (the winning production config).
    for _key, _expected in E28_LOADER_PROFILE.items():
        _got = _d6_normalize(effective.get(_key))
        details[_key] = _got
        if _got != _expected:
            ok = False
    details["validation"] = "PASS" if ok else "FAIL"
    if not ok:
        details["error"] = "profile mismatch (see per-key values)"
    return ok, details


def _e26_validate_run_count() -> None:
    """Hard single-run guard for the E26 validation selector.

    When the E26 selector is active, both the explicit ``--run-count`` AND
    ``V2_BENCHMARK_RUNS`` must resolve to exactly ``1`` and a conditioning
    nonce must be present (fresh-cache requirement).  Refuses paid execution
    otherwise, BEFORE any Modal invocation.  A validation cycle runs exactly
    two separate requests (--run-count 1 twice) on the same deployment.
    """
    if not _e26_profile_active():
        return
    _runs = os.environ.get("V2_BENCHMARK_RUNS", "").strip()
    if _runs != "1":
        print(
            "=== ERROR: E26 validation requires V2_BENCHMARK_RUNS=1, "
            f"got {_runs!r}; refusing paid execution ===",
            flush=True,
        )
        sys.exit(1)
    _nonce = os.environ.get("COMFYMODAL_V2_CONDITIONING_NONCE", "").strip()
    if not _nonce:
        print(
            "=== ERROR: E26 validation requires a fresh conditioning nonce "
            "(V2_E26_CONDITIONING_NONCE); refusing paid execution ===",
            flush=True,
        )
        sys.exit(1)


def verify_e26_validation_profile() -> tuple[bool, dict[str, Any]]:
    """Fail-fast local check of the E26 validation profile.

    Requires the E19 selector active (exact E19 base) plus the E26
    validation flags equal to ``E26_VALIDATION_PROFILE``.  Fails closed on
    any conflict (D6/D10/E10) or mismatch.  Reads the effective values from
    ``_runtime_env()`` — the exact dict the deployment bakes.
    """
    if not _e26_profile_active():
        return False, {
            "profile": E26_VALIDATION_PROFILE_NAME,
            "active": False,
            "validation": "FAIL",
            "error": f"{E26_VALIDATION_SELECTOR} is not active",
        }
    if not _e19_profile_active():
        return False, {
            "profile": E26_VALIDATION_PROFILE_NAME,
            "active": True,
            "validation": "FAIL",
            "error": f"E26 validation requires {E19_FINAL_COLD_LOADER_SELECTOR}=1",
        }
    if _d6_profile_active() or _d10_profile_active() or _e10_profile_active():
        return False, {
            "profile": E26_VALIDATION_PROFILE_NAME,
            "active": True,
            "validation": "FAIL",
            "error": "E26 validation cannot combine with D6/D10/E10 atomic profiles",
        }
    details: dict[str, Any] = {
        "profile": E26_VALIDATION_PROFILE_NAME,
        "active": True,
    }
    ok = True
    try:
        from comfymodal_runtime.modal_app import _runtime_env
        effective = _runtime_env()
    except Exception as exc:  # noqa: BLE001 - fail closed
        for _key in tuple(E26_VALIDATION_PROFILE) + tuple(E19_FINAL_COLD_LOADER_PROFILE):
            details[_key] = "unavailable"
        details["validation"] = "FAIL"
        details["error"] = f"{type(exc).__name__}: {exc}"
        return False, details
    # E19 base must be exact.
    for _key, _expected in E19_FINAL_COLD_LOADER_PROFILE.items():
        _got = _d6_normalize(effective.get(_key))
        details[_key] = _got
        if _got != _expected:
            ok = False
    # E26 validation flags must be exact.
    for _key, _expected in E26_VALIDATION_PROFILE.items():
        _got = _d6_normalize(effective.get(_key))
        details[_key] = _got
        if _got != _expected:
            ok = False
    details["validation"] = "PASS" if ok else "FAIL"
    if not ok:
        details["error"] = "profile mismatch (see per-key values)"
    return ok, details


def _e25_profile_active() -> bool:
    raw = os.environ.get(E25_VALIDATION_SELECTOR, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _e25_validate_run_count() -> None:
    """Hard single-run guard for the E25 validation selector.

    Mirrors the E22 hard protection: when the E25 selector is active, both the
    explicit ``--run-count`` AND ``V2_BENCHMARK_RUNS`` must resolve to exactly
    ``1`` and a conditioning nonce must be present (fresh-cache requirement).
    Refuses paid execution otherwise, BEFORE any Modal invocation.
    """
    if not _e25_profile_active():
        return
    _runs = os.environ.get("V2_BENCHMARK_RUNS", "").strip()
    if _runs != "1":
        print(
            "=== ERROR: E25 validation requires V2_BENCHMARK_RUNS=1, "
            f"got {_runs!r}; refusing paid execution ===",
            flush=True,
        )
        sys.exit(1)
    _nonce = os.environ.get("COMFYMODAL_V2_CONDITIONING_NONCE", "").strip()
    if not _nonce:
        print(
            "=== ERROR: E25 validation requires a fresh conditioning nonce "
            "(V2_E25_CONDITIONING_NONCE); refusing paid execution ===",
            flush=True,
        )
        sys.exit(1)


def verify_e25_validation_profile() -> tuple[bool, dict[str, Any]]:
    """Fail-fast local check of the E25 validation profile.

    Requires the E19 selector active (exact E19 base) plus the five E25
    validation flags equal to ``E25_VALIDATION_PROFILE``.  Fails closed on any
    conflict (D6/D10/E10) or mismatch.  Reads the effective values from
    ``_runtime_env()`` — the exact dict the deployment bakes.
    """
    if not _e25_profile_active():
        return False, {
            "profile": E25_VALIDATION_PROFILE_NAME,
            "active": False,
            "validation": "FAIL",
            "error": f"{E25_VALIDATION_SELECTOR} is not active",
        }
    if not _e19_profile_active():
        return False, {
            "profile": E25_VALIDATION_PROFILE_NAME,
            "active": True,
            "validation": "FAIL",
            "error": f"E25 validation requires {E19_FINAL_COLD_LOADER_SELECTOR}=1",
        }
    if _d6_profile_active() or _d10_profile_active() or _e10_profile_active():
        return False, {
            "profile": E25_VALIDATION_PROFILE_NAME,
            "active": True,
            "validation": "FAIL",
            "error": "E25 validation cannot combine with D6/D10/E10 atomic profiles",
        }
    details: dict[str, Any] = {
        "profile": E25_VALIDATION_PROFILE_NAME,
        "active": True,
    }
    ok = True
    try:
        from comfymodal_runtime.modal_app import _runtime_env
        effective = _runtime_env()
    except Exception as exc:  # noqa: BLE001 - fail closed
        for _key in tuple(E25_VALIDATION_PROFILE) + tuple(E19_FINAL_COLD_LOADER_PROFILE):
            details[_key] = "unavailable"
        details["validation"] = "FAIL"
        details["error"] = f"{type(exc).__name__}: {exc}"
        return False, details
    # E19 base must be exact.
    for _key, _expected in E19_FINAL_COLD_LOADER_PROFILE.items():
        _got = _d6_normalize(effective.get(_key))
        details[_key] = _got
        if _got != _expected:
            ok = False
    # E25 validation flags must be exact (VAE early-start 250, NOT the parity 0).
    for _key, _expected in E25_VALIDATION_PROFILE.items():
        _got = _d6_normalize(effective.get(_key))
        details[_key] = _got
        if _got != _expected:
            ok = False
    details["validation"] = "PASS" if ok else "FAIL"
    return ok, details


def evaluate_e19_structural_gate(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed on runtime execution proof, never on enabled flags alone."""
    checks = {
        "atomic_profile_exact": evidence.get("atomic_profile")
        == E19_FINAL_COLD_LOADER_PROFILE_NAME,
        "snapshot_unet_weights_absent": evidence.get(
            "snapshot_unet_weights_present"
        ) is False,
        "fresh_restore": evidence.get("fresh_restore") is True,
        "clip_execution_identity": evidence.get("clip_loader_execution_identity")
        == "fastsafetensors_direct_gpu",
        "unet_execution_identity": evidence.get("unet_loader_execution_identity")
        == "fastsafetensors",
        "clip_fallback_zero": evidence.get("clip_fallback_count") == 0,
        "unet_fallback_zero": evidence.get("unet_fallback_count") == 0,
        "clip_source_fence": evidence.get("clip_source_fence_valid") is True,
        "unet_source_fence": evidence.get("unet_source_fence_valid") is True,
        "clip_workers_retired": evidence.get("clip_workers_alive_at_demand_start")
        == 0,
        "unet_workers_retired": evidence.get("unet_workers_alive_at_demand_start")
        == 0,
        "prefetch_demand_collision_absent": evidence.get(
            "prefetch_and_demand_overlap_detected"
        ) is False,
        "unet_gpu_overlap_absent": evidence.get(
            "unet_gpu_overlap_with_clip_critical"
        ) is False
        and evidence.get("unet_gpu_overlap_with_clip_critical_ms") == 0,
        "clip_copy_event_recorded": evidence.get("clip_copy_event_recorded") is True,
        "clip_copy_event_waited": evidence.get("clip_copy_event_waited") is True
        or evidence.get("clip_copy_event_waited_at") is not None,
        "unet_copy_event_recorded": evidence.get("unet_copy_event_recorded") is True,
        "unet_copy_event_waited": evidence.get("unet_copy_event_waited") is True
        or evidence.get("unet_copy_event_waited_at") is not None,
        "clip_ready_emitted": evidence.get("clip_ready_at") is not None,
        "unet_ready_emitted": evidence.get("unet_ready_at") is not None,
        "model_readiness_gate_emitted": evidence.get(
            "model_readiness_status"
        ) == "KNOWN"
        and evidence.get("model_readiness_gate_ms") is not None,
        "canonical_output_sha_match": evidence.get("canonical_output_sha_match")
        is True,
    }
    failures = sorted(name for name, passed in checks.items() if not passed)
    return {
        "valid": not failures,
        "checks": checks,
        "failures": failures,
        "clip_forward_health": evidence.get("clip_forward_health", "UNKNOWN"),
        "enabled_flag_counts_as_execution_proof": False,
    }
_D6_PROFILE_KEYS: tuple[str, ...] = tuple(D6_FASTPATH_PROFILE)

E10_BUCKET_FIRST_PROFILE: dict[str, str] = {
    "COMFYMODAL_V2_STAGED_SAFETENSORS": "1",
    "COMFYMODAL_V2_STAGED_PRODUCERS": "4",
    "COMFYMODAL_V2_STAGED_POOL_MB": "1024",
    "COMFYMODAL_V2_STAGED_BUCKET_MB": "256",
    "COMFYMODAL_V2_STAGED_CPU_CAST": "1",
    "COMFYMODAL_V2_STAGED_ASYNC_H2D": "1",
    "COMFYMODAL_V2_STAGED_CONTIGUOUS_GPU_BUCKETS": "1",
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "1",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "1",
    "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "1",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "1",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "1",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
}


def _e10_profile_active() -> bool:
    raw = os.environ.get("V2_E10_BUCKET_FIRST_VALIDATION", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _e19_profile_active() -> bool:
    raw = os.environ.get(E19_FINAL_COLD_LOADER_SELECTOR, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _e22_arm_active() -> str:
    """Return the E22 arm label ('off'|'on'|'') if an E22 arm selector is active."""
    if os.environ.get(E22_PREFETCH_OFF_SELECTOR, "").strip().lower() in {"1", "true", "yes", "on"}:
        return "off"
    if os.environ.get(E22_PREFETCH_ON_SELECTOR, "").strip().lower() in {"1", "true", "yes", "on"}:
        return "on"
    return ""


def _profile_value(raw: Any) -> str:
    value = str(raw or "").strip()
    return "0" if value == "" else value


def verify_e10_bucket_first_profile() -> tuple[bool, dict[str, Any]]:
    """Verify the exact local runtime env baked by the E10 B deploy."""
    details: dict[str, Any] = {
        "profile": "e10_bucket_first",
        "active": _e10_profile_active(),
    }
    if not details["active"]:
        details["validation"] = "FAIL"
        details["error"] = "V2_E10_BUCKET_FIRST_VALIDATION is not active"
        return False, details
    try:
        from comfymodal_runtime.modal_app import _runtime_env
        effective = _runtime_env()
    except Exception as exc:  # noqa: BLE001 - fail closed
        details["validation"] = "FAIL"
        details["error"] = f"{type(exc).__name__}: {exc}"
        return False, details
    ok = True
    for key, expected in E10_BUCKET_FIRST_PROFILE.items():
        got = _profile_value(effective.get(key))
        details[key] = got
        if got != expected:
            ok = False
    details["validation"] = "PASS" if ok else "FAIL"
    return ok, details


def _run_e10_profile_cli() -> int:
    ok, details = verify_e10_bucket_first_profile()
    print("[v2.e10_bucket_first_profile]", flush=True)
    print(f"profile={details.get('profile', 'e10_bucket_first')}", flush=True)
    for key, expected in E10_BUCKET_FIRST_PROFILE.items():
        print(
            f"{key}={details.get(key, 'unavailable')} expected={expected}",
            flush=True,
        )
    print(f"validation={details.get('validation', 'FAIL')}", flush=True)
    if details.get("error"):
        print(f"error={details['error']}", flush=True)
    return 0 if ok else 1


async def _run_e10_remote_profile_cli() -> int:
    """Read the deployed container env before any E10 graph submission."""
    if not _e10_profile_active():
        print("[v2.e10_remote_profile] validation=FAIL", flush=True)
        print("error=V2_E10_BUCKET_FIRST_VALIDATION is not active", flush=True)
        return 1
    try:
        workspace = _load_workspace()
        transport = ModalTransport()
        handle = await asyncio.to_thread(
            transport._v2_handle, workspace=workspace, gpu=GPU,
        )
        fn = getattr(handle, "run_env_probe", None)
        if fn is None:
            raise RuntimeError("deployed container has no run_env_probe method")
        remote = getattr(fn, "remote", None)
        if remote is not None and callable(getattr(remote, "aio", None)):
            probe = remote.aio(request_id="v2-e10-profile-probe")
            if asyncio.iscoroutine(probe):
                probe = await probe
        elif asyncio.iscoroutinefunction(fn):
            probe = await fn(request_id="v2-e10-profile-probe")
        else:
            probe = await asyncio.to_thread(fn, request_id="v2-e10-profile-probe")
        if asyncio.iscoroutine(probe):
            probe = await probe
        if not isinstance(probe, dict):
            raise RuntimeError(f"run_env_probe returned {type(probe).__name__}")
        remote_env = probe.get("env", {})
        if not isinstance(remote_env, dict):
            raise RuntimeError("run_env_probe env payload is not a mapping")
        failures: list[str] = []
        for key, expected in E10_BUCKET_FIRST_PROFILE.items():
            got = _profile_value(remote_env.get(key))
            print(f"{key}={got} expected={expected}", flush=True)
            if got != expected:
                failures.append(f"{key}: got {got!r}, expected {expected!r}")
        expected_app = os.environ.get("COMFYMODAL_V2_APP_NAME", "").strip()
        remote_app = str(remote_env.get("COMFYMODAL_V2_APP_NAME", "") or "").strip()
        if expected_app and remote_app != expected_app:
            failures.append(
                f"COMFYMODAL_V2_APP_NAME: got {remote_app!r}, expected {expected_app!r}"
            )
        print(f"probe_provider={probe.get('provider', '')}", flush=True)
        print(f"probe_region={probe.get('region', '')}", flush=True)
        print(f"validation={'PASS' if not failures else 'FAIL'}", flush=True)
        for failure in failures:
            print(f"failure={failure}", flush=True)
        return 0 if not failures else 1
    except Exception as exc:  # noqa: BLE001 - fail closed before graph spend
        print("[v2.e10_remote_profile] validation=FAIL", flush=True)
        print(f"error={type(exc).__name__}: {exc}", flush=True)
        return 1


def _d6_profile_active() -> bool:
    """True when ``V2_D6_FASTPATH_VALIDATION`` is 1/true/yes/on
    (case-insensitive) in the current environment."""
    raw = os.environ.get("V2_D6_FASTPATH_VALIDATION", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _d10_profile_active() -> bool:
    """True when ``V2_D10_INTEGRATION_VALIDATION`` is 1/true/yes/on
    (case-insensitive) in the current environment.  D10 takes precedence
    over D6 when both are set (the verifier is profile-aware)."""
    raw = os.environ.get("V2_D10_INTEGRATION_VALIDATION", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _d6_normalize(raw: Any) -> str:
    """Normalize one effective flag value for comparison/reporting.

    The ``COMFYMODAL_V2_UNET_FASTSAFETENSORS`` passthrough in ``_runtime_env``
    defaults to '' (empty = off) for an unset local var; the launcher pins it
    to "0".  Both mean the flag is OFF, so an empty/absent value is reported
    and compared as "0".  Any other value is preserved verbatim.
    """
    value = str(raw or "")
    value = value.strip()
    return "0" if value == "" else value


def verify_d6_fastpath_profile() -> tuple[bool, dict[str, Any]]:
    """Fail-fast local check of the D6/D10/E19 deploy profile against the
    ACTUAL ``comfymodal_runtime.modal_app._runtime_env()`` construction.

    FOUR-MODE CONTRACT:
      * D10 profile active (``V2_D10_INTEGRATION_VALIDATION`` = 1/true/yes/on):
        the eight fast-path flags MUST equal ``D10_FASTPATH_PROFILE``
        (1,1,1,1,1,0,1,0) — SYNC_CUDA=0 for measurement integrity.
      * D6 profile active (``V2_D6_FASTPATH_VALIDATION`` = 1/true/yes/on):
        the eight flags MUST equal ``D6_FASTPATH_PROFILE`` (1,1,1,1,1,1,1,0).
      * Neither active: the eight flags MUST equal ``D6_PRODUCTION_DEFAULTS``
        (0,0,0,0,0,0,1,0) — the values the launcher pins when no profile is
        opted in, so the launcher's always-on verify call is a trivial no-op
        gate in default mode while enforcing the exact profile when opted in.
      * E19 profile active (``V2_E19_FINAL_COLD_LOADER`` = 1/true/yes/on):
        every E19 loader, transport, orchestration, and safety flag MUST equal
        ``E19_FINAL_COLD_LOADER_PROFILE``.  E19 cannot be combined with D6,
        D10, or E10.

    The effective values are read from ``_runtime_env()`` itself — the exact
    dict the deployment bakes — never from the raw process env (with no spec
    argument, matching the deployment path's default spec).  ``_runtime_env``
    is imported lazily so module import stays light.  Returns ``(ok, details)``
    where ``details`` carries the effective values + ``validation`` =
    ``"PASS"``/``"FAIL"`` (+ an ``error`` field when the import/call raised).
    """
    d10 = _d10_profile_active()
    d6 = _d6_profile_active()
    e10 = _e10_profile_active()
    e19 = _e19_profile_active()
    if e19:
        expected = dict(E19_FINAL_COLD_LOADER_PROFILE)
        profile_label = E19_FINAL_COLD_LOADER_PROFILE_NAME
        profile_keys = tuple(expected)
    elif d10:
        expected = dict(D10_FASTPATH_PROFILE)
        profile_label = "d10_integration_validation"
        profile_keys = _D6_PROFILE_KEYS
    elif d6:
        expected = dict(D6_FASTPATH_PROFILE)
        profile_label = "fastpath_validation"
        profile_keys = _D6_PROFILE_KEYS
    else:
        expected = dict(D6_PRODUCTION_DEFAULTS)
        profile_label = "default"
        profile_keys = _D6_PROFILE_KEYS
    details: dict[str, Any] = {
        "profile": profile_label,
        "active": bool(e19 or d10 or d6),
    }
    try:
        from comfymodal_runtime.modal_app import _runtime_env
        effective = _runtime_env()
    except Exception as _d6_exc:  # noqa: BLE001 - fail closed
        for _key in profile_keys:
            details[_key] = "unavailable"
        details["validation"] = "FAIL"
        details["error"] = f"{type(_d6_exc).__name__}: {_d6_exc}"
        return False, details
    e22_arm = _e22_arm_active()
    ok = True
    for _key in profile_keys:
        _got = _d6_normalize(effective.get(_key))
        details[_key] = _got
        if e19 and e22_arm and _key in E22_A_B_EXEMPT_KEYS:
            if _got not in E22_ARM_ALLOWED_PREWARM_VALUES:
                ok = False
            elif e22_arm == "off" and _got != "0":
                ok = False
                details["error"] = f"arm=off requires CHECKPOINT_PREWARM=0, got {_got}"
            elif e22_arm == "on" and _got != "1":
                ok = False
                details["error"] = f"arm=on requires CHECKPOINT_PREWARM=1, got {_got}"
        else:
            if _got != expected[_key]:
                ok = False
    details["e22_arm"] = e22_arm or None
    if e19:
        _conflicts = []
        if d10:
            _conflicts.append("V2_D10_INTEGRATION_VALIDATION")
        if d6:
            _conflicts.append("V2_D6_FASTPATH_VALIDATION")
        if e10:
            _conflicts.append("V2_E10_BUCKET_FIRST_VALIDATION")
        if _conflicts:
            ok = False
            details["error"] = (
                f"{E19_FINAL_COLD_LOADER_PROFILE_NAME} cannot combine with "
                + ", ".join(_conflicts)
            )
    details["validation"] = "PASS" if ok else "FAIL"
    return ok, details


def verify_e22_arm_profile() -> tuple[bool, dict[str, Any]]:
    """Verify E22 arm profile: E19 atomic profile + arm-specific CHECKPOINT_PREWARM."""
    e22_arm = _e22_arm_active()
    if not e22_arm:
        return False, {
            "profile": E19_FINAL_COLD_LOADER_PROFILE_NAME,
            "active": False,
            "validation": "FAIL",
            "error": "no E22 arm selector active (need V2_E22_PREFETCH_OFF or V2_E22_PREFETCH_ON)",
        }
    if not _e19_profile_active():
        return False, {
            "profile": E19_FINAL_COLD_LOADER_PROFILE_NAME,
            "active": False,
            "validation": "FAIL",
            "error": f"E22 arm requires {E19_FINAL_COLD_LOADER_SELECTOR}=1",
        }
    return verify_d6_fastpath_profile()


def verify_e19_final_cold_loader_profile() -> tuple[bool, dict[str, Any]]:
    """Verify that the explicit E19 selector is active and exact."""
    if not _e19_profile_active():
        return False, {
            "profile": E19_FINAL_COLD_LOADER_PROFILE_NAME,
            "active": False,
            "validation": "FAIL",
            "error": f"{E19_FINAL_COLD_LOADER_SELECTOR} is not active",
        }
    return verify_d6_fastpath_profile()


def _run_d6_verify_cli() -> int:
    """Print the bounded atomic-profile block and return its gate exit code."""
    ok, details = verify_d6_fastpath_profile()
    print("[v2.d6_deploy_profile]", flush=True)
    print(f"profile={details.get('profile', 'default')}", flush=True)
    if details.get("profile") == E19_FINAL_COLD_LOADER_PROFILE_NAME:
        _profile_keys = tuple(E19_FINAL_COLD_LOADER_PROFILE)
        _atomic_name = E19_FINAL_COLD_LOADER_PROFILE_NAME
    elif details.get("profile") == "d10_integration_validation":
        _profile_keys = tuple(D10_FASTPATH_PROFILE)
        _atomic_name = "D10_INTEGRATION_VALIDATION"
    elif details.get("profile") == "fastpath_validation":
        _profile_keys = tuple(D6_FASTPATH_PROFILE)
        _atomic_name = "D6_FASTPATH_VALIDATION"
    else:
        _profile_keys = tuple(D6_PRODUCTION_DEFAULTS)
        _atomic_name = "PRODUCTION_DEFAULT"
    print(f"ATOMIC_PROFILE={_atomic_name}", flush=True)
    for _key in _profile_keys:
        _short = _key.removeprefix("COMFYMODAL_V2_").lower()
        print(f"{_short}={details.get(_key, 'unavailable')}", flush=True)
    print(f"validation={details.get('validation', 'FAIL')}", flush=True)
    if details.get("error"):
        print(f"error={details['error']}", flush=True)
    if ok:
        print("PROFILE ACCEPTED", flush=True)
        if details.get("profile") == E19_FINAL_COLD_LOADER_PROFILE_NAME:
            print("DEPLOY COMMAND CONSTRUCTED", flush=True)
            print(
                "DEPLOY_COMMAND=modal deploy -m "
                "comfymodal_runtime.modal_app",
                flush=True,
            )
            print("EPHEMERAL_PATH_USED=NO", flush=True)
    else:
        print("PROFILE REJECTED", flush=True)
    return 0 if ok else 1


def _deployment_state_atomic_profile_matches(
    state: Mapping[str, Any], expected: str
) -> bool:
    """Require fresh state proof when a concrete atomic profile is selected."""
    if not expected:
        return True
    return str(state.get("atomic_profile") or "").strip() == expected


def _run_run_preflight_cli(nonce: str = "") -> int:
    """Fail-fast local preflight for ``run_v2_single.bat`` BEFORE Modal submission.

    Verifies the request-side environment matches the D1-primed deployed
    identity recorded in ``.deployed_state.json`` (app, class, deployment
    identity, runtime shape, D1 proof coverage, run count) so a canonical
    request can never silently target a legacy/wrong deployment (the D10
    failure class: fresh nonce against an old app -> warm exact_hit with
    encode_calls=0).  Local-only: no Modal calls, no spend.  Exits 0=PASS /
    1=FAIL; the run batch aborts before submission on FAIL.
    """
    _row = lambda key, value: print(f"{key}={value}", flush=True)  # noqa: E731
    failures: list[str] = []
    state: dict = {}
    try:
        from comfymodal_runtime.registry_proof_store import deployed_state_path as _dsp
        state = json.loads(_dsp().read_text(encoding="utf-8"))
    except Exception:
        state = {}
    if not isinstance(state, dict) or not state:
        failures.append("deployed state unavailable (.deployed_state.json missing or empty)")

    _app = str(state.get("app_name") or "").strip()
    _identity = str(state.get("deployment_combined_hash") or "").strip()
    _class = str(state.get("class_name") or "").strip()
    _shape_fp = str(state.get("runtime_shape_fingerprint") or "").strip()
    _shape_recorded = int(state.get("runtime_shape_recorded") or 0)
    _cpu = int(state.get("cpu_request") or 0)
    _mem = int(state.get("memory_request") or 0)
    _base_cpu = int(state.get("baseline_cpu_request") or 0)
    _base_mem = int(state.get("baseline_memory_request") or 0)
    _state_atomic_profile = str(state.get("atomic_profile") or "").strip()
    _expected_atomic_profile = str(
        os.environ.get("COMFYMODAL_V2_ATOMIC_PROFILE", "") or ""
    ).strip()
    if _e19_profile_active():
        _expected_atomic_profile = E19_FINAL_COLD_LOADER_PROFILE_NAME

    _env_app = os.environ.get("COMFYMODAL_V2_APP_NAME", "").strip()
    _env_class = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "").strip()
    _env_cpu = os.environ.get("COMFYMODAL_V2_CPU_REQUEST", "").strip()
    _env_mem = os.environ.get("COMFYMODAL_V2_MEMORY_MB", "").strip()
    _env_base_cpu = os.environ.get("COMFYMODAL_V2_BASELINE_CPU_REQUEST", "").strip()
    _env_base_mem = os.environ.get("COMFYMODAL_V2_BASELINE_MEMORY_REQUEST", "").strip()
    _runs = os.environ.get("V2_BENCHMARK_RUNS", "").strip()

    # Planned runtime-shape fingerprint from THIS request environment.
    _planned_fp = ""
    try:
        from comfymodal_runtime.runtime_shape import runtime_shape_config
        _planned_fp = runtime_shape_config().runtime_shape_fingerprint
    except Exception:
        _planned_fp = ""

    # Nonce target-app resolution (fail closed; D10 guard).
    _nonce_target = ""
    if nonce:
        try:
            _nonce_target = _resolve_nonce_target_app()
        except Exception as exc:
            failures.append(f"nonce target app resolution failed: {exc}")

    # D1 proof coverage under the current deploy-frozen identity (mirrors the
    # prime path exactly: same workflow, same production-options normalization).
    _covered = False
    try:
        _workflow, _modal_options = _load_workflow()
        _opts = normalize_production_options(_modal_options)
        _covered = _registry_proof_store_covers(
            _workflow,
            modal_options=_modal_options,
            production_options=_opts if _opts.get("enabled") else None,
        )
    except Exception:
        _covered = False

    if not _app:
        failures.append("deployed app_name empty (identity not recorded)")
    if not _identity:
        failures.append("deployed deployment_combined_hash empty")
    if not _class:
        failures.append("deployed class_name empty")
    if not _deployment_state_atomic_profile_matches(
        state, _expected_atomic_profile
    ):
        failures.append(
            "deployed atomic profile mismatch: "
            f"requested={_expected_atomic_profile or '<unset>'} "
            f"deployed={_state_atomic_profile or '<missing>'}"
        )
    if _env_app != _app:
        failures.append(
            f"target app mismatch: requested={_env_app or '<unset>'} deployed={_app}"
        )
    if _env_class != _class:
        failures.append(
            f"target class mismatch: requested={_env_class or '<unset>'} deployed={_class}"
        )
    if not _shape_recorded or not _shape_fp:
        failures.append("deployed runtime-shape not recorded (deploy identity record predates shape fields)")
    elif not _planned_fp:
        failures.append("planned runtime-shape fingerprint unavailable")
    elif _planned_fp != _shape_fp:
        failures.append(f"runtime-shape fingerprint mismatch: planned={_planned_fp} deployed={_shape_fp}")
    if _env_cpu and str(_cpu) and _env_cpu != str(_cpu):
        failures.append(f"cpu mismatch: requested={_env_cpu} deployed={_cpu}")
    if _env_mem and str(_mem) and _env_mem != str(_mem):
        failures.append(f"memory mismatch: requested={_env_mem} deployed={_mem}")
    if _env_base_cpu and str(_base_cpu) and _env_base_cpu != str(_base_cpu):
        failures.append(f"baseline cpu mismatch: requested={_env_base_cpu} deployed={_base_cpu}")
    if _env_base_mem and str(_base_mem) and _env_base_mem != str(_base_mem):
        failures.append(f"baseline memory mismatch: requested={_env_base_mem} deployed={_base_mem}")
    if not _covered:
        failures.append("D1 registry-proof store does not cover the deployment/workflow")
    if nonce:
        if not _nonce_target:
            failures.append("nonce target app could not be resolved")
        elif _nonce_target != _app:
            failures.append(f"nonce target app {_nonce_target!r} != deployed app {_app!r}")
        if _runs and _runs != "1":
            failures.append(f"nonce measurement requires V2_BENCHMARK_RUNS=1, got {_runs!r}")

    _final = "PASS" if not failures else "FAIL"
    print("[v2.run_preflight]", flush=True)
    _row("TARGET_APP", _env_app or "<unset>")
    _row("TARGET_CLASS", _env_class or "<unset>")
    _row("TARGET_DEPLOYMENT", _identity[:24] if _identity else "<empty>")
    _row("TARGET_MATCH", "YES" if (_env_app and _env_app == _app) else "NO")
    _row(
        "ATOMIC_PROFILE",
        f"{_expected_atomic_profile or '<none>'} == deployed "
        f"{_state_atomic_profile or '<missing>'}",
    )
    _row(
        "CPU",
        f"{_env_cpu or '?'} == deployed {_cpu or '?'}",
    )
    _row(
        "MEMORY",
        f"{_env_mem or '?'} == deployed {_mem or '?'}",
    )
    _row(
        "BASELINE_CPU",
        f"{_env_base_cpu or '?'} == deployed {_base_cpu or '?'}",
    )
    _row(
        "BASELINE_MEMORY",
        f"{_env_base_mem or '?'} == deployed {_base_mem or '?'}",
    )
    _row("RUNTIME_FINGERPRINT", f"{_planned_fp or '?'} == deployed {_shape_fp or '?'}")
    _row("D1_PROOF_COVERS", str(_covered).lower())
    _row("RUN_COUNT", _runs or "<unset>")
    for _f in failures:
        print(f"failure={_f}", flush=True)
    _row("FINAL_REQUEST_PREFLIGHT", _final)
    return 0 if _final == "PASS" else 1


def _identity(result: dict[str, Any]) -> dict[str, Any]:
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("name") != "remote_method_entry":
            continue
        metadata = event.get("metadata", {})
        if isinstance(metadata, dict) and metadata.get("method_name") == "run_plan_stream":
            return {
                "app_name": metadata.get("app_name", ""),
                "class_name": metadata.get("class_name", ""),
                "method_name": metadata.get("method_name", ""),
                "gpu": metadata.get("gpu", ""),
                "cpu": metadata.get("cpu"),
                "memory_mb": metadata.get("memory_mb"),
                "fingerprint": metadata.get("fingerprint", ""),
                "runtime_shape": metadata.get("runtime_shape", {}),
                "runtime_shape_fingerprint": metadata.get(
                    "runtime_shape_fingerprint", ""
                ),
                "runtime_shape_label": metadata.get("runtime_shape_label"),
                "stored_snapshot_model_order": metadata.get(
                    "stored_snapshot_model_order"
                ),
                # Preserve the request-scoped cold-proof fields emitted by
                # remote_method_entry.  The variance validator must inspect
                # these values rather than treating their absence as a warm
                # run after identity extraction.
                "restore_count": metadata.get("restore_count"),
                "request_count": metadata.get("request_count"),
                "restored_instance_id": metadata.get("restored_instance_id", ""),
                "restore_session_id": metadata.get("restore_session_id", ""),
                "container_task_id": metadata.get("container_task_id", ""),
                "modal_container_id": metadata.get("modal_container_id", ""),
                "image_id": metadata.get("image_id", ""),
                "cloud": metadata.get("cloud", ""),
                "region": metadata.get("region", ""),
                "modal_input_id": metadata.get("modal_input_id", ""),
                "container_session_id": (
                    metadata.get("container_session_id")
                    or result.get("container_session_id", "")
                    or trace.get("container_session_id", "")
                ),
            }
    metadata = trace.get("metadata", {}) if isinstance(trace, dict) else {}
    return dict(metadata) if isinstance(metadata, dict) else {}



def _runtime_shape_guard(shape: dict[str, Any]) -> dict[str, Any]:
    def _baseline_int(env_name: str, fallback: int) -> int:
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            return fallback
        try:
            value = int(raw)
        except ValueError as exc:
            raise RuntimeError(f"{env_name}={raw!r} is not an integer") from exc
        if value <= 0:
            raise RuntimeError(f"{env_name}={raw!r} must be positive")
        return value

    baseline_cpu = _baseline_int("COMFYMODAL_V2_BASELINE_CPU_REQUEST", 16)
    baseline_memory = _baseline_int(
        "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST",
        int(shape["memory_request"]),
    )
    changed_axes: list[str] = []
    if shape["thread_policy"] != "TBASE":
        changed_axes.append("thread_policy")
    if shape["snapshot_model_order"] != "O0":
        changed_axes.append("snapshot_model_order")
    if int(shape["cpu_request"]) != baseline_cpu:
        changed_axes.append("cpu_request")
    if int(shape["memory_request"]) != baseline_memory:
        changed_axes.append("memory_request")
    raw_override = os.environ.get("COMFYMODAL_V2_ALLOW_MULTI_AXIS", "").strip().lower()
    allow_multi_axis = raw_override in {"1", "true", "yes", "on"}
    guard = {
        "changed_axes": changed_axes,
        "allow_multi_axis": allow_multi_axis,
        "baseline_cpu_request": baseline_cpu,
        "baseline_memory_request": baseline_memory,
    }
    if len(changed_axes) > 1 and not allow_multi_axis:
        raise RuntimeError(
            "C8 experiment changes multiple axes without "
            "COMFYMODAL_V2_ALLOW_MULTI_AXIS=1: "
            + ", ".join(changed_axes)
        )
    return guard


def _runtime_shape_observations(result: dict[str, Any]) -> list[dict[str, Any]]:
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    if not isinstance(events, list):
        return []
    return [
        event.get("metadata", {})
        for event in events
        if isinstance(event, dict)
        and event.get("name") == "runtime_shape_observed"
        and isinstance(event.get("metadata"), dict)
    ]


def _cpu_model_snapshot_enabled() -> bool:
    """Return True when COMFYMODAL_V2_CPU_MODEL_SNAPSHOT is enabled.

    Uses the shared ``env_flag`` semantics (``1``/``true``/``yes``/``on``).
    When disabled, the deployment never constructs a CPU model snapshot, so
    ``stored_snapshot_model_order`` is legitimately absent from the identity
    metadata and the C8 runtime-shape validator must not demand it.
    """
    return env_flag("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT")


def _validate_runtime_shape(
    result: dict[str, Any],
    identity: dict[str, Any],
) -> dict[str, Any]:
    expected = runtime_shape_config().identity_payload()
    guard = _runtime_shape_guard(expected)
    deployed = identity.get("runtime_shape")
    if not isinstance(deployed, dict):
        deployed = {}
    failures: list[str] = []
    for key in (
        "thread_policy",
        "snapshot_model_order",
        "cpu_request",
        "memory_request",
        "runtime_shape_fingerprint",
        "runtime_shape_label",
    ):
        if deployed.get(key) != expected.get(key):
            failures.append(
                f"deployed {key}={deployed.get(key)!r} "
                f"requested={expected.get(key)!r}"
            )
    if int(identity.get("cpu", -1) or -1) != int(expected["cpu_request"]):
        failures.append(
            f"resource cpu={identity.get('cpu')!r} requested={expected['cpu_request']!r}"
        )
    if int(identity.get("memory_mb", -1) or -1) != int(expected["memory_request"]):
        failures.append(
            "resource memory_mb="
            f"{identity.get('memory_mb')!r} requested={expected['memory_request']!r}"
        )
    if not identity.get("fingerprint"):
        failures.append("snapshot target fingerprint is missing")
    observations = _runtime_shape_observations(result)
    observed = observations[-1] if observations else {}
    if not observed:
        failures.append("runtime_shape_observed event is missing")
    elif observed.get("runtime_shape_fingerprint") != expected["runtime_shape_fingerprint"]:
        failures.append(
            "observed runtime_shape_fingerprint="
            f"{observed.get('runtime_shape_fingerprint')!r} "
            f"requested={expected['runtime_shape_fingerprint']!r}"
        )
    if expected["thread_policy"] == "TBASE":
        if observed.get("status") not in {"baseline_passthrough", "validated"}:
            failures.append(f"baseline thread status={observed.get('status')!r}")
    else:
        if observed.get("status") not in {"applied", "already_applied", "validated"}:
            failures.append(f"active thread status={observed.get('status')!r}")
        if observed.get("requested_vs_actual_match") is not True:
            failures.append("requested Torch thread counts do not match actual counts")
    stored_order = identity.get("stored_snapshot_model_order")
    if stored_order is None:
        trace = result.get("trace", {}) if isinstance(result, dict) else {}
        events = trace.get("events", []) if isinstance(trace, dict) else []
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict) or event.get("name") != "cpu_snapshot_models_ready":
                continue
            metadata = event.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("status") == "ok":
                stored_order = metadata.get("construction_order")
    # No-CPU-model-snapshot deployments (COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=0)
    # never construct a snapshot model order, so a None stored order is the
    # expected state and the artifact persists.  Exact order validation is
    # retained whenever snapshots are enabled OR any concrete order is
    # reported (an unexpected non-None order is never silently accepted).
    if _cpu_model_snapshot_enabled() or stored_order is not None:
        if stored_order != expected["snapshot_model_order"]:
            failures.append(
                f"stored snapshot order={stored_order!r} "
                f"deployed={expected['snapshot_model_order']!r}"
            )
    if failures:
        raise RuntimeError("C8 runtime-shape validation failed: " + "; ".join(failures))
    return {
        "requested": expected,
        "deployed": deployed,
        "observed": observed,
        "stored_snapshot_model_order": stored_order,
        "snapshot_target_fingerprint": identity.get("fingerprint", ""),
        "guard": guard,
        "construction_order_semantics": "model_construction_order_only",
    }


def _validate_remote_profile(result: dict[str, Any]) -> None:
    """Reject a production benchmark when the remote profile is not production."""
    requested_profile = os.environ.get("COMFYMODAL_V2_ENV_PROFILE", "").strip().lower()
    if requested_profile != "production":
        return

    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    trace_metadata = trace.get("metadata", {}) if isinstance(trace, dict) else {}
    request_origin = (
        trace_metadata.get("request_origin_info", {})
        if isinstance(trace_metadata, dict)
        else {}
    )
    remote_effective = (
        str(request_origin.get("env_profile", "")).strip().lower()
        if isinstance(request_origin, dict)
        else ""
    ) or "absent"
    if remote_effective != "production":
        raise RuntimeError(
            "V2 production profile mismatch:\n"
            "requested=production\n"
            f"remote_effective={remote_effective}\n"
            "The benchmark would bypass the CPU snapshot fast path."
        )


def _timing(
    result: dict[str, Any],
    wall_ms: float,
    *,
    command_start_unix_ms: int | None = None,
    response_received_unix_ns: int | None = None,
) -> dict[str, Any]:
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    deltas = trace.get("deltas_ms", {}) if isinstance(trace, dict) else {}
    derived = trace.get("derived_ms", {}) if isinstance(trace, dict) else {}
    restore = result.get("_restore_timing", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []

    def event_ns(name: str, *, method_name: str = "") -> int | None:
        for event in events:
            if not isinstance(event, dict) or event.get("name") != name:
                continue
            if method_name and event.get("metadata", {}).get("method_name") != method_name:
                continue
            value = event.get("wall_unix_ns")
            if isinstance(value, (int, float)):
                return int(value)
        return None

    def event_mono(name: str, *, phase: str = "") -> int | None:
        """First event's monotonic_ns (same-process duration helper)."""
        for event in events:
            if not isinstance(event, dict) or event.get("name") != name:
                continue
            if phase and event.get("phase") != phase:
                continue
            value = event.get("monotonic_ns")
            if isinstance(value, (int, float)):
                return int(value)
        return None

    def duration_ms(start_name: str, end_name: str) -> float | None:
        start = event_ns(start_name)
        end = event_ns(end_name)
        if start is None or end is None:
            return None
        return round((end - start) / 1_000_000.0, 3)

    validation_to_output_ms = duration_ms("prompt_validation_end", "output_collect_end")
    pre_sampler_ms = duration_ms("prompt_validation_end", "sampler_start")
    sampler_ms = duration_ms("sampler_start", "sampler_end")
    vae_decode_ms = duration_ms("vae_decode_start", "vae_decode_end")
    output_collection_ms = duration_ms("output_collect_start", "output_collect_end")
    local_submit = event_ns("modal_submit_start")
    remote_entry = event_ns("remote_method_entry", method_name="run_plan_stream")
    submit2entry_ms = (
        round((remote_entry - local_submit) / 1_000_000.0, 3)
        if local_submit is not None and remote_entry is not None
        else None
    )
    handle_lookup_ms = duration_ms("modal_handle_lookup_start", "modal_handle_lookup_end")
    submission_to_first_remote_event_ms = duration_ms(
        "modal_submission_attempt", "modal_first_remote_event",
    )
    command_to_response_ms = None
    if command_start_unix_ms is not None and response_received_unix_ns is not None:
        command_to_response_ms = round(
            (response_received_unix_ns - int(command_start_unix_ms) * 1_000_000) / 1_000_000.0,
            1,
        )
    # ── Exact cross-process platform-entry reconciliation ────────────
    # Every interval below is computed from RAW wall timestamps that exist in
    # the trace events / restore timing — nothing is pushed into a generic
    # residual.  Local boundary = local submission attempt (wall); remote
    # boundaries = restore _restore_timing wall fields + method-entry event.
    _restore_timing_dict = restore if isinstance(restore, dict) else {}
    _remote_resume_ns = _num(_restore_timing_dict.get("remote_python_resume_wall_unix_ns"))
    _restore_start_ns = _num(_restore_timing_dict.get("restore_method_start_wall_unix_ns"))
    _restore_end_ns = _num(_restore_timing_dict.get("restore_method_end_wall_unix_ns"))
    _local_submit_ns = event_ns("modal_submission_attempt") or event_ns("modal_submit_start")
    _method_entry_ns = (
        event_ns("run_plan_method_first_line")
        or event_ns("remote_method_entry", method_name="run_plan_stream")
    )
    _first_remote_ns = event_ns("modal_first_remote_event")
    _final_ns = event_ns("final_result_received")

    def _wall_interval(start: Any, end: Any) -> float | None:
        if (
            start is None or end is None
            or not isinstance(start, (int, float)) or not isinstance(end, (int, float))
        ):
            return None
        _delta = int(end) - int(start)
        if _delta < 0:
            return None
        return round(_delta / 1_000_000.0, 3)

    submission_to_remote_python_resume_ms = _wall_interval(
        _local_submit_ns, _remote_resume_ns
    )
    remote_python_resume_to_restore_start_ms = _wall_interval(
        _remote_resume_ns, _restore_start_ns
    )
    restore_to_method_entry_ms = _wall_interval(_restore_end_ns, _method_entry_ns)
    method_entry_to_first_remote_event_ms = _wall_interval(
        _method_entry_ns, _first_remote_ns
    )
    first_remote_event_to_final_result_ms = _wall_interval(
        _first_remote_ns, _final_ns
    )
    # ── Diagnostic UNET transfer stages (same-process monotonic) ──────
    _ea_sched_mono = event_mono("unet_early_activation_scheduled")
    _ea_load_start_mono = event_mono("unet_early_activation_load_start")
    _ea_load_end_mono = event_mono("unet_early_activation_load_end")
    _transfer_queue_delay_ms = None
    if (
        _ea_sched_mono is not None and _ea_load_start_mono is not None
        and _ea_load_start_mono >= _ea_sched_mono
    ):
        _transfer_queue_delay_ms = round(
            (_ea_load_start_mono - _ea_sched_mono) / 1_000_000.0, 3
        )
    _synchronized_transfer_ms = None
    if (
        _ea_load_start_mono is not None and _ea_load_end_mono is not None
        and _ea_load_end_mono >= _ea_load_start_mono
    ):
        _synchronized_transfer_ms = round(
            (_ea_load_end_mono - _ea_load_start_mono) / 1_000_000.0, 3
        )
    # Quiesce wait (quiesced-transfer A/B arm B): emitted only when the
    # request-scoped diagnostic is enabled.
    _quiesce_wait_ms = None
    _quiesce_start_mono = event_mono("unet_quiesce_wait_start")
    _quiesce_end_mono = event_mono("unet_quiesce_wait_end")
    if (
        _quiesce_start_mono is not None and _quiesce_end_mono is not None
        and _quiesce_end_mono >= _quiesce_start_mono
    ):
        _quiesce_wait_ms = round(
            (_quiesce_end_mono - _quiesce_start_mono) / 1_000_000.0, 3
        )
    # Graph/prefill activity: PromptExecutor invoke → sampler lane wait
    # (the graph's own work before the sampler blocks on the mutation lane).
    _graph_activity_ms = None
    _invoke_mono = event_mono("prompt_executor_invoke_start")
    _lane_wait_mono = event_mono("sampler_lane_wait_start")
    if (
        _invoke_mono is not None and _lane_wait_mono is not None
        and _lane_wait_mono >= _invoke_mono
    ):
        _graph_activity_ms = round(
            (_lane_wait_mono - _invoke_mono) / 1_000_000.0, 3
        )
    # Sampler lane wait (authoritative metadata from the boundary events).
    _sampler_lane_wait_ms = None
    _sl_meta = None
    for _event in events:
        if (
            isinstance(_event, dict)
            and _event.get("name") == "sampler_lane_wait_end"
        ):
            _sl_meta = _event.get("metadata", {}) if isinstance(_event.get("metadata"), dict) else {}
            break
    if isinstance(_sl_meta, dict) and isinstance(_sl_meta.get("wait_ms"), (int, float)):
        _sampler_lane_wait_ms = round(float(_sl_meta["wait_ms"]), 3)
    # Quiesced transfer sampler record (arm B; absent otherwise).
    _quiesced_transfer = None
    for _event in events:
        if isinstance(_event, dict) and _event.get("name") == "unet_quiesced_transfer":
            _qt_meta = _event.get("metadata", {})
            if isinstance(_qt_meta, dict):
                _quiesced_transfer = _qt_meta
            break
    # Forward local_timing from result (copied/safe block)
    _local_timing = result.get("local_timing", {}) if isinstance(result, dict) else {}
    if not isinstance(_local_timing, dict):
        _local_timing = {}
    # Full restore breakdown: every restore_timing key ending in ``_ms``.
    restore_breakdown: dict[str, Any] = {}
    if isinstance(restore, dict):
        for _rk, _rv in restore.items():
            if isinstance(_rk, str) and _rk.endswith("_ms") and isinstance(_rv, (int, float)):
                restore_breakdown[_rk] = round(float(_rv), 3)
    # Worker-variance fields from the ``unet_activation_worker_variance`` event.
    _ea_total_ms = None
    _queue_delay_ms = None
    _cpu_snapshot_wait_ms = None
    _dtype_prep_ms = None
    _post_load_bb_ms = None
    for _event in events:
        if not isinstance(_event, dict) or _event.get("name") != "unet_activation_worker_variance":
            continue
        _meta = _event.get("metadata", {}) if isinstance(_event.get("metadata"), dict) else {}
        if isinstance(_meta.get("early_activation_total_ms"), (int, float)):
            _ea_total_ms = float(_meta["early_activation_total_ms"])
        if isinstance(_meta.get("queue_delay_ms"), (int, float)):
            _queue_delay_ms = float(_meta["queue_delay_ms"])
        if isinstance(_meta.get("cpu_snapshot_wait_ms"), (int, float)):
            _cpu_snapshot_wait_ms = float(_meta["cpu_snapshot_wait_ms"])
        _dtype_prep = _meta.get("dtype_layout_preparation")
        if isinstance(_dtype_prep, dict) and isinstance(_dtype_prep.get("wall_ms"), (int, float)):
            _dtype_prep_ms = float(_dtype_prep["wall_ms"])
        _post_bb = _meta.get("post_load_bookkeeping")
        if isinstance(_post_bb, dict) and isinstance(_post_bb.get("wall_ms"), (int, float)):
            _post_load_bb_ms = float(_post_bb["wall_ms"])
        break
    return {
        "wall_ms": round(wall_ms, 1),
        "handle_lookup_ms": handle_lookup_ms,
        "submission_to_first_remote_event_ms": submission_to_first_remote_event_ms,
        "command_to_response_ms": command_to_response_ms,
        "submit2entry_ms": deltas.get("modal_submit_to_entry_ms", submit2entry_ms),
        "t3b_to_t8_ms": deltas.get("t3b_to_t8", derived.get("t3b_to_t8_ms", validation_to_output_ms)),
        "restore_total_ms": restore.get("restore_total_ms") if isinstance(restore, dict) else None,
        "pre_sampler_ms": derived.get("prompt_start_to_sampler_start_ms", pre_sampler_ms),
        "sampler_ms": derived.get("sampler_ms", sampler_ms),
        "vae_decode_ms": derived.get("vae_decode_ms", deltas.get("vae_decode_ms", vae_decode_ms)),
        "output_collection_ms": deltas.get("output_collection_total_ms", output_collection_ms),
        "snapshot_callback_age_at_restore_ms": restore.get("snapshot_callback_age_at_restore_ms") if isinstance(restore, dict) else result.get("snapshot_callback_age_at_restore_ms"),
        "snapshot_callback_to_command_start_ms": result.get("snapshot_callback_to_command_start_ms"),
        # Prefer the truthfully-named field; fall back to the legacy name
        # (identical semantics: command_start -> python resume).
        "command_start_to_restore_start_ms": (
            result.get("command_start_to_python_resume_ms")
            if result.get("command_start_to_python_resume_ms") is not None
            else result.get("command_start_to_restore_start_ms")
        ),
        "local_timing": _local_timing,
        "restore_breakdown": restore_breakdown,
        "early_activation_total_ms": _ea_total_ms,
        "queue_delay_ms": _queue_delay_ms,
        "cpu_snapshot_wait_ms": _cpu_snapshot_wait_ms,
        "dtype_layout_preparation_ms": _dtype_prep_ms,
        "post_load_bookkeeping_ms": _post_load_bb_ms,
        # Exact cross-process platform-entry reconciliation (raw timestamps).
        "submission_to_remote_python_resume_ms": submission_to_remote_python_resume_ms,
        "remote_python_resume_to_restore_start_ms": remote_python_resume_to_restore_start_ms,
        "restore_to_method_entry_ms": restore_to_method_entry_ms,
        "method_entry_to_first_remote_event_ms": method_entry_to_first_remote_event_ms,
        "first_remote_event_to_final_result_ms": first_remote_event_to_final_result_ms,
        # Diagnostic UNET transfer stages.
        "transfer_queue_delay_ms": _transfer_queue_delay_ms,
        "synchronized_transfer_ms": _synchronized_transfer_ms,
        "quiesce_wait_ms": _quiesce_wait_ms,
        "graph_activity_ms": _graph_activity_ms,
        "sampler_lane_wait_ms": _sampler_lane_wait_ms,
        "quiesced_transfer": _quiesced_transfer,
    }


def _capture_ts() -> tuple[int, int]:
    """Return (wall_unix_ns, monotonic_ns) snapshot.

    Same-process duration calculations use monotonic_ns exclusively.
    Cross-process correlation uses wall_unix_ns only.
    """
    return (int(time.time() * 1_000_000_000), time.monotonic_ns())


# ── Inter-run intentional cooldown instrumentation (D1 local-dispatch) ──
# The deliberate cold-spacing sleep between benchmark runs is bracketed with
# wall+monotonic stamps and recorded explicitly so command→response accounting
# can attribute it (goal 4: separate explicit cooldown metric).  The wait
# happens BETWEEN runs — it always precedes the next run's
# benchmark_iteration_selected stamp, so it is NEVER inside a measured
# trigger→submission window.
_COLD_WAITS: list[dict[str, Any]] = []


async def _intentional_cold_wait(seconds: float) -> dict[str, Any]:
    """Bracket one deliberate inter-run cooldown sleep; record + print it.

    Uses `asyncio.sleep` internally (not time.sleep) so the event loop stays
    responsive and tests can patch `tools.benchmark_v2_direct.asyncio.sleep`.
    Returns the record; appends it to _COLD_WAITS.
    """
    _start = _capture_ts()
    await asyncio.sleep(seconds)
    _end = _capture_ts()
    _waited_ms = round((_end[1] - _start[1]) / 1_000_000.0, 3)
    _record = {
        "start_wall_unix_ns": _start[0],
        "end_wall_unix_ns": _end[0],
        "start_mono_ns": _start[1],
        "end_mono_ns": _end[1],
        "requested_seconds": float(seconds),
        "waited_mono_ms": _waited_ms,
    }
    _COLD_WAITS.append(_record)
    print(
        f"[v2.harness] intentional_cold_wait start_wall_unix_ns={_start[0]} "
        f"start_mono_ns={_start[1]} end_wall_unix_ns={_end[0]} "
        f"end_mono_ns={_end[1]} requested_seconds={float(seconds)} "
        f"waited_mono_ms={_waited_ms}",
        flush=True,
    )
    return _record


# ═══════════════════════════════════════════════════════════════════════════
# Modal snapshot-restore-begin boundary ingestion (instrumentation ONLY)
#
# The Modal platform boundary "Restoring Function from memory snapshot" (the
# scheduler handing the restored container to the not-yet-resumed Python
# process) is NOT visible in-process — it is only fetchable via the Modal app
# log.  These helpers resolve it (result-carried value first, else a Modal app
# log tail) and rebuild the run's waterfall with it.  Every path degrades
# gracefully when the boundary or log fetch is unavailable; no runtime
# behavior changes.
# ═══════════════════════════════════════════════════════════════════════════


def _await_async_helper(coro_factory: Any) -> Any:
    """Run an async helper to completion from a possibly-async context.

    Uses ``asyncio.run`` when no loop is running; otherwise executes the
    coroutine on its own fresh loop in a worker thread so the caller's loop is
    never blocked by itself.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
        return _pool.submit(asyncio.run, coro_factory()).result()


async def _fetch_modal_restore_begin_logs_async(
    app_name: str,
    *,
    max_lines: int = 20000,
    since: Any = None,
    until: Any = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Tail the Modal app log for the snapshot-restore-begin platform line.

    Mirrors ``tools/fetch_matrix_stage_lines.py``: reads the active workspace
    credentials from ``ROOT/.modal_workspaces.json``, resolves the app
    identifier, and tails the app log.  Returns structured records as
    ``[{"timestamp": <epoch seconds float>, "message": str, "task_id": str}]``.

    Raises on any failure (missing credentials file, import, resolve, tail,
    or timeout) — callers must treat a raise as "boundary unavailable".
    """
    if not WORKSPACES_PATH.is_file():
        raise FileNotFoundError(f"workspace credentials not found: {WORKSPACES_PATH}")
    _ws = json.loads(WORKSPACES_PATH.read_text(encoding="utf-8"))
    _aid = _ws.get("active_workspace_id")
    _entry = next(
        (w for w in _ws.get("workspaces", []) if w.get("id") == _aid),
        None,
    )
    if _entry is None or not _entry.get("token_id") or not _entry.get("token_secret"):
        raise RuntimeError("active Modal workspace has no credentials")

    import modal  # noqa: F401, PLC0415  (lazy — module imports without Modal)
    from modal.cli.app import resolve_app_identifier  # noqa: PLC0415
    from modal._logs import tail_logs  # noqa: PLC0415
    from modal.client import _Client  # noqa: PLC0415

    client = await _Client.from_credentials(_entry["token_id"], _entry["token_secret"])
    app_id, _, _ = await resolve_app_identifier(app_name, None, client)

    async def _collect() -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        async for batch in tail_logs(
            client, app_id, max_lines, since=since, until=until,
        ):
            for item in batch.items:
                ts = getattr(item, "timestamp", None)
                if ts is None:
                    continue
                raw = getattr(item, "data", b"")
                text = raw if isinstance(raw, str) else (raw or b"").decode("utf-8", "replace")
                records.append({
                    "timestamp": float(ts),
                    "message": text,
                    "task_id": str(getattr(item, "task_id", "") or ""),
                })
        return records

    return await asyncio.wait_for(_collect(), timeout=timeout)


def _result_app_name(result: Any) -> str:
    """Best-effort app name from the result identity / trace metadata."""
    if not isinstance(result, dict):
        return ""
    identity = result.get("identity")
    if isinstance(identity, dict) and identity.get("app_name"):
        return str(identity["app_name"])
    trace = result.get("trace")
    if isinstance(trace, dict):
        metadata = trace.get("metadata")
        if isinstance(metadata, dict) and metadata.get("app_name"):
            return str(metadata["app_name"])
    return ""


def _result_task_identity(result: Any) -> str:
    """Run task identity: prefer modal_task_id / container_task_id.

    Read from ``result["identity"]`` first, then trace metadata.
    """
    if not isinstance(result, dict):
        return ""
    identity = result.get("identity")
    if isinstance(identity, dict):
        for key in ("modal_task_id", "container_task_id"):
            value = identity.get(key)
            if value:
                return str(value)
    trace = result.get("trace")
    if isinstance(trace, dict):
        metadata = trace.get("metadata")
        if isinstance(metadata, dict):
            for key in ("modal_task_id", "container_task_id"):
                value = metadata.get(key)
                if value:
                    return str(value)
    return ""


def resolve_modal_restore_begin(
    result: Any,
    timing: Any = None,
    *,
    log_lines: Any = None,
    task_id: str = "",
    window_start_unix_ns: int | None = None,
    window_end_unix_ns: int | None = None,
) -> int | None:
    """Resolve the Modal snapshot-restore-begin boundary (ns) for one run.

    1. ``extract_restore_begin_from_result`` first — no log fetch when the
       value is already carried in the result/timing dicts.
    2. When *log_lines* is ``None``, tail the Modal app log for the platform
       ``Restoring Function from memory snapshot`` line (lazy Modal import via
       ``_fetch_modal_restore_begin_logs_async``; on ANY failure print
       ``modal_restore_begin_unavailable: log fetch failed`` and return
       ``None``).
    3. Otherwise parse *log_lines* via ``parse_modal_restore_begin`` with the
       run's task identity (prefer the result's ``modal_task_id`` /
       ``container_task_id``) and the caller-supplied wall window.

    Always returns ``None`` when the boundary is unavailable — never raises.
    """
    value = extract_restore_begin_from_result(result, timing)
    if value is not None:
        return int(value)
    if log_lines is None:
        app_name = _result_app_name(result) or os.environ.get(
            "COMFYMODAL_V2_APP_NAME", ""
        )
        try:
            log_lines = _await_async_helper(
                lambda: _fetch_modal_restore_begin_logs_async(app_name)
            )
        except Exception as exc:  # noqa: BLE001
            print("modal_restore_begin_unavailable: log fetch failed", flush=True)
            return None
    if not task_id:
        task_id = _result_task_identity(result)
    parsed = parse_modal_restore_begin(
        log_lines,
        task_id=task_id,
        window_start_unix_ns=window_start_unix_ns,
        window_end_unix_ns=window_end_unix_ns,
    )
    return parsed["modal_restore_begin_wall_unix_ns"]


def reconcile_waterfall_local(
    result: dict[str, Any],
    timing: Any = None,
    *,
    command_start_unix_ms: int | None = None,
    response_received_unix_ns: int | None = None,
    wall_ms: float | None = None,
    log_lines: Any = None,
    task_id: str = "",
    run_label: str = "",
    existing_waterfall: Any = None,
) -> dict[str, Any] | None:
    """Rebuild the run's waterfall with the Modal restore-begin boundary.

    Instrumentation/reporting ONLY.  Resolves the restore-begin boundary
    (result dicts first, else the Modal app log via
    ``resolve_modal_restore_begin``), rebuilds the waterfall with
    ``build_waterfall`` using the FINAL result (merged host trace + final
    ``local_timing``) plus the actual host response/caller-return boundary,
    stores ``result["waterfall_local"]`` (the full host-reconciled report the
    console strongly prefers), and prints a reconciliation block including an
    OLD-vs-NEW comparison against *existing_waterfall* (the remote-built
    waterfall).

    A remote raw artifact marked ``partial_waterfall=True`` NEVER blocks the
    host rebuild: when the existing ``result["waterfall"]`` is partial, it is
    replaced with the host-rebuilt full report (the remote partial cannot be
    the final valid report).  Every failure mode degrades gracefully — the
    run path is never affected.
    """
    try:
        import inspect  # noqa: PLC0415
        _params = inspect.signature(build_waterfall).parameters
        if "modal_restore_begin_wall_unix_ns" not in _params:
            return None
    except (TypeError, ValueError):
        return None
    window_start_ns = (
        int(command_start_unix_ms) * 1_000_000
        if command_start_unix_ms is not None else None
    )
    window_end_ns = (
        int(response_received_unix_ns)
        if response_received_unix_ns is not None else None
    )
    restore_begin = resolve_modal_restore_begin(
        result,
        timing,
        log_lines=log_lines,
        task_id=task_id,
        window_start_unix_ns=window_start_ns,
        window_end_unix_ns=window_end_ns,
    )
    try:
        rebuilt = build_waterfall(
            result=result,
            timing=timing,
            wall_ms=wall_ms,
            command_start_unix_ms=command_start_unix_ms,
            response_received_unix_ns=response_received_unix_ns,
            run_label=run_label,
            modal_restore_begin_wall_unix_ns=restore_begin,
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"WATERFALL RECONCILIATION (local rebuild) failed: {type(exc).__name__}",
            flush=True,
        )
        return None
    rebuilt_dict = waterfall_to_dict(rebuilt)
    # Cross-process clock-skew correction (measurement only; never gates app
    # behavior): container wall clocks can drift ahead of the host clock by
    # ~100 ms+, inflating the container-side accounted window by exactly the
    # skew.  When the host's result-receipt wall stamp is EARLIER than the
    # container's result-emit stamp, the negative difference is that skew.
    # Removing it from the residual restores the reconciliation to the true
    # window; the correction is recorded so acceptance blocks can attribute
    # the delta to platform clock variance instead of app behavior.
    try:
        _lt = (timing or {}).get("local_timing") if isinstance(timing, dict) else None
        if isinstance(_lt, dict):
            _emit = _lt.get("remote_result_emit_wall_unix_ns")
            _receipt = _lt.get("local_result_received_wall_ns")
            if isinstance(_emit, (int, float)) and isinstance(_receipt, (int, float)):
                _skew_ms = round((_receipt - _emit) / 1_000_000, 6)
                if _skew_ms < 0:
                    _skew_corr = round(abs(_skew_ms), 3)
                    _res = rebuilt_dict.get("residual_ms")
                    _tol = rebuilt_dict.get("tolerance_ms")
                    if isinstance(_res, (int, float)) and _tol is not None:
                        _corr_res = round(_res + _skew_corr, 3)
                        if abs(_corr_res) <= float(_tol):
                            rebuilt_dict["residual_ms"] = _corr_res
                            rebuilt_dict["reconciliation_ms"] = _corr_res
                            rebuilt_dict["reconciliation_status"] = "OK"
                            rebuilt_dict["clock_skew_correction_ms"] = _skew_corr
                            _warns = rebuilt_dict.get("warnings")
                            if isinstance(_warns, list):
                                _warns.append(
                                    f"clock skew correction {_skew_corr}ms applied "
                                    "(container clock ahead of host; residual restored)"
                                )
    except Exception:  # noqa: BLE001
        pass
    if isinstance(result, dict):
        result["waterfall_local"] = rebuilt_dict
        # A remote raw artifact marked partial must never be the final valid
        # report: the host rebuild replaces it in place when it is partial.
        _existing = result.get("waterfall")
        if (
            isinstance(_existing, dict)
            and _existing.get("partial_waterfall") is True
        ):
            result["waterfall"] = rebuilt_dict
            print(
                "WATERFALL RECONCILIATION (local rebuild) replaced remote "
                "PARTIAL report with the full host-reconciled report",
                flush=True,
            )

    def _num(value: Any) -> float | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _fmt(value: float | None) -> str:
        return f"{value:.1f}" if value is not None else "-"

    total = _num(rebuilt.total_ms)
    accounted = _num(rebuilt.accounted_ms)
    residual = _num(rebuilt.residual_ms)
    if residual is None:
        # Fall back to the accounted/reconciliation fields when the rebuilt
        # report predates residual_ms.
        residual = _num(rebuilt.reconciliation_ms)
    residual_pct = _num(rebuilt.residual_pct)
    if residual_pct is None and residual is not None and total and total > 0:
        residual_pct = residual / total * 100.0
    status = (
        rebuilt.reconciliation_status
        or (
            "OK"
            if (
                rebuilt.reconciliation_ms is not None
                and rebuilt.tolerance_ms is not None
                and abs(rebuilt.reconciliation_ms) <= rebuilt.tolerance_ms
            )
            else "EXCEEDS_TOLERANCE"
        )
    )
    controllable = _num(rebuilt.controllable_wall_ms)
    platform = _num(rebuilt.platform_wall_ms)
    unavailable = (
        "yes"
        if "modal_restore_begin_unavailable" in (rebuilt.boundary_flags or ())
        else "no"
    )

    print("WATERFALL RECONCILIATION (local rebuild)", flush=True)
    print(f"  command_to_response_ms            {_fmt(total)}", flush=True)
    print(f"  top_level_accounted_ms            {_fmt(accounted)}", flush=True)
    print(f"  global_residual_ms                {_fmt(residual)}", flush=True)
    print(f"  global_residual_pct               {_fmt(residual_pct)}", flush=True)
    print(f"  reconciliation_status             {status}", flush=True)
    print(f"  controllable_application_wall_ms  {_fmt(controllable)}", flush=True)
    print(f"  platform_wall_ms                  {_fmt(platform)}", flush=True)
    print(f"  modal_restore_begin_unavailable   {unavailable}", flush=True)

    old_accounted: float | None = None
    old_residual: float | None = None
    if isinstance(existing_waterfall, dict):
        old_accounted = _num(existing_waterfall.get("accounted_ms"))
        old_residual = _num(existing_waterfall.get("residual_ms"))
        if old_residual is None:
            old_residual = _num(existing_waterfall.get("reconciliation_ms"))
    print(
        "  OLD vs NEW accounted_ms %s -> %s | residual_ms %s -> %s" % (
            _fmt(old_accounted),
            _fmt(accounted),
            _fmt(old_residual),
            _fmt(residual),
        ),
        flush=True,
    )
    return rebuilt_dict


# ═══════════════════════════════════════════════════════════════════════════
# Full trace bundle download handoff
# ═══════════════════════════════════════════════════════════════════════════


def _find_in_dir(directory: Path, pattern: str) -> Path | None:
    """Find first file matching *pattern* in *directory* (recursive)."""
    matches = list(directory.rglob(pattern))
    return matches[0] if matches else None


async def _run_downloader_cli(
    *,
    volume_name: str,
    remote_bundle_path: str,
    bundle_sha256: str,
    trace_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Invoke ``tools/download_v2_full_trace.py`` via subprocess.

    The CLI outputs 6 ``KEY=VALUE`` lines on success.  This function parses
    those lines, discovers additional file paths inside the extract directory,
    times the operation, and returns a full metadata dict with all required
    keys for ``full_trace_download.json``.

    Raises ``RuntimeError`` on any failure (CLI not found, nonzero exit,
    timeout, or parse error).
    """
    downloader_path = ROOT / "tools" / "download_v2_full_trace.py"
    if not downloader_path.is_file():
        raise RuntimeError(
            f"Trace downloader not found at {downloader_path}"
        )

    t0 = time.perf_counter()

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(downloader_path),
            "--volume", str(volume_name),
            "--remote-path", str(remote_bundle_path),
            "--sha256", str(bundle_sha256),
            "--trace-id", str(trace_id),
            "--output-dir", str(output_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=120.0,
        )
    except asyncio.TimeoutError:
        raise RuntimeError("Trace downloader timed out after 120s")
    except Exception as exc:
        raise RuntimeError(f"Trace downloader subprocess failed: {exc}") from exc

    download_ms = (time.perf_counter() - t0) * 1000.0

    if proc.returncode != 0:
        stderr_text = (
            stderr_bytes.decode("utf-8", errors="replace")[:500]
            if stderr_bytes else ""
        )
        raise RuntimeError(
            f"Trace downloader exited code={proc.returncode}: {stderr_text}"
        )

    # Parse the 6 FULL_TRACE_* KEY=VALUE output lines from the downloader CLI.
    # Keys are: FULL_TRACE_BUNDLE, FULL_TRACE_REPORT, FULL_TRACE_VIZTRACER,
    #           FULL_TRACE_TORCH, FULL_TRACE_MANIFEST, FULL_TRACE_EXTRACT_DIR
    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    parsed: dict[str, str] = {}
    for line in stdout_text.strip().splitlines():
        line = line.strip()
        if "=" in line:
            k, _, v = line.partition("=")
            parsed[k.strip()] = v.strip()

    required_keys = {
        "FULL_TRACE_BUNDLE",
        "FULL_TRACE_REPORT",
        "FULL_TRACE_VIZTRACER",
        "FULL_TRACE_TORCH",
        "FULL_TRACE_MANIFEST",
        "FULL_TRACE_EXTRACT_DIR",
    }
    missing_keys = sorted(key for key in required_keys if key not in parsed)
    if missing_keys:
        raise RuntimeError(
            "Trace downloader output missing keys: " + ", ".join(missing_keys)
        )

    # Extract the known keys, then map to the required metadata schema
    extract_dir = Path(parsed.get("FULL_TRACE_EXTRACT_DIR", str(output_dir / f"full_trace_{trace_id}")))
    torch_val = parsed.get("FULL_TRACE_TORCH", "")
    if torch_val.lower() == "absent":
        torch_trace_path_val = "absent"
    else:
        torch_trace_path_val = torch_val

    meta: dict[str, Any] = {
        "trace_id": trace_id,
        "remote_bundle_path": remote_bundle_path,
        "local_bundle_path": parsed.get("FULL_TRACE_BUNDLE", ""),
        "extract_dir": str(extract_dir),
        "bundle_sha256": bundle_sha256,
        "verified": True,
        "report_path": parsed.get("FULL_TRACE_REPORT", ""),
        "viztracer_path": parsed.get("FULL_TRACE_VIZTRACER", ""),
        "torch_trace_path": torch_trace_path_val,
        "manifest_path": parsed.get("FULL_TRACE_MANIFEST", ""),
        "download_ms": round(download_ms, 1),
    }
    return meta


async def _handle_full_trace_artifact(
    result: dict[str, Any],
    output_dir: Path,
    workspace: dict[str, Any],
    transport: ModalTransport,
    *,
    _test_trace_downloader: Any = None,
) -> dict[str, Any] | None:
    """Handle ``full_trace_artifact`` from a remote result.

    Descriptor contract (the artifact dict):
      - ``status == 'ready'`` plus ``volume_name``, ``remote_bundle_path``,
        ``bundle_sha256``, ``trace_id`` → invoke the downloader exactly once,
        write ``full_trace_download.json`` beside the run file.
      - ``status == 'error'`` with ``error_type`` and optional ``error`` →
        raise ``RuntimeError`` with a sanitised message; the caller is
        expected to preserve the run file.
      - Absent artifact (no ``full_trace_artifact`` key or non-dict value)
        → return ``None``, no-op.
      - Unknown status → treated as absent (no-op).

    The caller **must** write ``run_<index>.json`` to disk *before* calling
    this function.

    Raises ``RuntimeError`` on error artifacts and on any download /
    verification / extraction / CLI failure.
    """
    full_trace_artifact = (
        result.get("full_trace_artifact")
        if isinstance(result, dict)
        else None
    )
    if not isinstance(full_trace_artifact, dict):
        return None  # absent

    status = full_trace_artifact.get("status", "")

    # ── Error artifact ──────────────────────────────────────────────────
    if status == "error":
        error_type = str(full_trace_artifact.get("error_type", "unknown_error"))[:100]
        error_msg = str(full_trace_artifact.get("error", ""))[:200]
        sanitized = (
            f"({error_type}) {error_msg}"
            if error_msg
            else f"({error_type})"
        )
        raise RuntimeError(f"Trace bundle error: {sanitized}")

    # ── Unknown status — treat as absent ────────────────────────────────
    if status != "ready":
        return None

    # ── Ready artifact — validate required fields ───────────────────────
    volume_name = str(full_trace_artifact.get("volume_name", ""))
    remote_bundle_path = str(full_trace_artifact.get("remote_bundle_path", ""))
    bundle_sha256 = str(full_trace_artifact.get("bundle_sha256", ""))
    trace_id = str(full_trace_artifact.get("trace_id", ""))

    if not all([volume_name, remote_bundle_path, bundle_sha256, trace_id]):
        raise RuntimeError(
            "Trace bundle error: ready artifact missing required fields "
            "(volume_name, remote_bundle_path, bundle_sha256, trace_id)"
        )

    # ── Invoke downloader exactly once ─────────────────────────────────
    if _test_trace_downloader is not None:
        download_meta = await _test_trace_downloader(
            volume_name=volume_name,
            remote_bundle_path=remote_bundle_path,
            bundle_sha256=bundle_sha256,
            trace_id=trace_id,
            output_dir=output_dir,
            workspace=workspace,
            transport=transport,
        )
    else:
        download_meta = await _run_downloader_cli(
            volume_name=volume_name,
            remote_bundle_path=remote_bundle_path,
            bundle_sha256=bundle_sha256,
            trace_id=trace_id,
            output_dir=output_dir,
        )

    if not isinstance(download_meta, dict):
        raise RuntimeError("Trace downloader returned invalid metadata")
    required_meta_keys = {
        "trace_id",
        "remote_bundle_path",
        "local_bundle_path",
        "extract_dir",
        "bundle_sha256",
        "verified",
        "report_path",
        "viztracer_path",
        "torch_trace_path",
        "manifest_path",
        "download_ms",
    }
    missing_meta_keys = sorted(required_meta_keys - set(download_meta))
    if missing_meta_keys:
        raise RuntimeError(
            "Trace downloader metadata missing keys: "
            + ", ".join(missing_meta_keys)
        )

    # Write download metadata beside run file
    (output_dir / "full_trace_download.json").write_text(
        json.dumps(download_meta, default=str, indent=2), encoding="utf-8",
    )
    return download_meta


def _merge_deferred_commit_trace_events(result: dict[str, Any], runtime_trace: Any) -> None:
    """Merge deferred-commit trace events into the result trace.

    The transport drain emits ``deferred_commit_start``/``deferred_commit_end``
    onto the local *runtime_trace* AFTER execute_plan returned (post-result,
    post-yield).  The result trace is a serialized snapshot taken before that,
    so re-merge those events here — additively and idempotently — so the
    structured artifact carries the deferred persistence evidence for host
    reconciliation.  Never alters the result/output descriptor semantics and
    never adds their duration to caller-visible stages.
    """
    if not isinstance(result, dict) or not isinstance(result.get("trace"), dict):
        return
    result_trace = result["trace"]
    if not isinstance(result_trace.get("events"), list):
        return
    existing = result_trace["events"]
    existing_keys = {
        (str(evt.get("name", "")), int(evt.get("wall_unix_ns", 0)), int(evt.get("monotonic_ns", 0)))
        for evt in existing
        if isinstance(evt, dict)
    }
    for evt in getattr(runtime_trace, "events", ()):
        if getattr(evt, "name", "") not in ("deferred_commit_start", "deferred_commit_end"):
            continue
        try:
            serialized = evt.to_dict()
        except Exception:
            continue
        key = (
            str(serialized.get("name", "")),
            int(serialized.get("wall_unix_ns", 0)),
            int(serialized.get("monotonic_ns", 0)),
        )
        if key not in existing_keys:
            existing.append(serialized)
            existing_keys.add(key)


# ── Host-side provenance re-emission (RUN-1 gate) ─────────────────────────
# Remote (Modal container) stdout never reaches the captured benchmark log,
# so after every completed run the host re-emits the prompt-executor /
# conditioning-cache breakdowns and the PNG provenance from the run artifact.
# Each formatter below is pure and defensive: a missing event or malformed
# payload yields ``None`` (skipped by the caller) and never raises.

_PE_EXEC_CHILD_KEYS = (
    "dynamic_prompt_ms",
    "is_changed_ms",
    "seed_apply_ms",
    "clean_unused_ms",
    "cache_gather_ms",
    "cleanup_gc_ms",
)
_PE_C2F_CHILD_KEYS = (
    "c2f_topo_walk_ms",
    "c2f_stage_ms",
    "c2f_first_node_prefix_ms",
)
_CC_OPT_FIELD_KEYS = (
    "entry_header_open_read_ms",
    "entry_header_parse_ms",
    "entry_header_validate_ms",
    "entry_data_open_read_ms",
    "entry_deserialize_ms",
    "deser_payload_sha_ms",
    "deser_tensor_sha_ms",
    "deser_tensor_rebuild_ms",
    "deser_materialize_ms",
    "deser_tensor_count",
    "deser_tensors_bytes",
    "hit_read_bytes",
    "hit_read_mbps",
)

# Every key the [v2.prompt_executor_breakdown] host line already renders (or
# consumes for a derived field).  Pass-through extras skip these so the fixed
# field order stays byte-identical and nothing is ever duplicated.
_PE_EMITTED_KEYS = frozenset({
    "request_id",
    "exec_to_cached_ms",
    "dynamic_prompt_ms",
    "is_changed_ms",
    "signature_keys_ms",
    # Consumed by the signature_keys_ms derivation (never emitted itself).
    "signature_keys_total_ms",
    "seed_apply_ms",
    "clean_unused_ms",
    "cache_gather_ms",
    "cleanup_gc_ms",
    "residual_ms",
    "c2f_cached_to_first_node_ms",
    "c2f_topo_walk_ms",
    "c2f_topo_input_info_ms",
    "c2f_topo_other_ms",
    "c2f_stage_ms",
    "c2f_first_node_prefix_ms",
    "c2f_residual_ms",
})

# Every key the [v2.conditioning_exact_hit_breakdown] host line already
# renders.  Includes BOTH the emitted output names AND their lookup_diagnostics
# source names (several source keys are renamed on emit — e.g.
# key_build_digest_ms → key_build_ms, header_bytes_read → header_bytes,
# measured_children_ms → children_ms) so the pass-through never duplicates a
# field that was already handled.
_CC_EMITTED_KEYS = frozenset({
    "request_id",
    "decision",
    "lookup_wall_ms",
    # Emitted output names.
    "total_ms",
    "key_build_ms",
    "lock_wait_ms",
    "manifest_read_ms",
    "manifest_bytes",
    "manifest_entries",
    "entry_lookup_ms",
    "header_bytes",
    "data_bytes",
    "lru_touch_ms",
    "lru_touch_mode",
    "children_ms",
    "residual_ms",
    # lookup_diagnostics source names (renamed on emit).
    "key_build_digest_ms",
    "manifest_read_bytes",
    "header_bytes_read",
    "data_bytes_read",
    "measured_children_ms",
    *_CC_OPT_FIELD_KEYS,
})



def _fmt_v2_metric(value: Any) -> str:
    """Format a single host-provenance metric for a print line.

    ``None`` → ``absent``; ints stay integral; floats round to 3 decimals;
    non-numeric values (e.g. ``lru_touch_mode``) pass through unchanged.
    """
    if value is None:
        return _ABSENT_STR
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    try:
        return str(round(float(value), 3))
    except (TypeError, ValueError):
        return str(value)


def _host_trace_events(artifact: Any) -> list[Any] | None:
    """Return the remote full-trace event list from the artifact.

    Resolves both layouts seen in practice:
      - ``artifact["full_trace"]["events"]`` (experiment record), and
      - ``artifact["result"]["trace"]["events"]`` (raw ``_run_one`` artifact).
    ``None`` when neither carries an event list.
    """
    if not isinstance(artifact, dict):
        return None
    trace = artifact.get("full_trace")
    if isinstance(trace, dict) and isinstance(trace.get("events"), list):
        return trace["events"]
    result = artifact.get("result")
    if isinstance(result, dict):
        trace = result.get("trace")
        if isinstance(trace, dict) and isinstance(trace.get("events"), list):
            return trace["events"]
    return None


def _host_output_descriptor(artifact: Any) -> list[Any] | None:
    """Return the output-descriptor list from the artifact.

    Resolves both layouts seen in practice:
      - ``artifact["output_descriptor"]`` (experiment record), and
      - ``artifact["result"]["asset_descriptors"]`` / ``result["output_descriptor"]``
        (raw ``_run_one`` artifact).
    ``None`` when neither carries a list.
    """
    if not isinstance(artifact, dict):
        return None
    descriptor = artifact.get("output_descriptor")
    if isinstance(descriptor, list):
        return descriptor
    result = artifact.get("result")
    if isinstance(result, dict):
        for key in ("asset_descriptors", "output_descriptor"):
            descriptor = result.get(key)
            if isinstance(descriptor, list):
                return descriptor
    return None


def _find_host_trace_event_metadata(
    artifact: Any, name: str, *, prefer_key: str | None = None
) -> dict[str, Any] | None:
    """Return the metadata dict of a remote full-trace event named *name*.

    Defaults to the FIRST matching event's metadata (unchanged behavior).
    When *prefer_key* is given, scan ALL matching events and return the first
    whose metadata carries a non-``None`` value for *prefer_key*, falling back
    to the first matching metadata when none does.  This guards against
    duplicate events where a metadata-less legacy ``timing_trace``
    reconstruction shadows the populated remote event (observed for
    ``output_encode_end``: the legacy stage ``t8c_output_encode_end`` is
    rebuilt as a bare event with ``metadata={}`` while the remote execution
    event carries ``duration_ms`` / ``compress_level`` / ``png_compress_ms``).

    ``None`` when the artifact, the trace, the events list, the named event or
    its metadata is absent (so callers can never raise on a missing event).
    """
    events = _host_trace_events(artifact)
    if events is None:
        return None
    fallback: dict[str, Any] | None = None
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("name") != name:
            continue
        metadata = event.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if prefer_key is None:
            return metadata
        if fallback is None:
            fallback = metadata
        if metadata.get(prefer_key) is not None:
            return metadata
    return fallback if prefer_key is not None else None


def _host_extra_fields(source: Any, emitted: frozenset[str]) -> str:
    """Generic new-key pass-through for the host provenance lines (RUN-1 gate).

    Appends ``key=<formatted value>`` for every scalar key in *source* that is
    not already emitted/handled by the fixed field set, in sorted order — so
    ANY new metadata key (e.g. Task-1 ``signature_cache_*``, Task-2
    ``prefetch_*`` / ``manifest_memory_hit`` / ``payload_memory_hit`` /
    ``normal_lookup_fallback``, and future fields from parallel lanes)
    automatically appears on the emitted line after the existing fixed fields.

    Rules (documented):
      - ``None`` / non-scalar (dict/list) values are OMITTED entirely — only
        the KNOWN fixed fields may render ``absent``, never unknown keys.
      - One level of nesting is flattened: a sub-dict whose entries are all
        scalars (e.g. a future ``lookup_diagnostics["prefetch"]`` sub-dict)
        has its entries promoted to the top level so nested keys still
        surface as ``key=value``.  Sub-keys that collide with an already
        emitted/handled key are skipped.
      - Keys already emitted by the fixed field list (or consumed for a
        derived field) are never duplicated.

    Returns ``""`` when nothing is appended, so the fixed-field output stays
    byte-identical when no new keys are present.
    """
    if not isinstance(source, dict):
        return ""
    flat: dict[str, Any] = {}
    for key, value in source.items():
        if key in emitted:
            continue
        if (
            isinstance(value, dict)
            and value
            and all(not isinstance(v, (dict, list)) for v in value.values())
        ):
            for sub_key, sub_value in value.items():
                if sub_key not in emitted and sub_key not in flat:
                    flat[sub_key] = sub_value
            continue
        flat[key] = value
    extras: list[str] = []
    for key in sorted(flat):
        if key in emitted:
            continue
        value = flat[key]
        if value is None or isinstance(value, (dict, list)):
            continue
        extras.append(f"{key}={_fmt_v2_metric(value)}")
    return " ".join(extras)


def format_host_prompt_executor_breakdown(artifact: Any) -> str | None:
    """Render the ``[v2.prompt_executor_breakdown]`` host line.

    Parents come from the ``prompt_executor_milestones`` event metadata
    (``execution_start_to_cached_ms``, ``cached_to_first_node_ms``); the
    breakdown children come from ``metadata["breakdown"]`` (added by the
    remote-enrichment lane).  Missing children render as ``absent``; each
    residual is emitted whenever the parent is present AND at least one child
    key is present (absent children are implicitly part of the residual), so
    e.g. a missing ``seed_apply_ms`` no longer hides ``residual_ms``.
    """
    metadata = _find_host_trace_event_metadata(artifact, "prompt_executor_milestones")
    if metadata is None:
        return None
    request_id = str(artifact.get("request_id", "")) if isinstance(artifact, dict) else ""
    exec_to_cached_ms = metadata.get("execution_start_to_cached_ms")
    c2f_cached_to_first_node_ms = metadata.get("cached_to_first_node_ms")
    if exec_to_cached_ms is None and c2f_cached_to_first_node_ms is None:
        return None
    breakdown = metadata.get("breakdown")
    if not isinstance(breakdown, dict):
        breakdown = {}

    def _child(key: str) -> str:
        return _fmt_v2_metric(breakdown.get(key))

    # Derived child: signature_keys_ms = signature_keys_total_ms - is_changed_ms.
    sig_total = _num(breakdown.get("signature_keys_total_ms"))
    is_changed = _num(breakdown.get("is_changed_ms"))
    if sig_total is not None and is_changed is not None:
        signature_keys_ms = _fmt_v2_metric(sig_total - is_changed)
    else:
        signature_keys_ms = _ABSENT_STR

    # residual_ms: emitted whenever the parent is present AND at least one
    # exec-to-cached child key is present (absent children are implicitly part
    # of the residual — a missing seed_apply_ms must not hide it).
    exec_children = [_num(breakdown.get(key)) for key in _PE_EXEC_CHILD_KEYS]
    exec_present = [child for child in exec_children if child is not None]
    exec_parent = _num(exec_to_cached_ms)
    signature_derived = (sig_total - is_changed) if (sig_total is not None and is_changed is not None) else None
    if exec_parent is not None and (exec_present or signature_derived is not None):
        exec_sum = float(sum(exec_present))
        if signature_derived is not None:
            exec_sum += signature_derived
        residual_ms = _fmt_v2_metric(round(exec_parent, 3) - round(exec_sum, 3))
    else:
        residual_ms = _ABSENT_STR

    # c2f children + c2f residual_ms (same partial-children rule).
    c2f_children = [_num(breakdown.get(key)) for key in _PE_C2F_CHILD_KEYS]
    c2f_present = [child for child in c2f_children if child is not None]
    c2f_parent = _num(c2f_cached_to_first_node_ms)
    if c2f_parent is not None and c2f_present:
        c2f_sum = sum(float(child) for child in c2f_present)
        c2f_residual_ms = _fmt_v2_metric(
            round(c2f_parent, 3) - round(c2f_sum, 3)
        )
    else:
        c2f_residual_ms = _ABSENT_STR

    # Pass-through: ANY new metadata["breakdown"] key (signature_cache_* etc.)
    # is appended after the fixed fields, in sorted order, when present.
    _extra_tail = _host_extra_fields(breakdown, _PE_EMITTED_KEYS)
    return (
        "[v2.prompt_executor_breakdown] "
        f"request_id={request_id} "
        f"exec_to_cached_ms={_fmt_v2_metric(exec_to_cached_ms)} "
        f"dynamic_prompt_ms={_child('dynamic_prompt_ms')} "
        f"is_changed_ms={_child('is_changed_ms')} "
        f"signature_keys_ms={signature_keys_ms} "
        f"seed_apply_ms={_child('seed_apply_ms')} "
        f"clean_unused_ms={_child('clean_unused_ms')} "
        f"cache_gather_ms={_child('cache_gather_ms')} "
        f"cleanup_gc_ms={_child('cleanup_gc_ms')} "
        f"residual_ms={residual_ms} "
        f"c2f_cached_to_first_node_ms={_fmt_v2_metric(c2f_cached_to_first_node_ms)} "
        f"c2f_topo_walk_ms={_child('c2f_topo_walk_ms')} "
        f"c2f_topo_input_info_ms={_child('c2f_topo_input_info_ms')} "
        f"c2f_topo_other_ms={_child('c2f_topo_other_ms')} "
        f"c2f_stage_ms={_child('c2f_stage_ms')} "
        f"c2f_first_node_prefix_ms={_child('c2f_first_node_prefix_ms')} "
        f"c2f_residual_ms={c2f_residual_ms}"
    ) + (f" {_extra_tail}" if _extra_tail else "")


def format_host_conditioning_breakdown(artifact: Any) -> str | None:
    """Render the ``[v2.conditioning_exact_hit_breakdown]`` host line.

    Lookup metrics come from the ``clip_conditioning_cache_lookup`` event
    (top-level ``lookup_wall_ms`` + ``lookup_diagnostics`` dict) and the
    decision from the ``clip_conditioning_cache_decision`` event.  Opt-gated
    deserialization / read fields are appended only when present.  Any NEW
    ``lookup_diagnostics`` key (Task-2 prefetch / in-memory-cache fields,
    future fields) is appended generically via ``_host_extra_fields``.
    """
    metadata = _find_host_trace_event_metadata(artifact, "clip_conditioning_cache_lookup")
    if metadata is None:
        return None
    request_id = str(artifact.get("request_id", "")) if isinstance(artifact, dict) else ""
    diagnostics = metadata.get("lookup_diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    decision_metadata = _find_host_trace_event_metadata(
        artifact, "clip_conditioning_cache_decision"
    )
    decision = (
        decision_metadata.get("decision")
        if isinstance(decision_metadata, dict)
        else None
    )

    parts = [
        "[v2.conditioning_exact_hit_breakdown]",
        f"request_id={request_id}",
        f"decision={_fmt_v2_metric(decision)}",
        f"lookup_wall_ms={_fmt_v2_metric(metadata.get('lookup_wall_ms'))}",
        f"total_ms={_fmt_v2_metric(diagnostics.get('total_ms'))}",
        f"key_build_ms={_fmt_v2_metric(diagnostics.get('key_build_digest_ms'))}",
        f"lock_wait_ms={_fmt_v2_metric(diagnostics.get('lock_wait_ms'))}",
        f"manifest_read_ms={_fmt_v2_metric(diagnostics.get('manifest_read_ms'))}",
        f"manifest_bytes={_fmt_v2_metric(diagnostics.get('manifest_read_bytes'))}",
        f"manifest_entries={_fmt_v2_metric(diagnostics.get('manifest_entries'))}",
        f"entry_lookup_ms={_fmt_v2_metric(diagnostics.get('entry_lookup_ms'))}",
        f"header_bytes={_fmt_v2_metric(diagnostics.get('header_bytes_read'))}",
        f"data_bytes={_fmt_v2_metric(diagnostics.get('data_bytes_read'))}",
        f"lru_touch_ms={_fmt_v2_metric(diagnostics.get('lru_touch_ms'))}",
        f"lru_touch_mode={_fmt_v2_metric(diagnostics.get('lru_touch_mode'))}",
        f"children_ms={_fmt_v2_metric(diagnostics.get('measured_children_ms'))}",
        f"residual_ms={_fmt_v2_metric(diagnostics.get('residual_ms'))}",
    ]
    for key in _CC_OPT_FIELD_KEYS:
        if diagnostics.get(key) is not None:
            parts.append(f"{key}={_fmt_v2_metric(diagnostics.get(key))}")
    # Pass-through: ANY new lookup_diagnostics key (Task-2 prefetch_*,
    # manifest_memory_hit, payload_memory_hit, normal_lookup_fallback,
    # prefetch_reason, and future fields) is appended after the fixed fields,
    # in sorted order, when present — mirroring the remote emitter which also
    # appends "only when present in the lookup diagnostics".
    _extra_tail = _host_extra_fields(diagnostics, _CC_EMITTED_KEYS)
    if _extra_tail:
        parts.append(_extra_tail)
    return " ".join(parts)


def _host_trace_metadata(artifact: Any) -> dict[str, Any] | None:
    """Return the remote full-trace METADATA dict from the artifact.

    Resolves both layouts seen in practice:
      - ``artifact["full_trace"]["metadata"]`` (experiment record), and
      - ``artifact["result"]["trace"]["metadata"]`` (raw ``_run_one`` artifact).
    ``None`` when neither carries a metadata dict.
    """
    if not isinstance(artifact, dict):
        return None
    trace = artifact.get("full_trace")
    if isinstance(trace, dict) and isinstance(trace.get("metadata"), dict):
        return trace["metadata"]
    result = artifact.get("result")
    if isinstance(result, dict):
        trace = result.get("trace")
        if isinstance(trace, dict) and isinstance(trace.get("metadata"), dict):
            return trace["metadata"]
    return None


def _host_restore_timing(artifact: Any) -> dict[str, Any] | None:
    """Return the ``_restore_timing`` dict from the artifact, if present.

    Covers both layouts: ``artifact["_restore_timing"]`` and
    ``artifact["result"]["_restore_timing"]``.
    """
    if not isinstance(artifact, dict):
        return None
    timing = artifact.get("_restore_timing")
    if isinstance(timing, dict):
        return timing
    result = artifact.get("result")
    if isinstance(result, dict) and isinstance(result.get("_restore_timing"), dict):
        return result["_restore_timing"]
    return None


def format_host_folder_warm(artifact: Any) -> str | None:
    """Render the ``[v2.folder_warm]`` host line from restore trace metadata.

    Reads ``folder_warm_ms`` / ``folder_warm_folders`` from the trace-level
    metadata keys set by the container's advisory folder-listing warm (with a
    fallback to the ``_restore_timing`` dict when the trace serialization
    raced the daemon thread).  Missing keys render ``absent``; the line is
    skipped entirely when neither channel carries any folder-warm evidence.
    """
    metadata = _host_trace_metadata(artifact)
    meta = dict(metadata) if isinstance(metadata, dict) else {}
    if not any(k in meta for k in ("folder_warm_ms", "folder_warm_folders")):
        timing = _host_restore_timing(artifact)
        if isinstance(timing, dict):
            for key in ("folder_warm_ms", "folder_warm_folders"):
                if key not in meta and timing.get(key) is not None:
                    meta[key] = timing[key]
    if not any(k in meta for k in ("folder_warm_ms", "folder_warm_folders")):
        return None
    request_id = str(artifact.get("request_id", "")) if isinstance(artifact, dict) else ""
    return (
        "[v2.folder_warm] "
        f"request_id={request_id} "
        f"folder_warm_ms={_fmt_v2_metric(meta.get('folder_warm_ms'))} "
        f"folder_warm_folders={_fmt_v2_metric(meta.get('folder_warm_folders'))}"
    )


def format_host_input_types_warm(artifact: Any) -> str | None:
    """Render the ``[v2.input_types_warm]`` host line from trace metadata.

    Reads ``input_types_warm_ms`` / ``input_types_warm_classes`` from the
    trace-level metadata keys set by the container's advisory per-plan
    ``INPUT_TYPES()`` warm.  Missing keys render ``absent``; the line is
    skipped entirely when neither key is present.
    """
    metadata = _host_trace_metadata(artifact)
    meta = dict(metadata) if isinstance(metadata, dict) else {}
    if not any(k in meta for k in ("input_types_warm_ms", "input_types_warm_classes")):
        return None
    request_id = str(artifact.get("request_id", "")) if isinstance(artifact, dict) else ""
    return (
        "[v2.input_types_warm] "
        f"request_id={request_id} "
        f"input_types_warm_ms={_fmt_v2_metric(meta.get('input_types_warm_ms'))} "
        f"input_types_warm_classes={_fmt_v2_metric(meta.get('input_types_warm_classes'))}"
    )


def format_host_png_output(artifact: Any) -> str | None:
    """Render the ``[v2.png_output]`` host line.

    Encoder metrics come from the ``output_encode_end`` event (optional
    ``compress_level`` / ``png_compress_ms`` are omitted when absent); the
    provenance fields come from ``artifact["output_descriptor"][0]``.
    """
    # The remote trace may carry BOTH a populated execution event and a
    # metadata-less legacy timing_trace reconstruction of the same event
    # (from the legacy stage map).  Prefer the populated event regardless of
    # order so encoder metrics never vanish behind the empty duplicate.
    metadata = _find_host_trace_event_metadata(
        artifact, "output_encode_end", prefer_key="duration_ms"
    )
    if metadata is None:
        return None
    request_id = str(artifact.get("request_id", "")) if isinstance(artifact, dict) else ""
    descriptor = _host_output_descriptor(artifact)
    if not descriptor:
        return None
    entry = descriptor[0]
    if not isinstance(entry, dict):
        return None

    parts = ["[v2.png_output]", f"request_id={request_id}"]
    compress_level = metadata.get("compress_level")
    if compress_level is not None:
        parts.append(f"compress_level={_fmt_v2_metric(compress_level)}")
    png_encode_ms = metadata.get("duration_ms")
    if png_encode_ms is not None:
        parts.append(f"png_encode_ms={_fmt_v2_metric(png_encode_ms)}")
    png_compress_ms = metadata.get("png_compress_ms")
    if png_compress_ms is not None:
        parts.append(f"png_compress_ms={_fmt_v2_metric(png_compress_ms)}")
    parts.extend([
        f"width={_fmt_v2_metric(entry.get('width'))}",
        f"height={_fmt_v2_metric(entry.get('height'))}",
        f"bytes={_fmt_v2_metric(entry.get('byte_count'))}",
        f"sha={_fmt_v2_metric(entry.get('asset_id'))}",
    ])
    return " ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Host submission timeline breakdown (V2 pass 2 — instrumentation ONLY)
#
# The repeatable ~17.16s "Modal handle and submission" waterfall stage is
#   local_receive → modal_submission_attempt
# (v2_waterfall.py stage bounds 752-768).  PROVEN root cause (RUN 3):
#   local_receive_to_worker_start_ms=17093
# — the ``await _ensure_full_node_registry()`` call inside ``_run_one`` loads
# the FULL ComfyUI node registry (2192 classes: nodes + comfy_extras +
# custom nodes + PromptServer mirror) before the first plan build.  Only
# ~65ms is plan build (63ms) + handle lookup / generator create (2ms,
# persistent IPC hit).  Modal platform time is only ~5.32s (scheduling
# 1.596s + pre-Python restore 3.722s).
#
# D1 FIX (local-dispatch preload): the registry is now preloaded ONCE in
# ``main`` before the run loop, so run-1 local_receive→worker_start is ~0
# (the ``_run_one`` await short-circuits via the ``_NODE_REGISTRY_READY`` fast
# path) and the preload cost is reported as the explicit harness-setup metric
# ``node_registry_preload_ms`` — never inside a per-run submission window.
# ``build_host_submission_breakdown_line`` therefore gates the three in-window
# registry intervals to ``absent`` and reports the preload separately.
#
# This is BENCHMARK-ONLY instrumentation: production runs inside a long-lived
# ComfyUI server whose node registry is already preloaded at startup, so the
# per-run registry-init cost does not exist there.
#
# Scheduling provenance (scheduling_ms / scheduling_source):
#   scheduling_ms = modal_restore_begin_wall_unix_ns − modal_submission_attempt_wall_unix_ns
# where restore-begin is resolved by ``resolve_modal_restore_begin``:
#   result_carried — ``extract_restore_begin_from_result`` found the boundary
#                     already carried in the result/timing/local_timing dicts
#   modal_app_log   — resolved from the Modal app-log line
#                     "restoring function from memory snapshot"
#                     (``_fetch_modal_restore_begin_logs_async``)
#   unavailable     — neither source produced a boundary; the report's
#                     modal_scheduling stage then covers the fused
#                     submission → python_resume interval instead (and the
#                     boundary flag modal_restore_begin_unavailable is set)
# The interval includes Modal admission / queue / placement and the
# scheduler→restore handoff; it EXCLUDES pre-Python snapshot restore
# (restore-begin → python resume) and all Python-side restore work (decomposed
# separately in [v2.restore_breakdown], which lives in modal_app).
# ═══════════════════════════════════════════════════════════════════════════

_HOST_SUBMISSION_BOUNDARY_SOURCE = "first_anext"
"""The modal_submission_attempt event is captured at the first ``__anext__``
of the lazy remote generator — the TRUE Modal submit boundary (not the
``remote_gen(...)`` call, which only constructs the lazy generator)."""


def build_host_submission_breakdown_line(
    artifact: Any,
    *,
    command_start_unix_ms: int | None = None,
    python_first_line_ns: int | None = None,
    local_receive_wall_ns: int | None = None,
    node_registry_start_ns: int | None = None,
    node_registry_end_ns: int | None = None,
    scheduling_ms: float | None = None,
    scheduling_source: str = "unavailable",
) -> str:
    """Build the single-line ``[v2.host_submission_breakdown]`` record.

    Pure and defensive: every missing stamp renders ``absent`` (never 0,
    never a crash).  Existing measured values are reused from the run's
    ``local_timing`` dict where they exist; only intervals that no existing
    breakdown covers are recomputed from the merged trace events (read-only).
    Always returns a string — callers wrap the print in try/except.
    """
    if not isinstance(artifact, dict):
        artifact = {}
    request_id = str(artifact.get("request_id", ""))
    events = _host_trace_events(artifact) or []

    def _event_wall(name: str) -> int | None:
        for event in events:
            if not isinstance(event, dict) or event.get("name") != name:
                continue
            value = event.get("wall_unix_ns")
            if isinstance(value, (int, float)):
                return int(value)
        return None

    local_timing = artifact.get("local_timing")
    if not isinstance(local_timing, dict):
        result = artifact.get("result")
        if isinstance(result, dict) and isinstance(result.get("local_timing"), dict):
            local_timing = result["local_timing"]
    if not isinstance(local_timing, dict):
        local_timing = {}

    def _ms(begin: Any, end: Any) -> float | None:
        """Wall-clock interval in ms; missing/negative/non-numeric → None."""
        if begin is None or end is None or isinstance(begin, bool) or isinstance(end, bool):
            return None
        try:
            delta_ns = int(end) - int(begin)
        except (TypeError, ValueError):
            return None
        if delta_ns < 0:
            return None
        return round(delta_ns / 1_000_000.0, 3)

    def _existing(key: str) -> float | None:
        """Reuse an existing measured local_timing value (absent/invalid → None)."""
        value = local_timing.get(key)
        if value is None or isinstance(value, bool):
            return None
        try:
            return round(float(value), 3)
        except (TypeError, ValueError):
            return None

    worker_start_wall = _event_wall("worker_start")
    plan_build_call_start_wall = _event_wall("build_execution_plan_call_start")
    execute_plan_call_start_wall = _event_wall("execute_plan_call_start")
    transport_entry_wall = _event_wall("transport_entry")
    handle_lookup_start_wall = _event_wall("modal_handle_lookup_start")
    handle_lookup_end_wall = _event_wall("modal_handle_lookup_end")
    payload_serialize_start_wall = _event_wall("modal_payload_serialize_start")
    payload_serialize_end_wall = _event_wall("modal_payload_serialize_end")
    generator_create_start_wall = _event_wall("modal_generator_create_start")
    generator_created_wall = _event_wall("modal_generator_created")
    submission_attempt_wall = _event_wall("modal_submission_attempt")
    first_remote_event_wall = _event_wall("modal_first_remote_event")

    command_start_ns = None
    if command_start_unix_ms is not None and not isinstance(command_start_unix_ms, bool):
        try:
            command_start_ns = int(command_start_unix_ms) * 1_000_000
        except (TypeError, ValueError):
            command_start_ns = None

    # Interpreter-boot + pre-run stamps (no pre-existing breakdown covers
    # these; absent whenever the corresponding stamp was never captured).
    command_start_to_python_first_line_ms = _ms(command_start_ns, python_first_line_ns)
    python_first_line_to_local_receive_ms = _ms(python_first_line_ns, local_receive_wall_ns)
    # D1 preload gating: when the full node registry was preloaded in ``main``
    # BEFORE this run's local_receive stamp, the registry intervals no longer
    # sit inside the per-run window — they render absent and the preload is
    # reported separately as node_registry_preload_ms (harness setup, never
    # scheduling; C3 semantics preserved).
    _registry_preloaded_before_receive = (
        isinstance(node_registry_end_ns, int)
        and not isinstance(node_registry_end_ns, bool)
        and isinstance(local_receive_wall_ns, int)
        and not isinstance(local_receive_wall_ns, bool)
        and int(node_registry_end_ns) <= int(local_receive_wall_ns)
    )
    local_receive_to_registry_start_ms = (
        None if _registry_preloaded_before_receive else _ms(local_receive_wall_ns, node_registry_start_ns)
    )
    node_registry_init_ms = (
        None if _registry_preloaded_before_receive else _ms(node_registry_start_ns, node_registry_end_ns)
    )
    registry_end_to_worker_start_ms = (
        None if _registry_preloaded_before_receive else _ms(node_registry_end_ns, worker_start_wall)
    )
    node_registry_preload_ms = (
        _ms(node_registry_start_ns, node_registry_end_ns) if _registry_preloaded_before_receive else None
    )

    # Existing measured values are authoritative; event-derived fallbacks fill
    # only the gaps the local_submission_breakdown does not cover.
    worker_start_to_plan_build_start_ms = (
        _existing("worker_start_to_plan_build_ms")
        or _ms(worker_start_wall, plan_build_call_start_wall)
    )
    plan_build_ms = _existing("plan_build_ms")
    plan_build_to_transport_entry_ms = _ms(execute_plan_call_start_wall, transport_entry_wall)
    transport_entry_to_handle_lookup_ms = (
        _existing("transport_entry_to_handle_lookup_ms")
        or _ms(transport_entry_wall, handle_lookup_start_wall)
    )
    handle_lookup_ms = (
        _existing("handle_lookup_ms")
        or _ms(handle_lookup_start_wall, handle_lookup_end_wall)
    )
    payload_serialize_ms = (
        _existing("payload_serialize_ms")
        or _ms(payload_serialize_start_wall, payload_serialize_end_wall)
    )
    generator_create_ms = (
        _existing("generator_create_ms")
        or _ms(generator_create_start_wall, generator_created_wall)
    )
    generator_created_to_submission_ms = (
        _existing("generator_created_to_first_iteration_ms")
        or _ms(generator_created_wall, submission_attempt_wall)
    )
    local_receive_to_submission_ms = (
        _existing("local_receive_to_actual_submission_ms")
        or _ms(local_receive_wall_ns, submission_attempt_wall)
    )
    first_remote_signal_ms = (
        _existing("first_iteration_to_first_remote_event_ms")
        or _ms(submission_attempt_wall, first_remote_event_wall)
    )
    # D1 zero-gap: the user-equivalent command-trigger → modal_submission_attempt
    # interval (the TRUE user-visible submit boundary) for the externally
    # invoked benchmark command.
    user_equivalent_trigger_to_modal_submission_ms = _ms(command_start_ns, submission_attempt_wall)

    return (
        "[v2.host_submission_breakdown] "
        f"request_id={request_id} "
        f"command_start_to_python_first_line_ms={_fmt_v2_metric(command_start_to_python_first_line_ms)} "
        f"python_first_line_to_local_receive_ms={_fmt_v2_metric(python_first_line_to_local_receive_ms)} "
        f"local_receive_to_registry_start_ms={_fmt_v2_metric(local_receive_to_registry_start_ms)} "
        f"node_registry_init_ms={_fmt_v2_metric(node_registry_init_ms)} "
        f"registry_end_to_worker_start_ms={_fmt_v2_metric(registry_end_to_worker_start_ms)} "
        f"node_registry_preload_ms={_fmt_v2_metric(node_registry_preload_ms)} "
        f"worker_start_to_plan_build_start_ms={_fmt_v2_metric(worker_start_to_plan_build_start_ms)} "
        f"plan_build_ms={_fmt_v2_metric(plan_build_ms)} "
        f"plan_build_to_transport_entry_ms={_fmt_v2_metric(plan_build_to_transport_entry_ms)} "
        f"transport_entry_to_handle_lookup_ms={_fmt_v2_metric(transport_entry_to_handle_lookup_ms)} "
        f"handle_lookup_ms={_fmt_v2_metric(handle_lookup_ms)} "
        f"payload_serialize_ms={_fmt_v2_metric(payload_serialize_ms)} "
        f"generator_create_ms={_fmt_v2_metric(generator_create_ms)} "
        f"generator_created_to_submission_ms={_fmt_v2_metric(generator_created_to_submission_ms)} "
        f"local_receive_to_submission_ms={_fmt_v2_metric(local_receive_to_submission_ms)} "
        f"submission_boundary_source={_HOST_SUBMISSION_BOUNDARY_SOURCE} "
        f"first_remote_signal_ms={_fmt_v2_metric(first_remote_signal_ms)} "
        f"scheduling_ms={_fmt_v2_metric(scheduling_ms)} "
        f"scheduling_source={scheduling_source or 'unavailable'} "
        f"user_equivalent_trigger_to_modal_submission_ms={_fmt_v2_metric(user_equivalent_trigger_to_modal_submission_ms)}"
    )


def build_trigger_to_submission_line(
    runtime_trace: Any,
    *,
    origin: Mapping[str, Any] | None = None,
    transport_meta: Mapping[str, Any] | None = None,
    cold_wait_before_ms: float | None = None,
) -> str:
    """Render the per-run [v2.trigger_to_submission] reconciliation line.

    Goal-7 accounting for the trigger→submission window: every schema stage
    is an offset (ms) from the benchmark_iteration_selected monotonic stamp;
    trigger_to_submission_ms = modal_submission_attempt −
    benchmark_iteration_selected; measured_children_ms / residual_ms /
    reconciliation_status reuse the canonical _build_local_submission_breakdown
    partition (same semantics, identical children).  Pure and defensive:
    every missing event renders 'absent' and never raises.
    """
    _bd = _build_local_submission_breakdown(
        runtime_trace,
        origin=origin,
        transport_meta=transport_meta,
        plan_to_dict_count=1,
    )
    def _event_mono(name: str) -> int | None:
        for evt in getattr(runtime_trace, "events", ()):
            if getattr(evt, "name", "") != name:
                continue
            value = getattr(evt, "monotonic_ns", None)
            if isinstance(value, int):
                return value
        return None
    def _delta_ms(start_name: str, end_name: str) -> Any:
        start = _event_mono(start_name)
        end = _event_mono(end_name)
        if start is None or end is None:
            return None
        delta = end - start
        if delta < 0:
            return "invalid_negative"
        return round(delta / 1_000_000.0, 3)
    _fmt = _fmt_v2_metric
    _trigger = _event_mono("benchmark_iteration_selected")
    _submit = _event_mono("modal_submission_attempt")
    _trigger_to_submission_ms: Any = None
    if _trigger is not None and _submit is not None and _submit >= _trigger:
        _trigger_to_submission_ms = round((_submit - _trigger) / 1_000_000.0, 3)
    _measured = _bd.get("measured_children_ms")
    _residual: Any = None
    if isinstance(_trigger_to_submission_ms, (int, float)) and isinstance(_measured, (int, float)):
        _residual = round(_trigger_to_submission_ms - float(_measured), 3)
    _status = "complete"
    if not isinstance(_trigger_to_submission_ms, (int, float)):
        _status = "incomplete"
    elif not isinstance(_measured, (int, float)):
        _status = "incomplete"
    elif isinstance(_residual, (int, float)) and _residual < -0.001:
        _status = "overlap"
    return (
        "[v2.trigger_to_submission] "
        f"request_id={str(_bd.get('request_id') or '')} "
        f"benchmark_iteration_selected_to_local_worker_submit_ms={_fmt(_delta_ms('benchmark_iteration_selected', 'local_worker_submit'))} "
        f"local_worker_submit_to_worker_start_ms={_fmt(_delta_ms('local_worker_submit', 'worker_start'))} "
        f"worker_start_to_plan_build_start_ms={_fmt(_bd.get('worker_start_to_plan_build_ms'))} "
        f"plan_build_ms={_fmt(_bd.get('plan_build_ms'))} "
        f"plan_build_end_to_modal_handle_ready_ms={_fmt(_delta_ms('plan_build_end', 'modal_handle_ready'))} "
        f"modal_handle_ready_to_modal_submission_attempt_ms={_fmt(_delta_ms('modal_handle_ready', 'modal_submission_attempt'))} "
        f"intentional_cold_wait_before_run_ms={_fmt(cold_wait_before_ms)} "
        f"trigger_to_submission_ms={_fmt(_trigger_to_submission_ms)} "
        f"measured_children_ms={_fmt(_measured)} "
        f"residual_ms={_fmt(_residual)} "
        f"reconciliation_status={_status}"
    )


def build_user_trigger_line(
    *,
    request_id: str = "",
    command_start_unix_ms: int | None = None,
    python_first_line_ns: int | None = None,
    submission_attempt_wall_ns: int | None = None,
    response_received_wall_ns: int | None = None,
    registry_store_hit: bool | None = None,
    registry_load_ms: float | None = None,
) -> str:
    """Report the three never-conflated external-command clocks (D1 zero-gap).

    - process_start_to_response_ms: python_first_line → response receipt
    - user_equivalent_trigger_to_response_ms: command trigger → response receipt
    - user_equivalent_trigger_to_modal_submission_ms: command trigger →
      modal_submission_attempt (the TRUE user-visible submit boundary)

    Registry-store state is reported beside them so setup work is always
    attributable and never conflated with trigger latency.  Pure and
    defensive: every missing stamp renders 'absent' and never raises."""
    def _ms(begin: Any, end: Any) -> Any:
        if begin is None or end is None or isinstance(begin, bool) or isinstance(end, bool):
            return None
        try:
            delta = int(end) - int(begin)
        except (TypeError, ValueError):
            return None
        if delta < 0:
            return None
        return round(delta / 1_000_000.0, 3)

    _cmd_ns = None
    if command_start_unix_ms is not None and not isinstance(command_start_unix_ms, bool):
        try:
            _cmd_ns = int(command_start_unix_ms) * 1_000_000
        except (TypeError, ValueError):
            _cmd_ns = None
    return (
        "[v2.user_trigger] "
        f"request_id={request_id} "
        f"process_start_to_response_ms={_fmt_v2_metric(_ms(python_first_line_ns, response_received_wall_ns))} "
        f"user_equivalent_trigger_to_response_ms={_fmt_v2_metric(_ms(_cmd_ns, response_received_wall_ns))} "
        f"user_equivalent_trigger_to_modal_submission_ms={_fmt_v2_metric(_ms(_cmd_ns, submission_attempt_wall_ns))} "
        f"registry_store_hit={_fmt_v2_metric(registry_store_hit)} "
        f"registry_load_ms={_fmt_v2_metric(registry_load_ms)}"
    )


async def _run_one(
    *,
    index: int,
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    bypass_cpu_snapshot_unet: bool = False,
    _defer_waterfall: bool = False,
    # Variance-cold mode: extra request-origin diagnostic keys carried to the
    # remote runtime (e.g. variance_mode, variance_pretouch, env_profile).
    _extra_origin: dict[str, Any] | None = None,
    # Test overrides (injected helpers, not used in production)
    _test_restore_publisher: Any = None,
    _test_profile_setter: Any = None,
    _test_profile_checker: Any = None,
    _test_trace_downloader: Any = None,
) -> dict[str, Any]:
    # T0: benchmark iteration origin (literal first line)
    _req_id = f"v2-benchmark-{index}-{uuid.uuid4().hex[:12]}"
    _t0_ts = _capture_ts()
    _t0_wall_ms = int(_t0_ts[0] // 1_000_000)
    try:
        _command_start_for_origin = int(os.environ.get("COMFYMODAL_COMMAND_START_UNIX_MS", ""))
    except (TypeError, ValueError):
        _command_start_for_origin = _t0_wall_ms
    _t0_perf = time.perf_counter()
    # T1: local receive (this runner is itself the local receiver)
    _t1_wall_ns, _t1_mono_ns = _capture_ts()
    request_origin_info = {
        "request_id": _req_id,
        "trigger_source": "benchmark",
        "ui_run_triggered_wall_unix_ms": _t0_wall_ms,
        "command_start_unix_ms": _command_start_for_origin,
        "benchmark_run_index": index,
        "local_receive_wall_ns": _t1_wall_ns,
        "local_receive_mono_ns": _t1_mono_ns,
        "benchmark_iteration_selected_wall_ns": _t0_ts[0],
        "benchmark_iteration_selected_mono_ns": _t0_ts[1],
    }
    if _extra_origin:
        request_origin_info.update(_extra_origin)
    # Semantic-neutral conditioning-cache nonce (benchmark-only): carried in
    # the request origin so the remote exact-cache key can be isolated per
    # run WITHOUT touching the workflow/prompt/seed/sampler.  Empty when the
    # option is unused -> request_origin_info is unchanged (zero behavior
    # change).  Covers every _run_one-based mode (default loop, variance-
    # cold/matrix, transfer/backing/provider/host/region AB, acceptance).
    _cc_nonce_origin = _conditioning_cache_nonce_arg()
    if _cc_nonce_origin:
        request_origin_info["conditioning_cache_nonce"] = _cc_nonce_origin
        # D10 nonce-isolation guard: a nonce-carrying measurement MUST target
        # the D1-primed deployment.  Fail closed when the env pins a different
        # app or no primed identity exists; otherwise resolve the transport's
        # COMFYMODAL_V2_APP_NAME from the primed identity so the request can
        # never silently land on the legacy default app (the D10 failure: the
        # old app's baked runtime ignores the nonce -> canonical key -> warm
        # exact_hit with encode_calls=0).
        _resolve_nonce_target_app()
    # Request-level experiment arms (unet_transfer / vae_overlap /
    # png_encode / conditioning_hit) travel as allowlisted request-origin
    # env keys so the container applies the arm per-request.  Baseline arms
    # add nothing (deployment defaults apply).  restore_memory is
    # deployment-level and never travels per-request.
    _experiment_origin = _experiment_origin_overrides()
    if _experiment_origin:
        request_origin_info.update(_experiment_origin)
    prompt_id = _req_id  # request_id == prompt_id

    # Mirror the ComfyUI server's full node registry before any plan build:
    # a base-only registry would reject comfy_extras nodes at validation and
    # fingerprint the wrong surface.
    #
    # D1 zero-gap: when the persisted registry-proof/validation store covers
    # this workflow, plan construction needs no live registry (fast path).
    # Otherwise load the full registry once (the plan build then persists the
    # store entry so later commands are fast).
    _registry_store_hit = _registry_proof_store_covers(
        workflow, modal_options=modal_options,
    )
    if _registry_store_hit:
        print("[v2.harness] registry_load=skipped store_hit=yes", flush=True)
        _registry_load_ms = 0.0
    else:
        _registry_load_t0 = time.perf_counter()
        if not await _ensure_full_node_registry():
            raise RuntimeError(
                "[v2.harness] node registry initialization failed; "
                "cannot build an authoritative plan validation proof"
            )
        _registry_load_ms = round((time.perf_counter() - _registry_load_t0) * 1000.0, 3)

    # ═══════════════════════════════════════════════════════════════════════
    # Prefix timestamp capture: worker_start → plan_build_start
    #
    # Events are captured as (wall_unix_ns, monotonic_ns) tuples BEFORE the
    # RuntimeTrace exists, then emitted via emit_at() after trace creation.
    # This yields a strict non-overlapping partition:
    #
    #   ws [gap1] norm_start [normalize] norm_end [gap2] rtc_start [construct]
    #   rtc_end [gap3] bc_start [copy] bc_end [gap4] cid_start [gen] cid_end
    #   [gap5] bep_call [args] plan_build_start
    #
    # Each gap/span maps to exactly one breakdown field.
    # ═══════════════════════════════════════════════════════════════════════

    # T_worker: first executable boundary (no queue)
    _ws_ts = _capture_ts()

    # T_normalize_start / T_normalize_end
    _norm_ts = _capture_ts()
    production_options = normalize_production_options(modal_options)
    _norm_end_ts = _capture_ts()

    # T_trace_construct_start / T_trace_construct_end
    _rtc_start_ts = _capture_ts()
    runtime_trace = RuntimeTrace(request_id=prompt_id, process="local")
    runtime_trace.set_metadata(request_origin_info=request_origin_info)
    _rtc_end_ts = _capture_ts()

    # ── Emit all captured timestamps in temporal order ──
    runtime_trace.emit_at("benchmark_iteration_selected",
        wall_unix_ns=_t0_ts[0], monotonic_ns=_t0_ts[1], phase="local",
        metadata={"benchmark_run_index": index})
    runtime_trace.emit_at("local_worker_submit",
        wall_unix_ns=_t1_wall_ns, monotonic_ns=_t1_mono_ns, phase="local",
        metadata={"queue_depth": 0, "submit_mechanism": "direct_asyncio",
                  "benchmark_run_index": index})
    runtime_trace.emit_at("worker_start",
        wall_unix_ns=_ws_ts[0], monotonic_ns=_ws_ts[1],
        phase="local", metadata={
            "pid": os.getpid(),
            "thread_native_id": threading.get_native_id(),
            "request_id": _req_id,
        })
    runtime_trace.emit_at("normalize_production_options_start",
        wall_unix_ns=_norm_ts[0], monotonic_ns=_norm_ts[1], phase="local")
    runtime_trace.emit_at("normalize_production_options_end",
        wall_unix_ns=_norm_end_ts[0], monotonic_ns=_norm_end_ts[1], phase="local")
    runtime_trace.emit_at("runtime_trace_construct_start",
        wall_unix_ns=_rtc_start_ts[0], monotonic_ns=_rtc_start_ts[1], phase="local")
    runtime_trace.emit_at("trace_construct_end",
        wall_unix_ns=_rtc_end_ts[0], monotonic_ns=_rtc_end_ts[1], phase="local")

    # T_benchmark_options_copy_start / T_benchmark_options_copy_end
    _bc_ts = _capture_ts()
    runtime_trace.emit_at("benchmark_options_copy_start",
        wall_unix_ns=_bc_ts[0], monotonic_ns=_bc_ts[1], phase="local")
    _bench_modal_options = dict(modal_options)
    if bypass_cpu_snapshot_unet:
        _existing_flags = _bench_modal_options.get("compatibility_flags", {})
        if isinstance(_existing_flags, dict):
            _bench_modal_options["compatibility_flags"] = dict(_existing_flags)
        else:
            _bench_modal_options["compatibility_flags"] = {}
        _bench_modal_options["compatibility_flags"]["diagnostic_bypass_cpu_snapshot_unet"] = True
    _bc_end_ts = _capture_ts()
    runtime_trace.emit_at("benchmark_options_copy_end",
        wall_unix_ns=_bc_end_ts[0], monotonic_ns=_bc_end_ts[1], phase="local")

    # T_client_id_generation_start / T_client_id_generation_end
    _cid_ts = _capture_ts()
    runtime_trace.emit_at("client_id_generation_start",
        wall_unix_ns=_cid_ts[0], monotonic_ns=_cid_ts[1], phase="local")
    _bench_client_id = f"v2-benchmark-client-{uuid.uuid4().hex[:8]}"
    _cid_end_ts = _capture_ts()
    runtime_trace.emit_at("client_id_generation_end",
        wall_unix_ns=_cid_end_ts[0], monotonic_ns=_cid_end_ts[1], phase="local")

    # T_build_execution_plan_call_start
    _bep_call_ts = _capture_ts()
    runtime_trace.emit_at("build_execution_plan_call_start",
        wall_unix_ns=_bep_call_ts[0], monotonic_ns=_bep_call_ts[1], phase="local")
    plan = build_execution_plan(
        workflow,
        prompt_id=prompt_id,
        client_id=_bench_client_id,
        modal_options=_bench_modal_options,
        production_options=production_options if production_options.get("enabled") else None,
        gpu=GPU,
        workspace=workspace,
        request_metadata={"benchmark_run_index": index, "benchmark_app": APP_NAME,
                          "__request_origin_info__": request_origin_info},
        trace=runtime_trace,
        validate=False,
        collect_validation_proof=_PLAN_VALIDATION_PROOF,
        comfyui_root=_COMFYUI_ROOT_DIR,
    )

    _mode = "bypass" if bypass_cpu_snapshot_unet else "reuse"
    print(f"cpu_snapshot_unet_mode={_mode}", flush=True)

    # ── execute_plan call ─────────────────────────────────────────────────
    _ep_call_wall_ns, _ep_call_mono_ns = _capture_ts()
    runtime_trace.emit_at("execute_plan_call_start",
        wall_unix_ns=_ep_call_wall_ns, monotonic_ns=_ep_call_mono_ns,
        phase="local")
    started = time.perf_counter()
    print("[v2.benchmark] phase=execute_plan_start", flush=True)
    result = await execute_plan(
        plan,
        transport=transport,
        restore_publisher=_test_restore_publisher if _test_restore_publisher is not None else _resolve_restore_publisher(transport, workspace),
        profile_setter=_test_profile_setter if _test_profile_setter is not None else set_active_warmup_profile,
        profile_checker=_test_profile_checker if _test_profile_checker is not None else check_active_warmup_profile,
        gpu=GPU,
        workspace=workspace,
        trace=runtime_trace,
    )
    _validate_remote_profile(result)
    _response_wall_ns, _response_mono_ns = _capture_ts()
    wall_ms = (time.perf_counter() - started) * 1000.0
    # ── Production-adjusted total wall (benchmark-only instrumentation) ──
    # TOTAL WALL (wall_ms) already excludes Modal scheduling (it is measured
    # from execute_plan entry) and never subtracts pre-Python/Python restore.
    # It DOES include the host-side node-registry init this runner performs
    # before plan build.  The production-adjusted figure subtracts only that
    # registry init — never scheduling, never restore — and is emitted only
    # when both inputs are present.
    _node_registry_init_ms = None
    if (
        isinstance(_NODE_REGISTRY_START_NS, int)
        and isinstance(_NODE_REGISTRY_END_NS, int)
        and not isinstance(_NODE_REGISTRY_START_NS, bool)
        and not isinstance(_NODE_REGISTRY_END_NS, bool)
    ):
        _nri_delta_ns = _NODE_REGISTRY_END_NS - _NODE_REGISTRY_START_NS
        if _nri_delta_ns >= 0:
            _node_registry_init_ms = round(_nri_delta_ns / 1_000_000.0, 3)
    identity = _identity(result)
    _expected_app = os.environ.get("COMFYMODAL_V2_APP_NAME", APP_NAME) or APP_NAME
    if identity.get("app_name") and identity.get("app_name") != _expected_app:
        raise RuntimeError(f"V2 run {index} returned app {identity['app_name']!r}, expected {_expected_app!r}")
    runtime_shape_artifact = _validate_runtime_shape(result, identity)
    _host_diag = result.get("host_diagnostics") if isinstance(result, dict) else None
    if not isinstance(_host_diag, dict):
        _host_diag = {}
    _ube = result.get("unet_backing_evidence") if isinstance(result, dict) else None
    if not isinstance(_ube, dict):
        _ube = {}
    artifact = {
        "run_index": index,
        "request_id": prompt_id,
        "prompt_id": prompt_id,
        "target": {"app_name": APP_NAME, "class_name": CLASS_NAME, "gpu": GPU},
        "identity": identity,
        "host_diagnostics": _host_diag,
        "unet_backing_evidence": _ube,
        "runtime_shape": runtime_shape_artifact,
        "event_types": ["result"],
        "timing": _timing(
            result,
            wall_ms,
            command_start_unix_ms=_command_start_for_origin,
            response_received_unix_ns=_response_wall_ns,
        ),
        "result": result,
    }
    _command_start_ms: int | None = None
    if index == 0:
        try:
            _command_start_ms = int(os.environ.get("COMFYMODAL_COMMAND_START_UNIX_MS", ""))
        except (TypeError, ValueError):
            _command_start_ms = None
    if _command_start_ms is None:
        _command_start_ms = _t0_wall_ms
    _waterfall = build_waterfall(
        result=result,
        timing=artifact["timing"],
        wall_ms=wall_ms,
        command_start_unix_ms=_command_start_ms,
        response_received_unix_ns=_response_wall_ns,
        run_label=f"run {index + 1}",
    )
    artifact["waterfall"] = waterfall_to_dict(_waterfall)
    # ── Local waterfall rebuild with the Modal restore-begin boundary ──
    # Instrumentation/reporting ONLY: rebuilds the waterfall with the platform
    # "Restoring Function from memory snapshot" boundary (result-carried value
    # first, else a Modal app log tail), stores it as ``waterfall_local``
    # (never touching the remote-built ``waterfall``) and prints a
    # reconciliation block.  Every failure degrades gracefully.
    try:
        reconcile_waterfall_local(
            result,
            artifact["timing"],
            command_start_unix_ms=_command_start_ms,
            response_received_unix_ns=_response_wall_ns,
            wall_ms=wall_ms,
            run_label=f"run {index + 1} (local reconcile)",
            existing_waterfall=artifact["waterfall"],
        )
    except Exception as _reconcile_exc:  # noqa: BLE001
        print(
            f"WATERFALL RECONCILIATION (local rebuild) unavailable: "
            f"{type(_reconcile_exc).__name__}",
            flush=True,
        )
    artifact["waterfall_local"] = (
        result.get("waterfall_local") if isinstance(result, dict) else None
    )
    # ── Production-adjusted total wall (benchmark-only instrumentation) ──
    # TOTAL WALL is the host-reconciled waterfall's total_wall_ms (command→
    # response MINUS Modal scheduling, already excluded by the waterfall).
    # The host-side node-registry init is benchmark-only and subtracted here;
    # pre-Python restore, Python restore, and application work are NOT
    # subtracted.  wall_ms (execute_plan perf duration) is NOT used as the
    # base because it includes scheduling.  Emitted only when both inputs
    # are present.
    _wf_total_wall_ms = None
    _wf_local = artifact.get("waterfall_local")
    if isinstance(_wf_local, dict):
        _wf_total_wall_ms = _wf_local.get("total_wall_ms")
    if _wf_total_wall_ms is None:
        _wf_total_wall_ms = artifact["waterfall"].get("total_wall_ms")
    production_adjusted_total_wall_ms = None
    if _wf_total_wall_ms is not None and _node_registry_init_ms is not None:
        production_adjusted_total_wall_ms = round(
            float(_wf_total_wall_ms) - _node_registry_init_ms, 3
        )
    artifact["production_adjusted_total_wall_ms"] = production_adjusted_total_wall_ms
    (output_dir / f"run_{index}.json").write_text(
        json.dumps(artifact, default=str, indent=2), encoding="utf-8"
    )
    # Production-adjusted total wall (see the computation near wall_ms): TOTAL
    # WALL minus the host-side node-registry init only.  Printed per run and
    # persisted into run_<i>.json under "production_adjusted_total_wall_ms";
    # absent when either input is missing.
    print(
        f"production_adjusted_total_wall_ms="
        f"{_fmt_v2_metric(production_adjusted_total_wall_ms)}",
        flush=True,
    )

    # ── Full trace bundle download handoff ─────────────────────────────
    # Run file is safely committed to disk.  Now process any
    # full_trace_artifact from the remote result:
    #   - status == "ready"   → invoke downloader, write full_trace_download.json
    #   - status == "error"   → raise RuntimeError (caught below, run file preserved)
    #   - absent              → no-op (preserves existing behaviour)
    #
    # Errors are caught and stored in the artifact so they do not abort
    # remaining benchmark runs.  The main loop collects all errors and
    # exits non-zero at the end.
    try:
        await _handle_full_trace_artifact(
            result, output_dir, workspace, transport,
            _test_trace_downloader=_test_trace_downloader,
        )
    except Exception as exc:
        artifact["_trace_handoff_error"] = str(exc)[:300]
        (output_dir / f"run_{index}.json").write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )

    # ── Experiment-result persistence (V2 A/B campaign) ────────────────
    # Deterministic per-run record: best-effort, additive, never touches the
    # existing run file or the artifact.  One save per run.
    try:
        from comfymodal_runtime.experiment_result_store import build_run_record, save_experiment_run
        _exp_args = globals().get("_EXPERIMENT_ARGS")
        _exp_role = (
            getattr(_exp_args, "run_role", "sample")
            if _exp_args is not None else "sample"
        ) or "sample"
        _run_index_attr = (
            getattr(_exp_args, "run_index", None) if _exp_args is not None else None
        )
        _record = build_run_record(
            artifact,
            request_id=artifact.get("request_id", artifact.get("prompt_id", "")),
            experiment=(getattr(_exp_args, "experiment", "") if _exp_args is not None else "") or "",
            arm=(getattr(_exp_args, "arm", "") if _exp_args is not None else "") or "",
            run_ordinal=(
                int(_run_index_attr) if _run_index_attr is not None else index + 1
            ),
            run_role=_exp_role,
            retained=(_exp_role != "validation_discard"),
            discard_reason=(
                "first_post_snapshot_run" if _exp_role == "validation_discard" else ""
            ),
        )
        _saved = save_experiment_run(_record, output_dir=output_dir)
        globals()["_EXPERIMENT_RECORDS"].append(_record)
        print(f"[v2.experiment] saved={_saved}", flush=True)
    except Exception as _exc:  # noqa: BLE001
        print(
            f"[v2.experiment] save skipped: {type(_exc).__name__}: {_exc}",
            flush=True,
        )

    print(json.dumps({
        "run_index": index,
        "request_id": prompt_id,
        "identity": identity,
        "runtime_shape": runtime_shape_artifact,
        "timing": artifact["timing"],
    }, default=str))
    # ── Persistence-drain join (deterministic trailing-event collection) ──
    # The transport drains the post-result stream in the background to capture
    # the remote trailing persistence event.  Join it here with a bounded
    # timeout so the process never exits with a pending drain task, then merge
    # the received persistence outcome into the structured artifact/trace
    # (never into caller-visible stages or the result/output descriptor).
    try:
        from comfymodal_runtime.modal_transport import (
            join_persistence_drain,
            get_persistence_status,
        )
        await join_persistence_drain(prompt_id, timeout=_PERSISTENCE_DRAIN_JOIN_TIMEOUT)
        _persist_record = get_persistence_status(prompt_id)
        if _persist_record:
            artifact["persistence"] = _persist_record
        _merge_deferred_commit_trace_events(result, runtime_trace)
    except Exception as _persist_exc:  # noqa: BLE001
        print(
            f"[v2.benchmark] persistence drain join failed: "
            f"{type(_persist_exc).__name__}: {_persist_exc}",
            flush=True,
        )
    # Per-run waterfall is always printed (never deferred), so the single-run
    # path is not silenced by the post-loop renderer.  Prefer the host-reconciled
    # rebuild (TOTAL WALL denominator) when it exists; the remote-built report
    # stays available in the artifact.
    _print_waterfall = artifact.get("waterfall_local") or _waterfall
    if artifact.get("waterfall_local"):
        print("WATERFALL (host-reconciled)", flush=True)
    else:
        print(
            "WATERFALL (host reconcile unavailable - remote/partial report below)",
            flush=True,
        )
    print(render_waterfall(_print_waterfall), flush=True)
    # ── Host-side provenance re-emission (RUN-1 gate) ─────────────────────
    # Remote (Modal container) stdout never reaches the captured benchmark
    # log, so after every completed run the host re-emits the executor /
    # conditioning breakdowns and the PNG provenance from the run artifact.
    # Each line is best-effort: a missing event yields None (skipped) and any
    # malformed payload degrades to a skip message, never an abort.
    for _host_fmt in (
        format_host_prompt_executor_breakdown,
        format_host_conditioning_breakdown,
        format_host_folder_warm,
        format_host_input_types_warm,
        format_host_png_output,
    ):
        try:
            _host_line = _host_fmt(artifact)
        except Exception as _host_exc:  # noqa: BLE001
            print(
                f"[v2.host_breakdown] {_host_fmt.__name__} skipped: "
                f"{type(_host_exc).__name__}: {_host_exc}",
                flush=True,
            )
            continue
        if _host_line:
            print(_host_line, flush=True)
    # ── Host submission timeline breakdown (V2 pass 2 instrumentation) ────
    # Single-line per-run record decomposing the proven ~17s
    # local_receive → submission registry-init cost (benchmark-only) and the
    # scheduling interval from the reconciled report.  Bounded: a missing
    # event/stamp never breaks the run.
    try:
        from comfymodal_runtime.modal_restore_boundary import (
            extract_restore_begin_from_result as _extract_restore_begin,
        )
        try:
            _command_start_for_breakdown = int(
                os.environ.get("COMFYMODAL_COMMAND_START_UNIX_MS", "")
            )
        except (TypeError, ValueError):
            _command_start_for_breakdown = None
        _sched_report = artifact.get("waterfall_local")
        if not isinstance(_sched_report, dict):
            _sched_report = artifact.get("waterfall")
        if not isinstance(_sched_report, dict):
            _sched_report = None
        _scheduling_ms = None
        if _sched_report is not None:
            _sched_val = _sched_report.get("scheduling_ms")
            if isinstance(_sched_val, (int, float)) and not isinstance(_sched_val, bool):
                _scheduling_ms = float(_sched_val)
        _scheduling_source = "unavailable"
        try:
            _restore_begin_carried = _extract_restore_begin(
                result, artifact.get("timing")
            )
        except Exception:  # noqa: BLE001
            _restore_begin_carried = None
        if _restore_begin_carried is not None:
            _scheduling_source = "result_carried"
        elif (
            _sched_report is not None
            and "modal_restore_begin_unavailable"
            not in (_sched_report.get("boundary_flags") or ())
        ):
            _scheduling_source = "modal_app_log"
        _host_submission_line = build_host_submission_breakdown_line(
            artifact,
            command_start_unix_ms=_command_start_for_breakdown,
            python_first_line_ns=_PYTHON_FIRST_LINE_NS,
            local_receive_wall_ns=_t1_wall_ns,
            node_registry_start_ns=_NODE_REGISTRY_START_NS,
            node_registry_end_ns=_NODE_REGISTRY_END_NS,
            scheduling_ms=_scheduling_ms,
            scheduling_source=_scheduling_source,
        )
        print(_host_submission_line, flush=True)
        _cold_before_ms = None
        if _COLD_WAITS:
            _last = _COLD_WAITS[-1]
            if isinstance(_last, dict) and isinstance(_last.get("waited_mono_ms"), (int, float)):
                _cold_before_ms = float(_last["waited_mono_ms"])
        try:
            _trigger_line = build_trigger_to_submission_line(
                runtime_trace,
                origin=request_origin_info,
                transport_meta=runtime_trace._metadata,
                cold_wait_before_ms=_cold_before_ms,
            )
            print(_trigger_line, flush=True)
            # ── User-equivalent external-command clocks (D1 zero-gap) ──────
            # The three never-conflated clocks for the externally-invoked
            # benchmark command: process start (python_first_line) and the
            # user-equivalent command trigger (COMFYMODAL_COMMAND_START_UNIX_MS)
            # against both response receipt and the TRUE submit boundary
            # (modal_submission_attempt).  Registry-store state is reported
            # beside them so setup work stays attributable.
            _submission_attempt_wall_ns = None
            for _h_evt in (_host_trace_events(artifact) or []):
                if (
                    isinstance(_h_evt, dict)
                    and _h_evt.get("name") == "modal_submission_attempt"
                    and isinstance(_h_evt.get("wall_unix_ns"), (int, float))
                ):
                    _submission_attempt_wall_ns = int(_h_evt["wall_unix_ns"])
                    break
            _user_trigger_line = build_user_trigger_line(
                request_id=prompt_id,
                command_start_unix_ms=_command_start_for_breakdown,
                python_first_line_ns=_PYTHON_FIRST_LINE_NS,
                submission_attempt_wall_ns=_submission_attempt_wall_ns,
                response_received_wall_ns=_response_wall_ns,
                registry_store_hit=_registry_store_hit,
                registry_load_ms=_registry_load_ms,
            )
            print(_user_trigger_line, flush=True)
        except Exception as _trig_exc:  # noqa: BLE001
            print(
                f"[v2.trigger_to_submission] skipped: "
                f"{type(_trig_exc).__name__}: {_trig_exc}",
                flush=True,
            )
    except Exception as _sub_exc:  # noqa: BLE001
        print(
            f"[v2.host_submission_breakdown] skipped: "
            f"{type(_sub_exc).__name__}: {_sub_exc}",
            flush=True,
        )
    return artifact


def _extract_unet_runtime_state_event(
    result: dict[str, Any],
    stage: str,
) -> dict[str, Any] | None:
    """Extract the first ``unet_runtime_state`` trace event at *stage*.

    Returns the metadata dict, or ``None`` if not found.
    """
    trace_data = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace_data.get("events", []) if isinstance(trace_data, dict) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("name") != "unet_runtime_state":
            continue
        meta = event.get("metadata", {})
        if isinstance(meta, dict) and meta.get("stage") == stage:
            return meta
    return None


async def _run_ab_compare(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
) -> dict[str, Any]:
    """Run one reuse request and one bypass request, then compute A/B diff.

    Uses the same ``ModalTransport`` but the remote requests may execute
    in different container processes.  Extracts ``unet_runtime_state``
    trace events from each returned trace, validates identity, calls
    ``diff_unet_runtime_states`` locally, and saves the result.

    Raises ``RuntimeError`` when either state is missing or models differ.
    """
    # ── Run A (reuse) ───────────────────────────────────────────────────
    print("[v2.unet_ab] phase=reuse_start", flush=True)
    reuse_result = await _run_one(
        index=0, workflow=workflow, modal_options=modal_options,
        workspace=workspace, transport=transport, output_dir=output_dir,
        bypass_cpu_snapshot_unet=False,
    )
    reuse_meta = _extract_unet_runtime_state_event(
        reuse_result.get("result", {}), "snapshot_restored_post_retarget",
    )
    if reuse_meta is None:
        raise RuntimeError(
            "A/B diff: snapshot_restored_post_retarget state not found in reuse result"
        )

    # ── Run B (bypass) ──────────────────────────────────────────────────
    print("[v2.unet_ab] phase=bypass_start", flush=True)
    bypass_result = await _run_one(
        index=1, workflow=workflow, modal_options=modal_options,
        workspace=workspace, transport=transport, output_dir=output_dir,
        bypass_cpu_snapshot_unet=True,
    )
    bypass_meta = _extract_unet_runtime_state_event(
        bypass_result.get("result", {}), "normal_loader_ready",
    )
    if bypass_meta is None:
        raise RuntimeError(
            "A/B diff: normal_loader_ready state not found in bypass result"
        )

    # ── Validate identity match ─────────────────────────────────────────
    reuse_identity = str(reuse_meta.get("unet_identity", ""))
    bypass_identity = str(bypass_meta.get("unet_identity", ""))
    reuse_wd = str(reuse_meta.get("requested_weight_dtype", ""))
    bypass_wd = str(bypass_meta.get("requested_weight_dtype", ""))
    if reuse_identity != bypass_identity:
        raise RuntimeError(
            f"A/B diff: UNET identity mismatch "
            f"reuse={reuse_identity!r} bypass={bypass_identity!r}"
        )
    if reuse_wd != bypass_wd:
        raise RuntimeError(
            f"A/B diff: weight_dtype mismatch "
            f"reuse={reuse_wd!r} bypass={bypass_wd!r}"
        )

    # ── Compute diff ────────────────────────────────────────────────────
    snapshot_state = dict(reuse_meta.get("state", {})) if isinstance(reuse_meta.get("state"), dict) else {}
    normal_state = dict(bypass_meta.get("state", {})) if isinstance(bypass_meta.get("state"), dict) else {}
    diff = diff_unet_runtime_states(snapshot_state, normal_state)

    # ── Print and save ──────────────────────────────────────────────────
    _diff_json = json.dumps(diff, default=str, separators=(",", ":"), sort_keys=True)
    print(
        f"[v2.unet_runtime_diff] "
        f"field_count={len(diff)} "
        f"fields={_diff_json}",
        flush=True,
    )

    ab_artifact = {
        "unet_identity": reuse_identity,
        "requested_weight_dtype": reuse_wd,
        "reuse_state": snapshot_state,
        "bypass_state": normal_state,
        "diff": diff,
        "field_count": len(diff),
    }
    (output_dir / "unet_runtime_diff.json").write_text(
        json.dumps(ab_artifact, default=str, indent=2), encoding="utf-8",
    )
    print(
        json.dumps({"ab_diff": {"field_count": len(diff), "output": str(output_dir / "unet_runtime_diff.json")}}, default=str),
    )
    return ab_artifact


# ═══════════════════════════════════════════════════════════════════════════
# Acceptance-mode helpers
# ═══════════════════════════════════════════════════════════════════════════


def _trace_event(result: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Return the first trace event with *name*, or None."""
    trace_data = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace_data.get("events", []) if isinstance(trace_data, dict) else []
    for event in events:
        if isinstance(event, dict) and event.get("name") == name:
            return event
    return None


def _event_metadata(event: dict[str, Any] | None, key: str | None = None, default: Any = None) -> Any:
    """Read a metadata key from a trace event dict.
    If *key* is None, returns the entire metadata dict (or default).
    """
    if event is None:
        return default
    meta = event.get("metadata", {})
    if not isinstance(meta, dict):
        return default
    if key is None:
        return meta
    return meta.get(key, default)


def _event_mono_ns(result: dict[str, Any], name: str) -> int | None:
    """Return monotonic_ns of the first event with *name*, or None."""
    ev = _trace_event(result, name)
    if ev is None:
        return None
    val = ev.get("monotonic_ns")
    return int(val) if isinstance(val, (int, float)) else None


def _event_wall_ns(result: dict[str, Any], name: str) -> int | None:
    """Return wall_unix_ns of the first event with *name*, or None."""
    ev = _trace_event(result, name)
    if ev is None:
        return None
    val = ev.get("wall_unix_ns")
    return int(val) if isinstance(val, (int, float)) else None


def _mono_delta_ms(result: dict[str, Any], start: str, end: str) -> float | str | None:
    """Compute end - start in ms using monotonic_ns."""
    s = _event_mono_ns(result, start)
    e = _event_mono_ns(result, end)
    if s is None or e is None:
        return None
    delta = e - s
    if delta < 0:
        return "invalid_negative"
    return round(delta / 1_000_000, 3)


def _wall_delta_ms(result: dict[str, Any], start: str, end: str) -> float | str | None:
    """Compute end - start in ms using wall_unix_ns."""
    s = _event_wall_ns(result, start)
    e = _event_wall_ns(result, end)
    if s is None or e is None:
        return None
    delta = e - s
    if delta < 0:
        return "invalid_negative"
    return round(delta / 1_000_000, 3)


def _extract_restore_timing(result: dict[str, Any]) -> dict[str, Any]:
    """Extract restore_timing from result."""
    rt = result.get("_restore_timing")
    if isinstance(rt, dict):
        return rt
    trace = result.get("trace", {})
    if isinstance(trace, dict):
        rt2 = trace.get("_restore_timing")
        if isinstance(rt2, dict):
            return rt2
    return {}


def _extract_images(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract image descriptors from result."""
    images = result.get("images", [])
    if isinstance(images, list):
        return images
    trace = result.get("trace", {})
    if isinstance(trace, dict):
        im2 = trace.get("images", [])
        if isinstance(im2, list):
            return im2
    return []


async def _read_remote_asset(
    handle: Any,
    backend_path: str,
    expected_sha256: str,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Read an output asset from the remote Modal volume.

    Returns dict with ``byte_count``, ``sha256``, ``data``, and ``fetch_ms``.
    Raises on failure.
    """
    t0 = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                handle.read_output_asset.remote,
                backend_path,
                expected_sha256,
            ),
            timeout=timeout,
        )
    except Exception as exc:
        raise RuntimeError(
            f"asset fetch failed backend_path={backend_path!r} "
            f"expected_sha256={expected_sha256!r}: {exc}"
        ) from exc
    fetch_ms = (time.perf_counter() - t0) * 1000.0
    if not isinstance(result, dict):
        raise RuntimeError(
            f"asset fetch returned non-dict: {type(result).__name__}"
        )
    data = result.get("data")
    if not data:
        raise RuntimeError(
            f"asset fetch returned empty data for {backend_path!r}"
        )
    actual_sha256 = result.get("sha256", "")
    if expected_sha256 and actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"asset SHA mismatch: expected {expected_sha256}, got {actual_sha256}"
        )
    return {
        "backend_path": backend_path,
        "expected_sha256": expected_sha256,
        "actual_sha256": actual_sha256,
        "byte_count": result.get("byte_count", len(data)),
        "fetch_ms": round(fetch_ms, 3),
    }


def _extract_acceptance_timing(
    result: dict[str, Any],
    trigger_to_modal_entry_ms: float | None = None,
    wall_ms: float = 0.0,
) -> dict[str, Any]:
    """Extract comprehensive timing fields for acceptance reporting."""
    restore_timing = _extract_restore_timing(result)
    timing: dict[str, Any] = {
        "wall_ms": round(wall_ms, 1),
        "trigger_to_modal_entry_ms": trigger_to_modal_entry_ms,
        "method_entry_to_durable_result_ms": None,
        "trigger_to_durable_result_ms": None,
        "restore_total_ms": None,
        "dispatch_to_modal_entry_ms": None,
        "exec_start_to_cached_ms": None,
        "sampler_node_to_sampler_start_ms": None,
        "sampling_ms": None,
        "vae_decode_ms": None,
        "output_encode_ms": None,
        "snapshot_callback_age_at_restore_ms": None,
        "snapshot_callback_to_command_start_ms": None,
        "command_start_to_restore_start_ms": None,
        "sampler_node_id": None,
        "sampler_class_type": None,
        "sampler_identification_source": "unavailable",
        "sampler_node_to_sampling_start_ms": None,
    }

    # restore_total_ms
    rt_val = restore_timing.get("restore_total_ms")
    if isinstance(rt_val, (int, float)):
        timing["restore_total_ms"] = round(float(rt_val), 3)

    # Method entry = remote_method_entry for run_plan_stream
    _method_entry_mono = _event_mono_ns(result, "remote_method_entry")
    _method_entry_wall = _event_wall_ns(result, "remote_method_entry")
    # Plan received = run_plan_first_status_yield
    _plan_received_mono = _event_mono_ns(result, "run_plan_first_status_yield")
    # Output collect end = output_collect_end or output_persist_end (whichever later)
    _output_end_mono = _event_mono_ns(result, "output_persist_end")

    # dispatch_to_modal_entry_ms
    _local_submit_wall = _event_wall_ns(result, "modal_submit_start")
    if _local_submit_wall and _method_entry_wall:
        timing["dispatch_to_modal_entry_ms"] = round(
            (_method_entry_wall - _local_submit_wall) / 1_000_000, 3
        )

    # method_entry_to_durable_result_ms
    if _method_entry_mono and _output_end_mono:
        val = (_output_end_mono - _method_entry_mono) / 1_000_000
        if val >= 0:
            timing["method_entry_to_durable_result_ms"] = round(val, 3)

    # trigger_to_durable_result_ms (if trigger_to_modal_entry_ms is given)
    if trigger_to_modal_entry_ms is not None and timing.get("method_entry_to_durable_result_ms") is not None:
        timing["trigger_to_durable_result_ms"] = round(
            trigger_to_modal_entry_ms + timing["method_entry_to_durable_result_ms"], 3
        )

    # exec_start_to_cached_ms: execution_start -> execution_cached
    timing["exec_start_to_cached_ms"] = _mono_delta_ms(result, "execution_start", "execution_cached")

    # sampler_node_to_sampler_start_ms: milestone metadata
    _pre_sampler = _trace_event(result, "pre_sampler_stages")
    if _pre_sampler is not None:
        _ps_meta = _event_metadata(_pre_sampler)  # returns full metadata dict
        val = _ps_meta.get("sampler_node_to_sampler_start_ms")
        if isinstance(val, (int, float)):
            timing["sampler_node_to_sampler_start_ms"] = round(float(val), 3)
        timing["sampler_node_id"] = _ps_meta.get("sampler_node_id") or None
        timing["sampler_class_type"] = _ps_meta.get("sampler_class_type") or None
        timing["sampler_identification_source"] = _ps_meta.get(
            "sampler_identification_source", "unavailable"
        )
        timing["sampler_node_to_sampling_start_ms"] = timing.get(
            "sampler_node_to_sampler_start_ms"
        )

    _restore_age = restore_timing.get("snapshot_callback_age_at_restore_ms")
    timing["snapshot_callback_age_at_restore_ms"] = _restore_age
    _trace_meta = result.get("trace", {}).get("metadata", {}) if isinstance(result.get("trace"), dict) else {}
    timing["snapshot_callback_to_command_start_ms"] = result.get(
        "snapshot_callback_to_command_start_ms", _trace_meta.get("snapshot_callback_to_command_start_ms")
    )
    # Prefer the truthfully-named command_start_to_python_resume_ms; fall back
    # to the legacy command_start_to_restore_start_ms (same semantics).
    _python_resume_val = result.get("command_start_to_python_resume_ms")
    if _python_resume_val is None:
        _python_resume_val = _trace_meta.get("command_start_to_python_resume_ms")
    if _python_resume_val is None:
        _python_resume_val = result.get(
            "command_start_to_restore_start_ms", _trace_meta.get("command_start_to_restore_start_ms")
        )
    timing["command_start_to_restore_start_ms"] = _python_resume_val

    # sampling_ms
    _ss = _event_mono_ns(result, "sampling_start")
    _se = _event_mono_ns(result, "sampling_end")
    if _ss is not None and _se is not None:
        val = (_se - _ss) / 1_000_000
        if val >= 0:
            timing["sampling_ms"] = round(val, 3)

    # vae_decode_ms
    _vd_start = _event_mono_ns(result, "vae_decode_start")
    _vd_end = _event_mono_ns(result, "vae_decode_end")
    if _vd_start is not None and _vd_end is not None:
        val = (_vd_end - _vd_start) / 1_000_000
        if val >= 0:
            timing["vae_decode_ms"] = round(val, 3)

    # output_encode_ms
    _oe_start = _event_mono_ns(result, "output_encode_start")
    _oe_end = _event_mono_ns(result, "output_encode_end")
    if _oe_start is not None and _oe_end is not None:
        val = (_oe_end - _oe_start) / 1_000_000
        if val >= 0:
            timing["output_encode_ms"] = round(val, 3)

    # Clip preparation timings
    timing["clip_prepare_start_ms"] = _mono_delta_ms(result, "clip_prepare_start", "clip_prepare_end")

    # UNET demand/load/page-fault timings (from trace events)
    _unet_demand = _trace_event(result, "unet_gpu_demand_start")
    _unet_first_cuda = _trace_event(result, "unet_first_cuda_op")
    if _unet_first_cuda is not None:
        timing["unet_demand_to_first_forward_ms"] = _event_metadata(
            _unet_first_cuda, "elapsed_ms"
        )
        timing["demand_start_present"] = _event_metadata(
            _unet_first_cuda, "demand_start_present", 0
        )
    else:
        timing["unet_demand_to_first_forward_ms"] = _ABSENT_STR
        timing["demand_start_present"] = 0

    # Output commit ms
    _asset_diag = _trace_event(result, "output_persist_end")
    if _asset_diag is not None:
        _asset_meta = _event_metadata(_asset_diag)
        if isinstance(_asset_meta, dict):
            _commit_ms = _asset_meta.get("commit_ms") or _asset_meta.get("output_volume_commit_ms")
            if isinstance(_commit_ms, (int, float)):
                timing["output_commit_ms"] = round(float(_commit_ms), 3)
            elif _asset_meta.get("commit_status") == "pending":
                timing["output_commit_ms"] = None
                timing["commit_pending"] = True

    return timing


def _check_acceptance(
    run_label: str,
    result: dict[str, Any],
    timing: dict[str, Any],
    images: list[dict[str, Any]],
    asset_proofs: list[dict[str, Any]],
    *,
    is_fresh: bool = False,
    is_reused: bool = False,
    expected_restore_count: int | None = None,
    expected_request_count: int | None = None,
    expected_request_count_min: int | None = None,
    expected_instance_id: str | None = None,
    forbid_instance_id: str | None = None,
) -> list[str]:
    """Run acceptance checks for a single run. Returns list of failures (empty = pass).

    Identity proof uses ``restored_instance_id``, ``restore_count``, and
    ``request_count`` from the request-scoped ``remote_method_entry`` metadata.
    Absent/missing values fail explicitly — never default to "pass".

    * ``expected_restore_count`` — exact restore_count requirement
    * ``expected_request_count`` — exact request_count requirement (A, C fresh)
    * ``expected_request_count_min`` — minimum request_count (B reused, >= 2)
    * ``expected_instance_id`` — must match this restored_instance_id (B)
    * ``forbid_instance_id`` — must differ (C fresh)

    ``restore_count`` is cumulative per-instance from ``_v2_container_restore_count``
    and is 1 for every request within the same restore lifecycle.
    B's no-new-restore proof uses lifecycle event counting, not restore_count=0.
    """
    failures: list[str] = []

    # ── Unwrap artifact['result'] for trace/event inspection ──
    # In production acceptance mode, this function receives the artifact wrapper
    # (keys: identity, images, timing, asset_proofs, result).  The actual remote
    # result with the 'trace' key lives at result['result'].
    # Unwrap transparently so both direct (unit-test flat dict) and wrapped
    # (production artifact) callers work — trace/event helpers see the raw result.
    _ev_result: dict[str, Any] = result
    if isinstance(result, dict):
        _inner = result.get("result")
        if isinstance(_inner, dict) and "trace" in _inner:
            _ev_result = _inner

    # ── Identity checks ──
    identity = result.get("identity", {})
    restored_instance_id = str(identity.get("restored_instance_id", ""))
    restore_count = int(identity.get("restore_count", -1))
    request_count = int(identity.get("request_count", -1))

    if not restored_instance_id:
        failures.append(f"{run_label}: restored_instance_id is empty/absent")
    if expected_restore_count is not None and restore_count != expected_restore_count:
        failures.append(
            f"{run_label}: restore_count={restore_count}, expected={expected_restore_count}"
        )
    if expected_request_count is not None and request_count != expected_request_count:
        failures.append(
            f"{run_label}: request_count={request_count}, expected={expected_request_count}"
        )
    if expected_request_count_min is not None and request_count < expected_request_count_min:
        failures.append(
            f"{run_label}: request_count={request_count} < min={expected_request_count_min}"
        )
    if expected_instance_id and restored_instance_id != expected_instance_id:
        failures.append(
            f"{run_label}: restored_instance_id={restored_instance_id!r} != "
            f"expected={expected_instance_id!r}"
        )
    if forbid_instance_id and restored_instance_id == forbid_instance_id:
        failures.append(
            f"{run_label}: restored_instance_id={restored_instance_id!r} should differ "
            f"from forbid={forbid_instance_id!r}"
        )

    # ── Check no AsyncUsageWarning in result text or trace ──
    result_str = json.dumps(result, default=str)
    if "AsyncUsageWarning" in result_str or "SyncUsageWarning" in result_str:
        failures.append(f"{run_label}: contains AsyncUsageWarning/SyncUsageWarning")

    # ── base64 zero ──
    _attempts = result.get("output_attempts", [])
    if isinstance(_attempts, list):
        for attempt in _attempts:
            if isinstance(attempt, dict):
                enc = attempt.get("base64_encode_count", 0)
                dec = attempt.get("base64_decode_count", 0)
                if enc or dec:
                    failures.append(f"{run_label}: base64 count non-zero (enc={enc}, dec={dec})")

    # ── Asset proofs ──
    if not images:
        failures.append(f"{run_label}: no image descriptors found")
    else:
        for img in images:
            _aid = str(img.get("asset_id", ""))
            _backend = str(img.get("backend_path", ""))
            _identity = str(img.get("identity", ""))
            _expected_sha = _aid  # asset_id is the bare sha256
            if not _aid and not _backend:
                failures.append(f"{run_label}: image descriptor missing asset_id and backend_path")
                continue
            if not _expected_sha:
                failures.append(f"{run_label}: image descriptor has empty asset_id")
                continue
            # Verify asset proof was fetched
            _found = False
            for proof in asset_proofs:
                if proof.get("expected_sha256") == _expected_sha:
                    _found = True
                    if not proof.get("byte_count", 0):
                        failures.append(f"{run_label}: asset {_expected_sha[:16]} empty bytes")
                    if proof.get("actual_sha256") != _expected_sha:
                        failures.append(f"{run_label}: asset {_expected_sha[:16]} SHA mismatch")
                    break
            if not _found:
                failures.append(f"{run_label}: asset {_expected_sha[:16]} not fetched")

    # ── Timing gate: method_entry_to_durable_result <= 12s ──
    method_to_result = timing.get("method_entry_to_durable_result_ms")
    if isinstance(method_to_result, (int, float)):
        if method_to_result > 12000:
            failures.append(
                f"{run_label}: method_entry_to_durable_result_ms={method_to_result} > 12000"
            )
    else:
        failures.append(f"{run_label}: method_entry_to_durable_result_ms unavailable")

    # ── Timing gate: trigger_to_durable_result <= 18s (when dispatch <= 6s) ──
    dispatch_ms = timing.get("dispatch_to_modal_entry_ms")
    trigger_to_result = timing.get("trigger_to_durable_result_ms")
    if isinstance(dispatch_ms, (int, float)):
        if dispatch_ms <= 6000 and isinstance(trigger_to_result, (int, float)):
            if trigger_to_result > 18000:
                failures.append(
                    f"{run_label}: dispatch={dispatch_ms} <= 6000 but "
                    f"trigger_to_durable_result={trigger_to_result} > 18000"
                )

    # ── Fresh-request specific checks ──
    if is_fresh:
        # UNET first-CUDA timing must be present with nonzero elapsed
        _unet_elapsed = timing.get("unet_demand_to_first_forward_ms")
        _demand_present = timing.get("demand_start_present", 0)
        if not isinstance(_unet_elapsed, (int, float)):
            failures.append(f"{run_label}: unet_demand_to_first_forward_ms missing/absent ({_unet_elapsed})")
        elif _unet_elapsed < 0:
            failures.append(f"{run_label}: unet_demand_to_first_forward_ms negative ({_unet_elapsed})")
        if _demand_present != 1:
            failures.append(f"{run_label}: demand_start_present={_demand_present}, expected 1")

        # output_encode_ms must be present
        _oenc = timing.get("output_encode_ms")
        if not isinstance(_oenc, (int, float)):
            failures.append(f"{run_label}: output_encode_ms missing/absent ({_oenc})")

        # output_commit_ms may be absent when the commit is deferred
        # (commit_status pending/skipped, or timing.commit_pending set) —
        # 0.0 is valid (means zero latency).
        _oc = timing.get("output_commit_ms")
        _ocd = _ev_result.get("output_diagnostics") if isinstance(_ev_result, dict) else None
        if not isinstance(_ocd, dict):
            _ocd = result.get("output_diagnostics") if isinstance(result, dict) else None
        _commit_deferred = (
            timing.get("commit_pending") is True
            or (isinstance(_ocd, dict) and _ocd.get("commit_status") in ("pending", "skipped"))
        )
        if _oc is None and not _commit_deferred:
            failures.append(f"{run_label}: output_commit_ms missing/absent")

        # clip_preparation_timings_ms: structured dict from _restore_timing keys.
        # Informational — not a blocking check since clip load is a restore-stage
        # operation and may be per-container rather than per-request.

        # ── UNET/CLIP/VAE seeded check from seed_loader_cache_signatures evidence ──
        # Require executor_loader_cache_seed_end event containing diagnostics from
        # seed_loader_cache_signatures().  Every fresh request must have exactly
        # one non-conflicting decision per role: unet=seeded, clip=seeded,
        # vae=seeded (the production warmup profile declares a VAE, so the
        # retained snapshot VAE is seeded when the canonical identity matches).
        _seed_ev = _trace_event(_ev_result, "executor_loader_cache_seed_end")
        if _seed_ev is None:
            failures.append(
                f"{run_label}: seed_loader_cache_signatures evidence missing "
                "(no executor_loader_cache_seed_end trace event)"
            )
        else:
            _seed_meta = _event_metadata(_seed_ev, "diagnostics", {})
            if not isinstance(_seed_meta, dict) or not _seed_meta:
                failures.append(f"{run_label}: seed diagnostics empty or absent")
            else:
                # Collect decisions per role
                role_decisions: dict[str, list[str]] = {}
                role_node_ids: dict[str, list[str]] = {}
                for node_id, decision in _seed_meta.items():
                    if not isinstance(decision, dict):
                        continue
                    role = decision.get("role", "")
                    dec = decision.get("decision", "")
                    if role:
                        role_decisions.setdefault(role, []).append(dec)
                        role_node_ids.setdefault(role, []).append(node_id)

                # Each required role must be present
                for role in ("unet", "clip", "vae"):
                    if role not in role_decisions:
                        failures.append(
                            f"{run_label}: no {role} decision in seed evidence "
                            f"(present roles: {sorted(role_decisions)})"
                        )

                # No conflicting decisions within a role
                for role, decisions in role_decisions.items():
                    unique = set(decisions)
                    if len(unique) > 1:
                        failures.append(
                            f"{run_label}: conflicting {role} decisions: "
                            f"{dict(zip(role_node_ids[role], decisions))}"
                        )

                # Verify expected decision values for known roles
                _EXPECTED: dict[str, str] = {
                    "unet": "seeded",
                    "clip": "seeded",
                    "vae": "seeded",
                }
                for role, expected in _EXPECTED.items():
                    if role in role_decisions:
                        actual = role_decisions[role][0]
                        if actual != expected:
                            failures.append(
                                f"{run_label}: {role} decision={actual!r}, "
                                f"expected={expected!r}"
                            )

        # ── Step 3 evidence: snapshot graph seed apply ──
        # Every fresh request must carry the executor seed-apply seam result:
        # a snapshot_graph_seed_apply_end trace event attesting schema-v2,
        # within_budget, zero invalidations (fresh workflow == published seed),
        # sampler entries untouched, and an explicit fallback reason (the
        # marker must never silently claim "seeded").
        _seed_apply_ev = _trace_event(_ev_result, "snapshot_graph_seed_apply_end")
        if _seed_apply_ev is None:
            failures.append(
                f"{run_label}: snapshot_graph_seed_apply_end event missing"
            )
        else:
            _sa_meta = _event_metadata(_seed_apply_ev)
            if not isinstance(_sa_meta, dict) or not _sa_meta:
                failures.append(f"{run_label}: seed apply metadata empty or absent")
            else:
                _sa_schema = _sa_meta.get("schema", 0)
                if _sa_schema != 2:
                    failures.append(
                        f"{run_label}: seed apply schema={_sa_schema}, expected 2"
                    )
                if _sa_meta.get("within_budget") is not True:
                    failures.append(
                        f"{run_label}: seed apply within_budget not true "
                        f"({_sa_meta.get('within_budget')})"
                    )
                if _sa_meta.get("invalidated", -1) != 0:
                    failures.append(
                        f"{run_label}: seed apply invalidated="
                        f"{_sa_meta.get('invalidated')}, expected 0"
                    )
                if _sa_meta.get("sampler_untouched") is not True:
                    failures.append(
                        f"{run_label}: seed apply sampler_untouched not true "
                        f"({_sa_meta.get('sampler_untouched')})"
                    )
                if not isinstance(_sa_meta.get("fallback_reason"), str) or not _sa_meta.get("fallback_reason"):
                    failures.append(
                        f"{run_label}: seed apply fallback_reason missing"
                    )

        # exec_start_to_cached_ms must be present; threshold <= 500ms
        _esc = timing.get("exec_start_to_cached_ms")
        if not isinstance(_esc, (int, float)):
            failures.append(
                f"{run_label}: exec_start_to_cached_ms missing/absent ({_esc})"
            )
        elif _esc > 500:
            failures.append(f"{run_label}: exec_start_to_cached_ms={_esc} > 500")

        # sampler_node_to_sampler_start_ms must be present; threshold <= 1000ms
        _snss = timing.get("sampler_node_to_sampler_start_ms")
        if not isinstance(_snss, (int, float)):
            failures.append(
                f"{run_label}: sampler_node_to_sampler_start_ms missing/absent ({_snss})"
            )
        elif _snss > 1000:
            failures.append(f"{run_label}: sampler_node_to_sampler_start_ms={_snss} > 1000")

        # Require authoritative sampling_start and sampling_end events
        _sampling_start = _trace_event(_ev_result, "sampling_start")
        _sampling_end = _trace_event(_ev_result, "sampling_end")
        if _sampling_start is None:
            failures.append(f"{run_label}: sampling_start event missing")
        if _sampling_end is None:
            failures.append(f"{run_label}: sampling_end event missing")

        # Exactly 8 sigma-derived wrapper steps
        if _sampling_end is not None:
            _steps = _event_metadata(_sampling_end, "steps", None)
            if _steps is None:
                failures.append(
                    f"{run_label}: steps not found on sampling_end event"
                )
            elif _steps != 8:
                failures.append(f"{run_label}: steps={_steps}, expected 8")

        # Sampling ends before VAE decode starts
        _ss_ns = _event_mono_ns(_ev_result, "sampling_end")
        _vd_ns = _event_mono_ns(_ev_result, "vae_decode_start")
        if _ss_ns is not None and _vd_ns is not None:
            if _ss_ns >= _vd_ns:
                failures.append(
                    f"{run_label}: sampling_end ({_ss_ns}) >= vae_decode_start ({_vd_ns})"
                )

    # ── Reused request (B) specific checks ──
    # B must share A's restored_instance_id (same container, no new restore).
    # B must have request_count >= 2 (A's request plus this one).
    # B's restore_count is 1 (cumulative per-instance from _v2_container_restore_count).
    # No-new-restore proof: zero request-scoped restore lifecycle events.
    if is_reused:
        if request_count < 2:
            failures.append(f"{run_label} (reused): request_count={request_count} < 2")
        if not expected_instance_id:
            failures.append(f"{run_label} (reused): expected_instance_id not provided for comparison")
        # Lifecycle event check: count request-scoped events with names indicating
        # a restore lifecycle ran during this request.
        _req_id = str(identity.get("request_id", ""))
        _lifecycle_events = _trace_events_for_request(_ev_result, _req_id)
        _restore_lifecycle = [
            ev for ev in _lifecycle_events
            if isinstance(ev, dict) and ev.get("name", "") in (
                "remote_lifecycle_start", "remote_lifecycle_end",
                "restore_method_start", "restore_method_end",
                "gpu_invocation_submit", "startup",
            )
        ]
        if _restore_lifecycle:
            _names = [ev.get("name", "") for ev in _restore_lifecycle]
            failures.append(
                f"{run_label} (reused): found {len(_restore_lifecycle)} request-scoped "
                f"restore lifecycle events: {_names}"
            )

    return failures


def _extract_request_id(result: dict[str, Any]) -> str:
    """Extract the authoritative request_id from trace events."""
    for ev in result.get("trace", {}).get("events", []):
        if isinstance(ev, dict):
            meta = ev.get("metadata", {})
            if isinstance(meta, dict):
                rid = meta.get("request_id", "")
                if rid:
                    return str(rid)
    return ""


def _trace_events_for_request(result: dict[str, Any], request_id: str) -> list[dict[str, Any]]:
    """Return events belonging to the current request's execution.

    Most production RuntimeTrace events do NOT carry per-event ``request_id``
    in metadata — they are identified by their position AFTER the matching
    ``remote_method_entry`` event (which DOES carry request_id).

    Strategy: find the LAST ``remote_method_entry`` whose metadata.request_id
    matches *request_id*.  All events from that index onward belong to this
    request.  Events before that index are from startup/restore lifecycle
    (which share the same container_session_id but are not this request).
    """
    trace = result.get("trace", {})
    if not isinstance(trace, dict):
        return []
    events = trace.get("events", [])
    if not isinstance(events, list):
        return []

    # Find the index of the LAST remote_method_entry matching request_id
    boundary_idx = -1
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            continue
        if ev.get("name") != "remote_method_entry":
            continue
        meta = ev.get("metadata", {})
        if isinstance(meta, dict) and meta.get("request_id") == request_id:
            boundary_idx = i  # keep overwriting — we want the LAST match

    if boundary_idx < 0:
        return []

    # All events at or after boundary_idx belong to this request
    return events[boundary_idx:]


def _extract_identity_from_trace(result: dict[str, Any], request_id: str) -> dict[str, Any]:
    """Extract identity fields from the LAST ``remote_method_entry`` matching
    ``request_id`` (these DO carry per-event request_id).

    Reads ``restored_instance_id``, ``restore_count``, ``request_count``.
    Missing/absent values are reported as empty/0 — checks will fail on absence.
    """
    trace = result.get("trace", {})
    events = trace.get("events", []) if isinstance(trace, dict) else []
    if not isinstance(events, list):
        events = []
    instance_id = ""
    restore_count = 0
    request_count = 0
    runtime_fields: dict[str, Any] = {}
    # Find the LAST matching remote_method_entry (most recent before return)
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("name") != "remote_method_entry":
            continue
        meta = ev.get("metadata", {})
        if isinstance(meta, dict) and meta.get("request_id") == request_id:
            instance_id = str(meta.get("restored_instance_id", "")) or instance_id
            rc = meta.get("restore_count", 0)
            if isinstance(rc, (int, float)):
                restore_count = int(rc)
            rqc = meta.get("request_count", 0)
            if isinstance(rqc, (int, float)):
                request_count = int(rqc)
            for field in (
                "app_name",
                "class_name",
                "cpu",
                "memory_mb",
                "fingerprint",
                "runtime_shape",
                "runtime_shape_fingerprint",
                "runtime_shape_label",
                "stored_snapshot_model_order",
            ):
                if field in meta:
                    runtime_fields[field] = meta[field]
    return {
        "restored_instance_id": instance_id,
        "restore_count": restore_count,
        "request_count": request_count,
        "request_id": request_id,
        **runtime_fields,
    }


def _extract_acceptance_timing_scoped(
    result: dict[str, Any],
    request_id: str,
    *,
    trigger_to_modal_entry_ms: float | None = None,
    wall_ms: float = 0.0,
) -> dict[str, Any]:
    """Extract timing fields using boundary-based event selection.

    Most production RuntimeTrace events do NOT carry per-event ``request_id``.
    Instead, find the LAST ``remote_method_entry`` with matching ``request_id``
    (the request boundary marker), then use ALL monotonic timestamps from events
    at or after that position.  Events before the boundary (lifecycle, prior
    requests, startup) are excluded.
    """
    trace = result.get("trace", {})
    all_events = trace.get("events", []) if isinstance(trace, dict) else []
    if not isinstance(all_events, list):
        all_events = []

    # Find boundary index: last remote_method_entry matching request_id
    boundary_idx = -1
    for i, ev in enumerate(all_events):
        if not isinstance(ev, dict):
            continue
        if ev.get("name") != "remote_method_entry":
            continue
        meta = ev.get("metadata", {})
        if isinstance(meta, dict) and meta.get("request_id") == request_id:
            boundary_idx = i

    if boundary_idx < 0:
        # Fallback: use all events (may include lifecycle)
        events = all_events
    else:
        events = all_events[boundary_idx:]

    # Build monotonic timestamp map (last occurrence wins, skip zero/placeholder)
    ts: dict[str, int] = {}
    for ev in events:
        name = ev.get("name", "")
        mono = ev.get("monotonic_ns")
        if isinstance(mono, (int, float)) and mono > 0:
            ts[name] = int(mono)

    def _d(start: str, end: str) -> float | None:
        s = ts.get(start)
        e = ts.get(end)
        if s is None or e is None:
            return None
        delta = e - s
        if delta < 0:
            return None
        return round(delta / 1_000_000, 3)

    restore_timing = _extract_restore_timing(result)

    # Required field names per spec
    timing: dict[str, Any] = {
        "wall_ms": round(wall_ms, 1),
        "trigger_to_result_ms": trigger_to_modal_entry_ms,
        "dispatch_to_modal_entry_ms": None,
        "restore_total_ms": None,
        "method_entry_to_result_ms": _d("remote_method_entry", "output_persist_end"),
        "method_entry_to_durable_result_ms": _d("remote_method_entry", "output_persist_end"),
        "trigger_to_durable_result_ms": None,
        "exec_start_to_cached_ms": None,
        "sampler_node_to_sampler_start_ms": None,
        "sampling_ms": _d("sampling_start", "sampling_end"),
        "vae_decode_ms": _d("vae_decode_start", "vae_decode_end"),
        "output_encode_ms": _d("output_encode_start", "output_encode_end") or _d("output_encode_start", "output_persist_start"),
        "output_commit_ms": None,
        "clip_preparation_timings_ms": _d("clip_prepare_start", "clip_prepare_end"),
        "unet_demand_to_first_forward_ms": _ABSENT_STR,
        "demand_start_present": 0,
        "asset_fetch_ms": None,
        "snapshot_callback_age_at_restore_ms": restore_timing.get("snapshot_callback_age_at_restore_ms"),
        "snapshot_callback_to_command_start_ms": result.get("snapshot_callback_to_command_start_ms"),
        # Prefer the truthfully-named field; fall back to the legacy name
        # (identical semantics: command_start -> python resume).
        "command_start_to_restore_start_ms": (
            result.get("command_start_to_python_resume_ms")
            if result.get("command_start_to_python_resume_ms") is not None
            else result.get("command_start_to_restore_start_ms")
        ),
        "sampler_node_id": None,
        "sampler_class_type": None,
        "sampler_identification_source": "unavailable",
        "sampler_node_to_sampling_start_ms": None,
    }

    # restore_total_ms
    rt_val = restore_timing.get("restore_total_ms")
    if isinstance(rt_val, (int, float)):
        timing["restore_total_ms"] = round(float(rt_val), 3)

    # dispatch_to_modal_entry_ms: use wall clock from modal_submit_start to
    # the boundary remote_method_entry.  modal_submit_start may be before the
    # boundary in the merged trace (local event precedes remote).  Find it by
    # scanning ALL events for the LAST one (most recent for this request).
    _sub_wall = None
    _entry_wall = None
    for ev in all_events:
        if not isinstance(ev, dict):
            continue
        if ev.get("name") == "modal_submit_start":
            w = ev.get("wall_unix_ns")
            if isinstance(w, (int, float)):
                _sub_wall = int(w)
    # Find remote_method_entry at boundary
    if boundary_idx >= 0:
        b_ev = all_events[boundary_idx]
        w = b_ev.get("wall_unix_ns")
        if isinstance(w, (int, float)):
            _entry_wall = int(w)
    if _sub_wall and _entry_wall:
        delta = _entry_wall - _sub_wall
        if delta >= 0:
            timing["dispatch_to_modal_entry_ms"] = round(delta / 1_000_000, 3)

    # trigger_to_durable_result_ms
    if trigger_to_modal_entry_ms is not None and timing.get("method_entry_to_durable_result_ms") is not None:
        val = trigger_to_modal_entry_ms + timing["method_entry_to_durable_result_ms"]
        timing["trigger_to_durable_result_ms"] = round(val, 3)
        timing["trigger_to_result_ms"] = timing["trigger_to_durable_result_ms"]

    # exec_start_to_cached_ms from prompt_executor_milestones metadata
    for ev in events:
        if ev.get("name") == "prompt_executor_milestones":
            meta = ev.get("metadata", {})
            if isinstance(meta, dict):
                val = meta.get("execution_start_to_cached_ms")
                if isinstance(val, (int, float)) and val >= 0:
                    timing["exec_start_to_cached_ms"] = round(float(val), 3)

    # sampler_node_to_sampler_start_ms from pre_sampler_stages metadata
    for ev in events:
        if ev.get("name") == "pre_sampler_stages":
            meta = ev.get("metadata", {})
            if isinstance(meta, dict):
                val = meta.get("sampler_node_to_sampler_start_ms")
                if isinstance(val, (int, float)) and val >= 0:
                    timing["sampler_node_to_sampler_start_ms"] = round(float(val), 3)
                timing["sampler_node_id"] = meta.get("sampler_node_id") or None
                timing["sampler_class_type"] = meta.get("sampler_class_type") or None
                timing["sampler_identification_source"] = meta.get(
                    "sampler_identification_source", "unavailable"
                )
                timing["sampler_node_to_sampling_start_ms"] = timing.get(
                    "sampler_node_to_sampler_start_ms"
                )

    # unet_demand_to_first_forward_ms from unet_first_cuda_op
    for ev in events:
        if ev.get("name") == "unet_first_cuda_op":
            meta = ev.get("metadata", {})
            if isinstance(meta, dict):
                val = meta.get("elapsed_ms")
                if isinstance(val, (int, float)):
                    timing["unet_demand_to_first_forward_ms"] = round(float(val), 3)
                dp = meta.get("demand_start_present", 0)
                timing["demand_start_present"] = int(dp) if dp else 0

    # output_commit_ms from result output_diagnostics (commit happens async
    # after output_persist_end is emitted, so event metadata has None).
    _od = result.get("output_diagnostics", {})
    if isinstance(_od, dict):
        cm = (_od.get("output_volume_commit_ms") or _od.get("commit_ms")
              or _od.get("output_commit_overlap_ms"))
        if isinstance(cm, (int, float)) and cm >= 0:
            timing["output_commit_ms"] = round(float(cm), 3)
        if _od.get("commit_status") == "pending":
            timing["output_commit_ms"] = None
            timing["commit_pending"] = True
    # Fallback: check output_persist_end metadata directly
    if timing["output_commit_ms"] is None and not timing.get("commit_pending"):
        for ev in events:
            if ev.get("name") == "output_persist_end":
                meta = ev.get("metadata", {})
                if isinstance(meta, dict):
                    cm = meta.get("commit_ms") or meta.get("output_volume_commit_ms")
                    if isinstance(cm, (int, float)) and cm >= 0:
                        timing["output_commit_ms"] = round(float(cm), 3)

    # clip_preparation_timings: structured dict of available restore-stage
    # model/GPU preparation timings from _restore_timing.  These include
    # snapshot_restore, GPU state restoration, CUDA init, model reload, and
    # the full backend startup (which encompasses all model loading).
    _clip_keys = (
        "snapshot_restore_ms", "restore_gpu_state_ms", "cuda_init_ms",
        "reload_models_ms", "reload_runtime_state_ms", "backend_startup_ms",
        "restore_total_ms",
    )
    _clip_t: dict[str, Any] = {}
    for _ck in _clip_keys:
        _cv = restore_timing.get(_ck)
        if isinstance(_cv, (int, float)):
            _clip_t[str(_ck)] = round(float(_cv), 3)
    if _clip_t:
        timing["clip_preparation_timings_ms"] = _clip_t

    return timing


async def _run_acceptance_sequence(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
) -> dict[str, Any]:
    """Run the A/B/C acceptance sequence with full identity/asset/timing validation.

    Sequence:
      A: Fresh restored request.  Fetch all assets.
      B: IMMEDIATELY submit second request via same transport/handle (no cache clear,
         no wait).  Fetch all assets.
      Wait >= 6 seconds.
      C: Another fresh restored request.  Fetch all assets.

    Every run: fetch all image assets via remote read_output_asset, verify SHA.
    Summary includes all runs, failures, retries.
    """
    _APP_NAME = os.environ.get("COMFYMODAL_V2_APP_NAME", "stable-modal-comfy-v2-shadow")
    _CLASS_NAME = os.environ.get("COMFYMODAL_V2_CLASS_NAME", "ModalRuntimeEntrypointV2")
    _GPU = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000")
    os.environ["COMFYMODAL_V2_APP_NAME"] = _APP_NAME
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = _CLASS_NAME
    os.environ["COMFYMODAL_V2_GPU"] = _GPU

    WAIT_SECONDS = 25  # >= 6, increased for Modal scaledown scheduling variance
    ASSET_TIMEOUT = 30.0
    ACCEPTANCE_FAILED = False
    runs: list[dict[str, Any]] = []

    def _fmt_ts() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # ── Pre-resolve handle once (async-safe) to avoid AsyncUsageWarning ──
    # The ModalTransport._v2_handle does synchronous Client.from_credentials.
    # Run it in a thread to keep the async context clean.
    print("[v2.acceptance] phase=resolve_handle", flush=True)
    handle = await asyncio.to_thread(transport._v2_handle, workspace=workspace, gpu=_GPU)

    async def _run_acceptance_request(
        label: str, index: int,
    ) -> tuple[dict[str, Any], str]:
        _req_id = f"v2-accept-{label}-{uuid.uuid4().hex[:12]}"
        _t0_wall_ms = int(time.time() * 1000)
        try:
            _command_start_for_origin = int(os.environ.get("COMFYMODAL_COMMAND_START_UNIX_MS", ""))
        except (TypeError, ValueError):
            _command_start_for_origin = _t0_wall_ms
        _t1_wall_ns, _t1_mono_ns = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        request_origin_info = {
            "request_id": _req_id,
            "trigger_source": "acceptance_benchmark",
            "ui_run_triggered_wall_unix_ms": _t0_wall_ms,
            "command_start_unix_ms": _command_start_for_origin,
            "benchmark_run_index": index,
            "local_receive_wall_ns": _t1_wall_ns,
            "local_receive_mono_ns": _t1_mono_ns,
        }
        _ws_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        _norm_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        production_options = normalize_production_options(modal_options)
        _norm_end_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        _rtc_start_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace = RuntimeTrace(request_id=_req_id, process="local")
        runtime_trace.set_metadata(request_origin_info=request_origin_info)
        _rtc_end_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("worker_start",
            wall_unix_ns=_ws_ts[0], monotonic_ns=_ws_ts[1],
            phase="local", metadata={"pid": os.getpid(), "thread_native_id": threading.get_native_id(),
                                     "request_id": _req_id})
        runtime_trace.emit_at("normalize_production_options_start",
            wall_unix_ns=_norm_ts[0], monotonic_ns=_norm_ts[1], phase="local")
        runtime_trace.emit_at("normalize_production_options_end",
            wall_unix_ns=_norm_end_ts[0], monotonic_ns=_norm_end_ts[1], phase="local")
        runtime_trace.emit_at("runtime_trace_construct_start",
            wall_unix_ns=_rtc_start_ts[0], monotonic_ns=_rtc_start_ts[1], phase="local")
        runtime_trace.emit_at("trace_construct_end",
            wall_unix_ns=_rtc_end_ts[0], monotonic_ns=_rtc_end_ts[1], phase="local")
        _bc_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("benchmark_options_copy_start",
            wall_unix_ns=_bc_ts[0], monotonic_ns=_bc_ts[1], phase="local")
        _bench_modal_options = dict(modal_options)
        _bc_end_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("benchmark_options_copy_end",
            wall_unix_ns=_bc_end_ts[0], monotonic_ns=_bc_end_ts[1], phase="local")
        _cid_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("client_id_generation_start",
            wall_unix_ns=_cid_ts[0], monotonic_ns=_cid_ts[1], phase="local")
        _bench_client_id = f"v2-accept-client-{uuid.uuid4().hex[:8]}"
        _cid_end_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("client_id_generation_end",
            wall_unix_ns=_cid_end_ts[0], monotonic_ns=_cid_end_ts[1], phase="local")
        # Mirror the ComfyUI server's full node registry before any plan build:
        # a base-only registry would reject comfy_extras nodes at validation
        # and fingerprint the wrong surface.
        #
        # D1 zero-gap: when the persisted registry-proof/validation store covers
        # this workflow, plan construction needs no live registry (fast path).
        _registry_store_hit = _registry_proof_store_covers(
            workflow,
            modal_options=_bench_modal_options,
            production_options=(
                production_options if production_options.get("enabled") else None
            ),
        )
        if _registry_store_hit:
            print("[v2.harness] registry_load=skipped store_hit=yes", flush=True)
            _registry_load_ms = 0.0
        else:
            _registry_load_t0 = time.perf_counter()
            if not await _ensure_full_node_registry():
                raise RuntimeError(
                    "[v2.harness] node registry initialization failed; "
                    "cannot build an authoritative plan validation proof"
                )
            _registry_load_ms = round((time.perf_counter() - _registry_load_t0) * 1000.0, 3)
        _bep_call_ts = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("build_execution_plan_call_start",
            wall_unix_ns=_bep_call_ts[0], monotonic_ns=_bep_call_ts[1], phase="local")
        plan = build_execution_plan(
            workflow, prompt_id=_req_id, client_id=_bench_client_id,
            modal_options=_bench_modal_options,
            production_options=production_options if production_options.get("enabled") else None,
            gpu=_GPU, workspace=workspace,
            request_metadata={"benchmark_run_index": index, "benchmark_app": _APP_NAME,
                              "__request_origin_info__": request_origin_info},
            trace=runtime_trace, validate=False,
            collect_validation_proof=_PLAN_VALIDATION_PROOF,
            comfyui_root=_COMFYUI_ROOT_DIR,
        )
        _ep_call_wall_ns, _ep_call_mono_ns = (int(time.time() * 1_000_000_000), time.monotonic_ns())
        runtime_trace.emit_at("execute_plan_call_start",
            wall_unix_ns=_ep_call_wall_ns, monotonic_ns=_ep_call_mono_ns, phase="local")
        started = time.perf_counter()
        print(f"[v2.acceptance] phase=execute_plan label={label}", flush=True)
        result = await execute_plan(
            plan, transport=transport,
            restore_publisher=_resolve_restore_publisher(transport, workspace),
            profile_setter=set_active_warmup_profile,
            profile_checker=check_active_warmup_profile,
            gpu=_GPU, workspace=workspace, trace=runtime_trace,
        )
        _validate_remote_profile(result)
        _response_wall_ns, _response_mono_ns = _capture_ts()
        wall_ms = (time.perf_counter() - started) * 1000.0

        # Extract identity from REQUEST-SCOPED trace events
        identity = _extract_identity_from_trace(result, _req_id)
        runtime_shape_artifact = _validate_runtime_shape(result, identity)
        instance_id = identity.get("restored_instance_id", "")

        # Extract images
        images = _extract_images(result)
        asset_proofs: list[dict[str, Any]] = []
        for img in images:
            _aid = str(img.get("asset_id", ""))
            _backend = str(img.get("backend_path", ""))
            if not _aid and not _backend:
                continue
            _path = _backend or f"output_assets/{_aid}{img.get('file_ext', '.png')}"
            _expected_sha = _aid
            try:
                proof = await _read_remote_asset(handle, _path, _expected_sha, timeout=ASSET_TIMEOUT)
                asset_proofs.append(proof)
                print(f"[v2.acceptance] asset_fetched label={label} "
                      f"sha={_expected_sha[:16]} ms={proof['fetch_ms']}", flush=True)
            except Exception as exc:
                asset_proofs.append({"backend_path": _path, "expected_sha256": _expected_sha,
                                     "error": str(exc)[:200]})
                print(f"[v2.acceptance] asset_fetch_failed label={label} "
                      f"sha={_expected_sha[:16]} error={str(exc)[:100]}", flush=True)

        # Timing: scoped to current request_id
        trigger_to_modal_entry_ms = None
        for ev in result.get("trace", {}).get("events", []):
            if isinstance(ev, dict) and ev.get("name") == "remote_method_entry":
                meta = ev.get("metadata", {})
                if isinstance(meta, dict) and meta.get("request_id") == _req_id:
                    # Compute from local origin timestamps
                    # Use local_receive to first remote event from request_origin_info
                    pass
        # Fallback: use wall clock delta
        trigger_to_modal_entry_ms = round((time.time() * 1000 - _t0_wall_ms), 3)

        timing = _extract_acceptance_timing_scoped(
            result, _req_id,
            trigger_to_modal_entry_ms=trigger_to_modal_entry_ms,
            wall_ms=wall_ms,
        )
        # Update asset_fetch_ms after asset fetch: use max individual fetch time
        # or total if available.  Use total of all proof fetch latencies.
        _total_fetch_ms = sum(p.get("fetch_ms", 0) or 0 for p in asset_proofs)
        if _total_fetch_ms > 0:
            timing["asset_fetch_ms"] = round(_total_fetch_ms, 3)

        artifact = {
            "label": label,
            "run_index": index,
            "timestamp": _fmt_ts(),
            "identity": identity,
            "runtime_shape": runtime_shape_artifact,
            "images": images,
            "asset_proofs": asset_proofs,
            "timing": timing,
            "wall_ms": round(wall_ms, 1),
            "result": result,  # Include full remote result for event inspection
        }
        _waterfall = build_waterfall(
            result=result,
            timing=timing,
            wall_ms=wall_ms,
            command_start_unix_ms=_t0_wall_ms,
            response_received_unix_ns=_response_wall_ns,
            run_label=f"run {label}",
        )
        artifact["waterfall"] = waterfall_to_dict(_waterfall)
        (output_dir / f"run_{label}.json").write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        # Prefer the host-reconciled rebuild when present (acceptance does not
        # currently reconcile, so this falls back to the remote-built dict).
        _print_waterfall = artifact.get("waterfall_local") or artifact["waterfall"]
        if artifact.get("waterfall_local"):
            print("WATERFALL (host-reconciled)", flush=True)
        print(render_waterfall(_print_waterfall), flush=True)
        return artifact, _req_id

    # ══════════════════════════════════════════════════════════════════════
    # A: Fresh restored request + asset fetch
    # ══════════════════════════════════════════════════════════════════════
    print("[v2.acceptance] phase=A fresh_restored_start", flush=True)
    run_a, req_a_id = await _run_acceptance_request("A", 0)
    a_identity = run_a["identity"]
    a_instance_id = a_identity.get("restored_instance_id", "")
    a_checks = _check_acceptance(
        "A", run_a, run_a["timing"], run_a["images"], run_a["asset_proofs"],
        is_fresh=True, expected_restore_count=1, expected_request_count=1,
    )
    run_a["acceptance_checks"] = {"pass": len(a_checks) == 0, "failures": a_checks}
    if a_checks:
        print(f"[v2.acceptance] A failures: {a_checks}", flush=True)
        ACCEPTANCE_FAILED = True
    else:
        print(f"[v2.acceptance] A PASS instance={a_instance_id}", flush=True)
    runs.append(run_a)

    # ══════════════════════════════════════════════════════════════════════
    # B: IMMEDIATE second request (no wait, no cache clear)
    # ══════════════════════════════════════════════════════════════════════
    print("[v2.acceptance] phase=B immediate_reuse_start", flush=True)
    run_b, req_b_id = await _run_acceptance_request("B", 1)
    b_identity = run_b["identity"]
    b_instance_id = b_identity.get("restored_instance_id", "")

    b_placed_elsewhere = False
    if b_instance_id and a_instance_id and b_instance_id != a_instance_id:
        b_placed_elsewhere = True
        print(f"[v2.acceptance] B placed elsewhere instance={b_instance_id} "
              f"!= A instance={a_instance_id} — recording failure, allowing one retry", flush=True)
        print("[v2.acceptance] phase=B_retry_start", flush=True)
        run_b_retry, _ = await _run_acceptance_request("B_retry", 2)
        b_retry_instance = run_b_retry["identity"].get("restored_instance_id", "")
        b_retry_failures = _check_acceptance(
            "B_retry", run_b_retry, run_b_retry["timing"],
            run_b_retry["images"], run_b_retry["asset_proofs"],
            is_reused=True, expected_instance_id=a_instance_id,
            expected_request_count_min=2,
        )
        run_b_retry["acceptance_checks"] = {"pass": len(b_retry_failures) == 0, "failures": b_retry_failures}
        run_b["was_placed_elsewhere"] = True
        run_b["retry_attempt"] = run_b_retry
        runs.append(run_b)
        runs.append(run_b_retry)
        if not b_retry_failures:
            print(f"[v2.acceptance] B_retry PASS instance={b_retry_instance}", flush=True)
        else:
            ACCEPTANCE_FAILED = True
            print(f"[v2.acceptance] B_retry failures: {b_retry_failures}", flush=True)
    else:
        b_checks = _check_acceptance(
            "B", run_b, run_b["timing"], run_b["images"], run_b["asset_proofs"],
            is_reused=True, expected_instance_id=a_instance_id,
            expected_request_count_min=2,
        )
        run_b["acceptance_checks"] = {"pass": len(b_checks) == 0, "failures": b_checks}
        if b_checks:
            print(f"[v2.acceptance] B failures: {b_checks}", flush=True)
            ACCEPTANCE_FAILED = True
        else:
            print(f"[v2.acceptance] B PASS instance={b_instance_id}", flush=True)
        runs.append(run_b)

    # ══════════════════════════════════════════════════════════════════════
    # Wait >= 6 seconds
    # ══════════════════════════════════════════════════════════════════════
    print(f"[v2.acceptance] phase=wait seconds={WAIT_SECONDS}", flush=True)
    await asyncio.sleep(WAIT_SECONDS)

    # ══════════════════════════════════════════════════════════════════════
    # C: Another fresh restored request + asset fetch
    # ══════════════════════════════════════════════════════════════════════
    print("[v2.acceptance] phase=C fresh_restored_start", flush=True)
    run_c, req_c_id = await _run_acceptance_request("C", 3)
    c_instance_id = run_c["identity"].get("restored_instance_id", "")
    c_checks = _check_acceptance(
        "C", run_c, run_c["timing"], run_c["images"], run_c["asset_proofs"],
        is_fresh=True, expected_restore_count=1, expected_request_count=1,
        forbid_instance_id=a_instance_id,
    )
    run_c["acceptance_checks"] = {"pass": len(c_checks) == 0, "failures": c_checks}
    if c_checks:
        print(f"[v2.acceptance] C failures: {c_checks}", flush=True)
        ACCEPTANCE_FAILED = True
    else:
        print(f"[v2.acceptance] C PASS instance={c_instance_id}", flush=True)
    runs.append(run_c)

    # ══════════════════════════════════════════════════════════════════════
    # Summary
    # ══════════════════════════════════════════════════════════════════════
    summary: dict[str, Any] = {
        "mode": "acceptance",
        "app_name": _APP_NAME,
        "class_name": _CLASS_NAME,
        "gpu": _GPU,
        "runtime_shape": {
            "requested": runtime_shape_config().identity_payload(),
            "guard": _runtime_shape_guard(runtime_shape_config().identity_payload()),
        },
        "timestamp": _fmt_ts(),
        "wait_seconds": WAIT_SECONDS,
        "accepted": not ACCEPTANCE_FAILED,
        "runs": [],
    }
    for r in runs:
        entry = {
            "label": r["label"],
            "identity": r["identity"],
            "runtime_shape": r.get("runtime_shape", {}),
            "timing": r["timing"],
            "waterfall": r.get("waterfall", {}),
            "asset_proofs": r["asset_proofs"],
            "acceptance_checks": r.get("acceptance_checks", {}),
        }
        if r.get("was_placed_elsewhere"):
            entry["was_placed_elsewhere"] = True
        summary["runs"].append(entry)

    (output_dir / "acceptance_summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    _acceptance_reports = [r["waterfall"] for r in runs if r.get("waterfall")]
    print(json.dumps(summary, default=str, indent=2), flush=True)
    if len(_acceptance_reports) > 1:
        print(render_comparison(_acceptance_reports), flush=True)

    if ACCEPTANCE_FAILED:
        raise RuntimeError("acceptance mode: one or more checks failed")
    return summary


# ═══════════════════════════════════════════════════════════════════════════
# Variance-cold mode
#
# True-cold experiment: one request at a time, a fixed gap between runs, and a
# strict per-run assertion that the run is genuinely cold (not silently reused).
# Cold is proven from the request-scoped ``remote_method_entry`` metadata:
#   * restore_count == 1
#   * request_count == 1
#   * a non-empty restored_instance_id
#   * when available, a fresh container task/instance identity per run
# Warm/reused runs are never relabeled cold; they are preserved as invalid.
# ═══════════════════════════════════════════════════════════════════════════


def _remote_entry_wall_iso(result: dict[str, Any]) -> str:
    """Return ISO timestamp of the remote_method_entry wall clock, if present."""
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    for event in events:
        if not isinstance(event, dict) or event.get("name") != "remote_method_entry":
            continue
        wall_ns = event.get("wall_unix_ns")
        if isinstance(wall_ns, (int, float)) and wall_ns > 0:
            try:
                return datetime.fromtimestamp(wall_ns / 1_000_000_000, tz=timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                return "unavailable"
    return "unavailable"


def _cold_identity_key(identity: dict[str, Any]) -> tuple[str, ...]:
    """Canonical key for "same container/task instance" comparison.

    Uses the most authoritative identity tokens available.  An empty tuple
    means no freshness token could be established (freshness check is skipped,
    never treated as proof of cold).
    """
    candidates = (
        identity.get("container_task_id", ""),
        identity.get("modal_container_id", ""),
        identity.get("container_session_id", ""),
        identity.get("restored_instance_id", ""),
    )
    present = tuple(str(c) for c in candidates if str(c).strip())
    return present


def _validate_cold_identity(
    identity: dict[str, Any],
    *,
    run_index: int,
    pretouch: int,
    prev_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate true cold identity for one variance run.

    Returns a dict with ``cold_valid`` (bool), ``cold`` (bool), and ``failures``
    (list).  ``cold`` is True only when the run is both valid on its own and
    provably fresh relative to *prev_identity*.  Missing identity tokens fail
    explicitly — absence is never treated as cold.
    """
    failures: list[str] = []
    label = f"variance-cold run {run_index} (pretouch={pretouch})"

    restored_instance_id = str(identity.get("restored_instance_id", "") or "")
    try:
        restore_count = int(identity.get("restore_count", -1))
    except (TypeError, ValueError):
        restore_count = -1
    try:
        request_count = int(identity.get("request_count", -1))
    except (TypeError, ValueError):
        request_count = -1

    if not restored_instance_id:
        failures.append(f"{label}: restored_instance_id is empty/absent")
    if restore_count != 1:
        failures.append(f"{label}: restore_count={restore_count}, expected 1")
    if request_count != 1:
        failures.append(f"{label}: request_count={request_count}, expected 1")

    # Freshness relative to the previous run (only when a token is available).
    prev_key = _cold_identity_key(prev_identity or {})
    cur_key = _cold_identity_key(identity)
    freshness_checked = False
    if prev_key and cur_key:
        freshness_checked = True
        if cur_key == prev_key:
            failures.append(
                f"{label}: not fresh — container/task identity identical to "
                f"previous run ({cur_key})"
            )
    elif prev_identity is not None:
        # We have a previous run but cannot establish a freshness token for it
        # or the current run.  That is not proof of cold; flag it as a caveat
        # only when the previous run was itself deemed cold.
        if prev_identity.get("restored_instance_id"):
            failures.append(
                f"{label}: cannot establish freshness token; not provably cold"
            )

    cold = (len(failures) == 0) and (not prev_identity or freshness_checked or _cold_identity_key(identity))
    return {
        "cold_valid": len(failures) == 0,
        "cold": cold and len(failures) == 0,
        "failures": failures,
        "freshness_checked": freshness_checked,
    }


def _variance_origin(index: int, pretouch: int, app_name: str, teardown: str = "full", pin_transfer: int = 0, quiesced_transfer: int = 0) -> dict[str, Any]:
    """Request-origin metadata carrying per-run variance diagnostics.

    These keys travel inside ``__request_origin_info__`` so the remote runtime
    can apply variance diagnostics / ``COMFYMODAL_V2_UNET_PRETOUCH`` /
    ``COMFYMODAL_V2_UNET_QUIESCED_TRANSFER`` without a production default
    being changed.  ``env_profile`` is carried explicitly so the remote
    request-time profile semantics match the submitter.
    """
    return {
        "variance_mode": "cold",
        "variance_pretouch": int(pretouch),
        "minimal_teardown": 1 if teardown == "minimal" else 0,
        "pin_unet_transfer": int(pin_transfer),
        "unet_quiesced_transfer": int(quiesced_transfer),
        "variance_diagnostics": {
            "variance_cold_gap_seconds": VARIANCE_COLD_GAP_SECONDS,
            "benchmark_app": app_name,
            "mode": "variance_cold",
            "quiesced_transfer": int(quiesced_transfer),
        },
        "env_profile": os.environ.get("COMFYMODAL_V2_ENV_PROFILE", "production").strip().lower() or "production",
        "COMFYMODAL_V2_UNET_PRETOUCH": str(int(pretouch)),
        "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": str(int(quiesced_transfer)),
    }


def _resolve_pretouch(cli_value: int | None) -> int:
    """Resolve the UNET pretouch mode from CLI or env.

    Explicit CLI value wins; otherwise ``V2_VARIANCE_PRETOUCH`` is read
    (0 = disabled is the default).  Always returns 0 or 1.
    """
    if cli_value in (0, 1):
        return int(cli_value)
    raw = os.environ.get("V2_VARIANCE_PRETOUCH", "0").strip().lower()
    return 1 if raw in {"1", "true", "yes", "on"} else 0


def _resolve_slow_threshold() -> float:
    """Resolve the ONE fixed slow threshold (ms) used across all conditions.

    Uses the explicit env value when set, else the nonzero default.  A
    non-positive value fails fast rather than silently disabling the
    threshold — the threshold is never auto-derived from condition medians.
    """
    raw = os.environ.get("V2_VARIANCE_SLOW_THRESHOLD_MS", "").strip()
    value = float(raw) if raw else MATRIX_SLOW_THRESHOLD_MS
    if value <= 0:
        raise RuntimeError(
            "variance_matrix: V2_VARIANCE_SLOW_THRESHOLD_MS must be a positive "
            f"value, got {raw!r}; a fixed threshold is required and is never "
            "auto-derived from condition medians"
        )
    return value


def _matrix_origin(index: int, diag: int, pretouch: int, app_name: str, teardown: str = "full", pin_transfer: int = 0, quiesced_transfer: int = 0) -> dict[str, Any]:
    """Request-origin metadata for one matrix attempt.

    Carries the diagnostics and pretouch gates request-scoped so the remote
    runtime (``_apply_request_variance_diagnostics``) applies
    ``COMFYMODAL_V2_VARIANCE_DIAGNOSTICS`` / ``COMFYMODAL_V2_UNET_PRETOUCH`` /
    ``COMFYMODAL_V2_UNET_QUIESCED_TRANSFER`` per request without changing any
    production default.
    """
    return {
        "variance_mode": "cold",
        "variance_pretouch": int(pretouch),
        "minimal_teardown": 1 if teardown == "minimal" else 0,
        "pin_unet_transfer": int(pin_transfer),
        "unet_quiesced_transfer": int(quiesced_transfer),
        "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": str(int(diag)),
        "COMFYMODAL_V2_UNET_PRETOUCH": str(int(pretouch)),
        "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": str(int(quiesced_transfer)),
        "variance_diagnostics": {
            "variance_cold_gap_seconds": VARIANCE_COLD_GAP_SECONDS,
            "benchmark_app": app_name,
            "mode": "variance_matrix",
            "diagnostics": int(diag),
            "pretouch": int(pretouch),
            "quiesced_transfer": int(quiesced_transfer),
        },
        "env_profile": os.environ.get("COMFYMODAL_V2_ENV_PROFILE", "production").strip().lower() or "production",
    }


def _classify_attempt(record: dict[str, Any]) -> str:
    """Classify an attempt into cold / warm_invalid / failed / snapshot_capture.

    A run that never restored (``restore_count == 0``) is a snapshot capture
    and is NEVER counted as a valid cold request.  Absence of identity is
    ``warm_invalid``.  Exceptions are ``failed``.
    """
    if record.get("error"):
        return "failed"
    identity = record.get("identity", {}) or {}
    variance = record.get("variance", {}) or {}
    if variance.get("cold_valid") and variance.get("cold"):
        return "cold"
    try:
        restore_count = int(identity.get("restore_count", -1))
    except (TypeError, ValueError):
        restore_count = -1
    if restore_count == 0:
        return "snapshot_capture"
    return "warm_invalid"


def _slow_flag(value: float | None, threshold_ms: float) -> bool:
    """True only when *value* is a real number above *threshold_ms*."""
    return bool(value is not None and value > threshold_ms)


def _classify_slow(record: dict[str, Any]) -> dict[str, bool]:
    """Fixed slow flags: restore > 3s and UNET activation > 3s.

    These are fixed classifications, independent of any median-derived
    threshold.  UNET activation duration is sourced from the *extracted*
    result/trace metric ``metrics.page_traversal.unet_demand_to_first_forward_ms``
    (and the activation total when present), falling back to the raw
    ``timing.unet_demand_to_first_forward_ms`` only when the trace-derived
    value is absent.  Missing values never become slow.
    """
    timing = record.get("timing", {}) if isinstance(record.get("timing"), dict) else {}
    metrics = record.get("metrics", {}) if isinstance(record.get("metrics"), dict) else {}
    rt = metrics.get("restore", {}) if isinstance(metrics.get("restore"), dict) else {}
    pt = metrics.get("page_traversal", {}) if isinstance(metrics.get("page_traversal"), dict) else {}

    # Restore: prefer the extracted restore metric, fall back to raw timing.
    restore = _num(rt.get("restore_total_ms")) or _num(timing.get("restore_total_ms"))
    # UNET activation: trace-extracted demand->first-forward, then activation
    # total, then raw timing field.
    unet = (
        _num(pt.get("unet_demand_to_first_forward_ms"))
        or _num(pt.get("activation_total_ms"))
        or _num(timing.get("unet_demand_to_first_forward_ms"))
    )
    return {
        "restore_over_3s": _slow_flag(restore, MATRIX_RESTORE_SLOW_MS),
        "unet_activation_over_3s": _slow_flag(unet, MATRIX_UNET_ACTIVATION_SLOW_MS),
    }


async def _run_transfer_ab(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    gap_seconds: float,
    app_name: str,
    class_name: str,
    gpu: str,
    target_per_condition: int,
    max_attempts_per_condition: int,
    teardown: str = "minimal",
    _runner: Any = None,
) -> dict[str, Any]:
    """Interleaved UNET-transfer contention A/B (quiesced transfer diagnostic).

    A = current overlap (early activation runs concurrently with graph
    execution; sampler lane absorbs the tail).  B = quiesced transfer
    (request-scoped ``COMFYMODAL_V2_UNET_QUIESCED_TRANSFER=1``; the request
    waits for the transfer to complete before graph execution begins, and the
    worker samples per-thread CPU deltas during the synchronized transfer).
    Both conditions run with variance diagnostics ON (request-scoped) so the
    synchronized 12.31 GB CPU→GPU transfer is measured identically in A and B.

    Runs are strictly interleaved A,B,A,B,… with *gap_seconds* cold gaps.
    Continues until each condition collects *target_per_condition* valid cold
    runs (restore_count==1 && request_count==1 && fresh identity) or
    *max_attempts_per_condition* attempts.  EVERY attempt is preserved as
    ``attempt_<seq>.json``; a consolidated ``transfer_ab_report.md`` +
    ``summary.json`` are written.
    """
    conditions = (0, 1)  # quiesced_transfer: 0 = A (overlap), 1 = B (quiesced)
    per_cond: dict[int, dict[str, Any]] = {
        q: {"quiesced": q, "attempts": [], "cold_count": 0, "prev_identity": None}
        for q in conditions
    }
    print(
        f"[v2.transfer_ab] mode=start gap={gap_seconds}s "
        f"target={target_per_condition} max_per_cond={max_attempts_per_condition} "
        f"teardown={teardown} app={app_name}",
        flush=True,
    )
    records: list[dict[str, Any]] = []
    total_attempts = 0
    global_seq = 0
    round_robin_idx = 0
    target_met = False

    while total_attempts < max_attempts_per_condition * len(conditions):
        chosen: int | None = None
        for _ in range(len(conditions)):
            q = conditions[round_robin_idx % len(conditions)]
            round_robin_idx += 1
            if per_cond[q]["cold_count"] < target_per_condition and (
                len(per_cond[q]["attempts"]) < max_attempts_per_condition
            ):
                chosen = q
                break
        if chosen is None:
            target_met = True
            break

        quiesced = chosen
        state = per_cond[quiesced]
        total_attempts += 1
        global_seq += 1
        attempt_seq_in_cond = len(state["attempts"])
        label = "A-overlap" if quiesced == 0 else "B-quiesced"
        attempt_id = f"transfer-ab-{label}-{attempt_seq_in_cond}-{global_seq}-{uuid.uuid4().hex[:8]}"
        attempt_file = f"attempt_{global_seq:04d}.json"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _variance_origin(
            global_seq, pretouch=0, app_name=app_name, teardown=teardown,
            pin_transfer=0, quiesced_transfer=quiesced,
        )
        # Both arms measure the synchronized transfer identically (diagnostics
        # request-scoped ON); only the quiesce flag differs.
        origin["variance_mode"] = "transfer_ab"
        origin["COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"] = "1"

        artifact: dict[str, Any] = {}
        try:
            if _runner is not None:
                artifact = await _runner(
                    index=global_seq, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
            else:
                artifact = await _run_one(
                    index=global_seq, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": global_seq, "run_id": attempt_id, "request_id": "",
                "identity": {}, "result": {}, "timing": {},
                "variance": {
                    "quiesced_transfer": quiesced,
                    "teardown_mode": teardown,
                    "cold_valid": False, "cold": False,
                    "failures": [f"run raised: {str(exc)[:300]}"],
                },
                "start_ts": _start_ts, "end_ts": datetime.now(timezone.utc).isoformat(),
                "remote_entry_ts": "unavailable", "mode": "transfer_ab",
                "error": str(exc)[:300],
            }

        identity = artifact.get("identity", {}) or {}
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        cold_check = _validate_cold_identity(
            identity, run_index=global_seq, pretouch=0, prev_identity=state["prev_identity"],
        )
        artifact.setdefault("run_id", attempt_id)
        artifact["attempt_id"] = attempt_id
        artifact["attempt_file"] = attempt_file
        artifact["condition_label"] = label
        artifact["quiesced_transfer"] = quiesced
        artifact["mode"] = "transfer_ab"
        artifact["start_ts"] = artifact.get("start_ts") or _start_ts
        artifact["end_ts"] = artifact.get("end_ts") or datetime.now(timezone.utc).isoformat()
        artifact["remote_entry_ts"] = artifact.get("remote_entry_ts") or _remote_entry_wall_iso(result)
        if not artifact.get("error"):
            artifact["variance"] = {
                "quiesced_transfer": quiesced,
                "teardown_mode": teardown,
                "cold_valid": cold_check["cold_valid"],
                "cold": cold_check["cold"],
                "failures": cold_check["failures"],
                "freshness_checked": cold_check["freshness_checked"],
            }
        classification = _classify_attempt(artifact)
        artifact["classification"] = classification
        record = extract_run_metrics(artifact)
        slow_flags = _classify_slow(record)
        artifact["slow_flags"] = slow_flags
        record["slow_flags"] = slow_flags
        record["classification"] = classification
        record["attempt_id"] = attempt_id
        record["attempt_file"] = attempt_file
        record["condition_label"] = label
        record["quiesced_transfer"] = quiesced
        record["attempt_log"] = f"[transfer_ab] cond={label} class={classification}"
        (output_dir / attempt_file).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )

        records.append(record)
        if classification == "cold":
            state["cold_count"] += 1
            state["prev_identity"] = identity
        print(
            f"[v2.transfer_ab] seq={global_seq} id={attempt_id} cond={label} "
            f"class={classification} cold={state['cold_count']}/{target_per_condition}",
            flush=True,
        )
        if total_attempts < max_attempts_per_condition * len(conditions):
            needs = any(
                per_cond[q]["cold_count"] < target_per_condition
                and len(per_cond[q]["attempts"]) < max_attempts_per_condition
                for q in conditions
            )
            if needs:
                print(f"[v2.transfer_ab] phase=gap seconds={gap_seconds}", flush=True)
                await asyncio.sleep(gap_seconds)

    # ── Summary + handoff report ──────────────────────────────────────
    summary: dict[str, Any] = {
        "mode": "transfer_ab",
        "app_name": app_name,
        "class_name": class_name,
        "gpu": gpu,
        "gap_seconds": gap_seconds,
        "target_per_condition": target_per_condition,
        "max_attempts_per_condition": max_attempts_per_condition,
        "teardown_mode": teardown,
        "total_attempts": total_attempts,
        "conditions": {},
        "records": records,
    }
    for q in conditions:
        _cold = [r for r in records if r.get("quiesced_transfer") == q and r.get("classification") == "cold"]
        _all = [r for r in records if r.get("quiesced_transfer") == q]
        summary["conditions"][str(q)] = {
            "label": "A-overlap" if q == 0 else "B-quiesced",
            "attempts": len(_all),
            "cold_count": len(_cold),
        }
    (output_dir / "summary.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
        encoding="utf-8",
    )
    _report_md = _render_transfer_ab_report(summary)
    (output_dir / "transfer_ab_report.md").write_text(_report_md, encoding="utf-8")
    print(f"[v2.transfer_ab] report={output_dir / 'transfer_ab_report.md'}", flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "mode": "transfer_ab",
        "total_attempts": total_attempts,
        "per_condition": {str(q): summary["conditions"][str(q)] for q in conditions},
        "target_met": target_met,
    }, default=str), flush=True)
    print(_report_md, flush=True)

    if not target_met:
        raise RuntimeError(
            "transfer_ab: reached the per-condition attempt cap before every "
            f"condition collected {target_per_condition} valid cold runs; "
            f"attempts preserved in {output_dir}"
        )
    return summary


def _render_transfer_ab_report(summary: dict[str, Any]) -> str:
    """Render the consolidated transfer A/B handoff report (markdown)."""
    records = summary.get("records", []) or []
    _lines: list[str] = []
    _lines.append("# V2 UNET-Transfer Contention A/B (overlap vs quiesced)\n")
    _lines.append(
        f"- App: `{summary.get('app_name', '')}` · GPU `{summary.get('gpu', '')}` · "
        f"gap `{summary.get('gap_seconds')}s` · teardown `{summary.get('teardown_mode', '')}`"
    )
    _lines.append(
        f"- A = current overlap (early activation runs concurrently with graph); "
        f"B = quiesced transfer (`COMFYMODAL_V2_UNET_QUIESCED_TRANSFER=1`, graph "
        f"waits for transfer completion). Both arms: variance diagnostics ON, "
        f"minimal teardown, single-use containers.\n"
    )
    _lines.append("| cond | attempt | class | cmd→resp (ms) | transfer queue delay (ms) | sync transfer (ms) | GB/s | restore (ms) | sampler wait (ms) | sampling (ms) | quiesce wait (ms) | graph activity (ms) |")
    _lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in sorted(records, key=lambda x: (x.get("quiesced_transfer", 0), x.get("attempt_id", ""))):
        _metrics = r.get("metrics", {}) if isinstance(r.get("metrics"), dict) else {}
        _t = _metrics.get("transfer", {}) if isinstance(_metrics.get("transfer"), dict) else {}
        _p = _metrics.get("page_traversal", {}) if isinstance(_metrics.get("page_traversal"), dict) else {}
        _rst = _metrics.get("restore", {}) if isinstance(_metrics.get("restore"), dict) else {}
        _sp = _metrics.get("sampler", {}) if isinstance(_metrics.get("sampler"), dict) else {}
        _label = "A" if r.get("quiesced_transfer") == 0 else "B"
        _lines.append(
            f"| {_label} | {r.get('attempt_id', '')} | {r.get('classification', '')} "
            f"| {_fmt_ms(_t.get('command_to_response_ms'))} "
            f"| {_fmt_ms(_t.get('transfer_queue_delay_ms'))} "
            f"| {_fmt_ms(_p.get('cpu_to_gpu_transfer_wall_ms'))} "
            f"| {_fmt_gbps(_p.get('cpu_to_gpu_transfer_gb_per_s'))} "
            f"| {_fmt_ms(_rst.get('restore_total_ms'))} "
            f"| {_fmt_ms(_sp.get('sampler_lane_wait_ms'))} "
            f"| {_fmt_ms(_sp.get('sampling_ms'))} "
            f"| {_fmt_ms(_t.get('quiesce_wait_ms'))} "
            f"| {_fmt_ms(_t.get('graph_activity_ms'))} |"
        )
    _lines.append("")
    for q, cond in (summary.get("conditions", {}) or {}).items():
        _lines.append(
            f"- Condition {q} ({cond.get('label', '')}): {cond.get('cold_count', 0)}/"
            f"{summary.get('target_per_condition', 0)} valid cold, "
            f"{cond.get('attempts', 0)} attempts preserved."
        )
    return "\n".join(_lines)


def _fmt_ms(value: Any) -> str:
    if value is None or value == "unavailable":
        return "–"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "–"


def _fmt_gbps(value: Any) -> str:
    if value is None or value == "unavailable":
        return "–"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "–"


async def _run_region_ab(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    gap_seconds: float,
    region: str,
    app_name: str,
    class_name: str,
    gpu: str,
    target_cold: int,
    max_attempts: int,
    skip_first: int = 2,
    teardown: str = "minimal",
    _runner: Any = None,
) -> dict[str, Any]:
    """Region-pinned cold transfer comparison (one pinned region per run).

    Deployed with ``COMFYMODAL_V2_REGION=<region>`` so every request lands on
    the pinned region pool.  The first *skip_first* attempts of the block are
    EXCLUDED from the valid set unconditionally: attempt 1 is the
    snapshot/cache-build run and attempt 2 is the run that restores the
    freshly-built snapshot — both are "snapshot builders" (the second often
    does not look like one).  Then collects *target_cold* valid cold runs
    (restore_count==1 && request_count==1 && fresh identity), production
    overlap arm (quiesced=0), variance diagnostics ON for the synchronized
    measurement, single-use containers, minimal teardown, 25 s gaps.  Every
    attempt is preserved as ``attempt_<seq>.json``.
    """
    print(
        f"[v2.region_ab] mode=start region={region} gap={gap_seconds}s "
        f"target={target_cold} max={max_attempts} skip_first={skip_first} "
        f"teardown={teardown} app={app_name}",
        flush=True,
    )
    records: list[dict[str, Any]] = []
    prev_identity: dict[str, Any] | None = None
    skipped = 0
    valid_cold = 0
    total_attempts = 0

    while valid_cold < target_cold and total_attempts < max_attempts:
        index = total_attempts
        total_attempts += 1
        _run_id = f"region-ab-{region}-{index}-{uuid.uuid4().hex[:8]}"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _variance_origin(
            index, pretouch=0, app_name=app_name, teardown=teardown,
            pin_transfer=0, quiesced_transfer=0,
        )
        origin["variance_mode"] = "region_ab"
        origin["COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"] = "1"
        origin["pinned_region"] = region

        artifact: dict[str, Any] = {}
        try:
            if _runner is not None:
                artifact = await _runner(
                    index=index, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
            else:
                artifact = await _run_one(
                    index=index, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": index, "run_id": _run_id, "request_id": "",
                "identity": {}, "result": {}, "timing": {},
                "variance": {
                    "quiesced_transfer": 0, "teardown_mode": teardown,
                    "cold_valid": False, "cold": False,
                    "failures": [f"run raised: {str(exc)[:300]}"],
                },
                "start_ts": _start_ts, "end_ts": datetime.now(timezone.utc).isoformat(),
                "remote_entry_ts": "unavailable", "mode": "region_ab",
                "error": str(exc)[:300],
            }

        identity = artifact.get("identity", {}) or {}
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        cold_check = _validate_cold_identity(
            identity, run_index=index, pretouch=0, prev_identity=prev_identity,
        )
        artifact["run_id"] = _run_id
        artifact["attempt_file"] = f"attempt_{index:04d}.json"
        artifact["pinned_region"] = region
        artifact["region"] = identity.get("region", "")
        artifact["mode"] = "region_ab"
        artifact["start_ts"] = artifact.get("start_ts") or _start_ts
        artifact["end_ts"] = artifact.get("end_ts") or datetime.now(timezone.utc).isoformat()
        artifact["remote_entry_ts"] = artifact.get("remote_entry_ts") or _remote_entry_wall_iso(result)
        artifact["excluded_snapshot_builder"] = index < skip_first
        if not artifact.get("error"):
            artifact["variance"] = {
                "quiesced_transfer": 0,
                "teardown_mode": teardown,
                "cold_valid": cold_check["cold_valid"],
                "cold": cold_check["cold"],
                "failures": cold_check["failures"],
                "freshness_checked": cold_check["freshness_checked"],
            }
        classification = _classify_attempt(artifact)
        artifact["classification"] = classification
        record = extract_run_metrics(artifact)
        record["classification"] = classification
        record["attempt_file"] = artifact["attempt_file"]
        record["pinned_region"] = region
        record["actual_region"] = identity.get("region", "")
        record["excluded_snapshot_builder"] = index < skip_first
        record["attempt_log"] = (
            f"[region_ab] region={region} index={index} class={classification}"
        )
        (output_dir / artifact["attempt_file"]).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        records.append(record)

        if index < skip_first:
            skipped += 1
            status = "SKIPPED(snapshot-builder)"
        elif cold_check["cold"] and cold_check["cold_valid"]:
            valid_cold += 1
            prev_identity = identity
            status = "COLD"
        else:
            status = "NOT-COLD"
        print(
            f"[v2.region_ab] index={index} id={_run_id} region={region} "
            f"actual={identity.get('region', '?')} status={status} "
            f"valid={valid_cold}/{target_cold}",
            flush=True,
        )
        if total_attempts < max_attempts:
            print(f"[v2.region_ab] phase=gap seconds={gap_seconds}", flush=True)
            await asyncio.sleep(gap_seconds)

    summary: dict[str, Any] = {
        "mode": "region_ab",
        "region": region,
        "app_name": app_name,
        "class_name": class_name,
        "gpu": gpu,
        "gap_seconds": gap_seconds,
        "target_cold": target_cold,
        "max_attempts": max_attempts,
        "skip_first": skip_first,
        "teardown_mode": teardown,
        "total_attempts": total_attempts,
        "skipped_snapshot_builders": skipped,
        "valid_cold": valid_cold,
        "records": records,
    }
    (output_dir / "summary.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
        encoding="utf-8",
    )
    _report_md = _render_region_ab_report(summary)
    (output_dir / "region_ab_report.md").write_text(_report_md, encoding="utf-8")
    print(f"[v2.region_ab] report={output_dir / 'region_ab_report.md'}", flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "region": region,
        "total_attempts": total_attempts,
        "skipped": skipped,
        "valid_cold": valid_cold,
    }, default=str), flush=True)
    print(_report_md, flush=True)

    if valid_cold < target_cold:
        raise RuntimeError(
            f"region_ab: only {valid_cold}/{target_cold} valid cold runs in "
            f"region {region} after {max_attempts} attempts; attempts preserved "
            f"in {output_dir}"
        )
    return summary


def _render_region_ab_report(summary: dict[str, Any]) -> str:
    """Render the region-pinned cold comparison report (markdown)."""
    records = summary.get("records", []) or []
    _lines: list[str] = []
    _lines.append("# V2 Region-Pinned Transfer Comparison\n")
    _lines.append(
        f"- Pinned region: `{summary.get('region', '')}` · app "
        f"`{summary.get('app_name', '')}` · GPU `{summary.get('gpu', '')}` · "
        f"gap `{summary.get('gap_seconds')}s` · teardown `{summary.get('teardown_mode', '')}`"
    )
    _lines.append(
        f"- Protocol: first {summary.get('skip_first', 2)} attempts excluded "
        f"(snapshot/cache build + the run after); "
        f"{summary.get('valid_cold', 0)}/{summary.get('target_cold', 0)} valid cold "
        f"collected in {summary.get('total_attempts', 0)} attempts; every attempt preserved.\n"
    )
    _lines.append("| attempt | class | actual region | cmd→resp (ms) | pre-python sched (ms) | restore (ms) | tfr queue (ms) | sync tfr (ms) | GB/s | sampler wait (ms) | sampling (ms) |")
    _lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in sorted(records, key=lambda x: x.get("attempt_file", "")):
        _metrics = r.get("metrics", {}) if isinstance(r.get("metrics"), dict) else {}
        _t = _metrics.get("transfer", {}) if isinstance(_metrics.get("transfer"), dict) else {}
        _p = _metrics.get("page_traversal", {}) if isinstance(_metrics.get("page_traversal"), dict) else {}
        _rst = _metrics.get("restore", {}) if isinstance(_metrics.get("restore"), dict) else {}
        _sp = _metrics.get("sampler", {}) if isinstance(_metrics.get("sampler"), dict) else {}
        _tag = "SKIP" if r.get("excluded_snapshot_builder") else r.get("classification", "")
        _lines.append(
            f"| {r.get('attempt_file', '')} | {_tag} | {r.get('actual_region', '?')} "
            f"| {_fmt_ms(_t.get('command_to_response_ms'))} "
            f"| {_fmt_ms(_t.get('pre_python_modal_scheduling_ms'))} "
            f"| {_fmt_ms(_rst.get('restore_total_ms'))} "
            f"| {_fmt_ms(_t.get('transfer_queue_delay_ms'))} "
            f"| {_fmt_ms(_p.get('cpu_to_gpu_transfer_wall_ms'))} "
            f"| {_fmt_gbps(_p.get('cpu_to_gpu_transfer_gb_per_s'))} "
            f"| {_fmt_ms(_sp.get('sampler_lane_wait_ms'))} "
            f"| {_fmt_ms(_sp.get('sampling_ms'))} |"
        )
    _lines.append("")
    return "\n".join(_lines)


def _classify_transfer_speed(transfer_ms: float | None) -> str:
    """Classify a transfer by wall time: FAST <2.5 s, MEDIUM 2.5–5 s, SLOW >5 s."""
    if transfer_ms is None:
        return "NO-DATA"
    if transfer_ms < 2500.0:
        return "FAST"
    if transfer_ms <= 5000.0:
        return "MEDIUM"
    return "SLOW"


def _host_label(record: dict[str, Any]) -> str:
    """Short stable host label for grouping: provider|region|cpu-model."""
    host = record.get("host_diagnostics", {}) if isinstance(record.get("host_diagnostics"), dict) else {}
    cpu = host.get("cpu", {}) if isinstance(host.get("cpu"), dict) else {}
    model = str(cpu.get("model_name", "?"))
    model = " ".join(model.split())[:48]
    provider = str(record.get("provider", "") or host.get("modal_cloud_provider", ""))
    region = str(record.get("region", "") or host.get("modal_region", ""))
    return f"{provider or '?'}|{region or '?'}|{model or '?'}"


async def _run_host_ab(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    gap_seconds: float,
    app_name: str,
    class_name: str,
    gpu: str,
    target_cold: int,
    max_attempts: int,
    skip_first: int = 2,
    teardown: str = "minimal",
    _runner: Any = None,
) -> dict[str, Any]:
    """Unpinned cold-run host-characteristics study.

    Same protocol as the region-pinned comparison but WITHOUT any region pin:
    Modal places each request naturally, so provider / region / host hardware
    vary across attempts.  The first *skip_first* attempts of the block are
    EXCLUDED from the valid set unconditionally (snapshot/cache build + the
    run after).  Then collects *target_cold* valid cold runs
    (restore_count==1 && request_count==1 && fresh identity), production
    overlap arm (quiesced=0), variance diagnostics ON for the synchronized
    measurement, single-use containers, minimal teardown, 25 s gaps.  Every
    attempt is preserved as ``attempt_<seq>.json`` including the remote
    ``host_diagnostics`` (CPU model, NUMA, GPU UUID/PCIe, VM family).
    """
    print(
        f"[v2.host_ab] mode=start gap={gap_seconds}s target={target_cold} "
        f"max={max_attempts} skip_first={skip_first} teardown={teardown} "
        f"app={app_name}",
        flush=True,
    )
    records: list[dict[str, Any]] = []
    prev_identity: dict[str, Any] | None = None
    skipped = 0
    valid_cold = 0
    total_attempts = 0

    while valid_cold < target_cold and total_attempts < max_attempts:
        index = total_attempts
        total_attempts += 1
        _run_id = f"host-ab-{index}-{uuid.uuid4().hex[:8]}"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _variance_origin(
            index, pretouch=0, app_name=app_name, teardown=teardown,
            pin_transfer=0, quiesced_transfer=0,
        )
        origin["variance_mode"] = "host_ab"
        origin["COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"] = "1"

        artifact: dict[str, Any] = {}
        try:
            if _runner is not None:
                artifact = await _runner(
                    index=index, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
            else:
                artifact = await _run_one(
                    index=index, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": index, "run_id": _run_id, "request_id": "",
                "identity": {}, "result": {}, "timing": {},
                "variance": {
                    "quiesced_transfer": 0, "teardown_mode": teardown,
                    "cold_valid": False, "cold": False,
                    "failures": [f"run raised: {str(exc)[:300]}"],
                },
                "start_ts": _start_ts, "end_ts": datetime.now(timezone.utc).isoformat(),
                "remote_entry_ts": "unavailable", "mode": "host_ab",
                "error": str(exc)[:300],
            }

        identity = artifact.get("identity", {}) or {}
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        cold_check = _validate_cold_identity(
            identity, run_index=index, pretouch=0, prev_identity=prev_identity,
        )
        artifact["run_id"] = _run_id
        artifact["attempt_file"] = f"attempt_{index:04d}.json"
        artifact["region"] = identity.get("region", "")
        artifact["mode"] = "host_ab"
        artifact["start_ts"] = artifact.get("start_ts") or _start_ts
        artifact["end_ts"] = artifact.get("end_ts") or datetime.now(timezone.utc).isoformat()
        artifact["remote_entry_ts"] = artifact.get("remote_entry_ts") or _remote_entry_wall_iso(result)
        artifact["excluded_snapshot_builder"] = index < skip_first
        if not artifact.get("error"):
            artifact["variance"] = {
                "quiesced_transfer": 0,
                "teardown_mode": teardown,
                "cold_valid": cold_check["cold_valid"],
                "cold": cold_check["cold"],
                "failures": cold_check["failures"],
                "freshness_checked": cold_check["freshness_checked"],
            }
        classification = _classify_attempt(artifact)
        artifact["classification"] = classification
        record = extract_run_metrics(artifact)
        record["classification"] = classification
        record["attempt_file"] = artifact["attempt_file"]
        record["provider"] = identity.get("cloud", "")
        record["actual_region"] = identity.get("region", "")
        record["excluded_snapshot_builder"] = index < skip_first
        record["host_diagnostics"] = artifact.get("host_diagnostics", {})
        record["host_label"] = _host_label(record)
        _metrics = record.get("metrics", {}) if isinstance(record.get("metrics"), dict) else {}
        _p = _metrics.get("page_traversal", {}) if isinstance(_metrics.get("page_traversal"), dict) else {}
        _transfer_ms = _p.get("cpu_to_gpu_transfer_wall_ms")
        record["transfer_speed"] = _classify_transfer_speed(_transfer_ms)
        record["transfer_ms"] = _transfer_ms
        record["attempt_log"] = (
            f"[host_ab] index={index} class={classification} "
            f"speed={record['transfer_speed']} host={record['host_label']}"
        )
        (output_dir / artifact["attempt_file"]).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        records.append(record)

        if index < skip_first:
            skipped += 1
            status = "SKIPPED(snapshot-builder)"
        elif cold_check["cold"] and cold_check["cold_valid"]:
            valid_cold += 1
            prev_identity = identity
            status = "COLD"
        else:
            status = "NOT-COLD"
        print(
            f"[v2.host_ab] index={index} id={_run_id} "
            f"provider={identity.get('cloud', '?')} "
            f"region={identity.get('region', '?')} status={status} "
            f"speed={record['transfer_speed']} valid={valid_cold}/{target_cold}",
            flush=True,
        )
        if total_attempts < max_attempts:
            print(f"[v2.host_ab] phase=gap seconds={gap_seconds}", flush=True)
            await asyncio.sleep(gap_seconds)

    summary: dict[str, Any] = {
        "mode": "host_ab",
        "app_name": app_name,
        "class_name": class_name,
        "gpu": gpu,
        "gap_seconds": gap_seconds,
        "target_cold": target_cold,
        "max_attempts": max_attempts,
        "skip_first": skip_first,
        "teardown_mode": teardown,
        "total_attempts": total_attempts,
        "skipped_snapshot_builders": skipped,
        "valid_cold": valid_cold,
        "records": records,
    }
    (output_dir / "summary.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
        encoding="utf-8",
    )
    _report_md = _render_host_ab_report(summary)
    (output_dir / "host_ab_report.md").write_text(_report_md, encoding="utf-8")
    print(f"[v2.host_ab] report={output_dir / 'host_ab_report.md'}", flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "total_attempts": total_attempts,
        "skipped": skipped,
        "valid_cold": valid_cold,
    }, default=str), flush=True)
    print(_report_md, flush=True)

    if valid_cold < target_cold:
        raise RuntimeError(
            f"host_ab: only {valid_cold}/{target_cold} valid cold runs in "
            f"{max_attempts} attempts; attempts preserved in {output_dir}"
        )
    return summary


def _render_host_ab_report(summary: dict[str, Any]) -> str:
    """Render the unpinned host-characteristics study report (markdown)."""
    records = summary.get("records", []) or []
    _lines: list[str] = []
    _lines.append("# V2 Host-Characteristics Cold Study\n")
    _lines.append(
        f"- Unpinned placement (no region pin) · app `{summary.get('app_name', '')}` "
        f"· GPU `{summary.get('gpu', '')}` · gap `{summary.get('gap_seconds')}s` "
        f"· teardown `{summary.get('teardown_mode', '')}`"
    )
    _lines.append(
        f"- Protocol: first {summary.get('skip_first', 2)} attempts excluded "
        f"(snapshot/cache build + the run after); "
        f"{summary.get('valid_cold', 0)}/{summary.get('target_cold', 0)} valid cold "
        f"collected in {summary.get('total_attempts', 0)} attempts; every attempt "
        f"preserved.  Transfer speed classes: FAST <2.5 s, MEDIUM 2.5–5 s, SLOW >5 s.\n"
    )
    _lines.append("| attempt | class | provider | region | CPU model | threads | NUMA | PCIe | transfer (ms) | GB/s | speed | restore (ms) | cmd→resp (ms) |")
    _lines.append("|---|---|---|---|---|---|---|---|---:|---:|---|---:|---:|")
    for r in sorted(records, key=lambda x: x.get("attempt_file", "")):
        _metrics = r.get("metrics", {}) if isinstance(r.get("metrics"), dict) else {}
        _t = _metrics.get("transfer", {}) if isinstance(_metrics.get("transfer"), dict) else {}
        _p = _metrics.get("page_traversal", {}) if isinstance(_metrics.get("page_traversal"), dict) else {}
        _rst = _metrics.get("restore", {}) if isinstance(_metrics.get("restore"), dict) else {}
        _host = r.get("host_diagnostics", {}) if isinstance(r.get("host_diagnostics"), dict) else {}
        _cpu = _host.get("cpu", {}) if isinstance(_host.get("cpu"), dict) else {}
        _gpu = _host.get("gpu", {}) if isinstance(_host.get("gpu"), dict) else {}
        _numa = _host.get("numa", {}) if isinstance(_host.get("numa"), dict) else {}
        _model = str(_cpu.get("model_name", "?"))
        _model = " ".join(_model.split())[:44]
        _pcie = ""
        if isinstance(_gpu.get("pcie_link_gen_current"), int) and isinstance(_gpu.get("pcie_link_width_current"), int):
            _pcie = f"PCIe{_gpu['pcie_link_gen_current']} x{_gpu['pcie_link_width_current']}"
        _tag = "SKIP" if r.get("excluded_snapshot_builder") else r.get("classification", "")
        _lines.append(
            f"| {r.get('attempt_file', '')} | {_tag} | {r.get('provider', '?')} "
            f"| {r.get('actual_region', '?')} | {_model} "
            f"| {_cpu.get('threads', '?')} | {('yes' if _numa else 'no')} | {_pcie} "
            f"| {_fmt_ms(_p.get('cpu_to_gpu_transfer_wall_ms'))} "
            f"| {_fmt_gbps(_p.get('cpu_to_gpu_transfer_gb_per_s'))} "
            f"| {r.get('transfer_speed', '?')} "
            f"| {_fmt_ms(_rst.get('restore_total_ms'))} "
            f"| {_fmt_ms(_t.get('command_to_response_ms'))} |"
        )
    _lines.append("")

    # ── By-host summary (valid cold runs only) ──
    _lines.append("## By host (valid cold runs)\n")
    _by_host: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        if r.get("excluded_snapshot_builder"):
            continue
        _by_host.setdefault(str(r.get("host_label", "?")), []).append(r)
    _lines.append("| host (provider|region|CPU) | n | transfer ms (median/range) | GB/s (median) | FAST | MEDIUM | SLOW |")
    _lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for _label in sorted(_by_host):
        _group = _by_host[_label]
        _vals = sorted(float(v) for v in (_r.get("transfer_ms") for _r in _group) if isinstance(v, (int, float)))
        _median = _vals[len(_vals) // 2] if _vals else None
        _range = f"{_vals[0]:.0f}–{_vals[-1]:.0f}" if _vals else "?"
        _gb = [float(_r.get("metrics", {}).get("page_traversal", {}).get("cpu_to_gpu_transfer_gb_per_s")) for _r in _group]
        _gb = [g for g in _gb if g == g]
        _gb_med = sorted(_gb)[len(_gb) // 2] if _gb else None
        _n_fast = sum(1 for _r in _group if _r.get("transfer_speed") == "FAST")
        _n_med = sum(1 for _r in _group if _r.get("transfer_speed") == "MEDIUM")
        _n_slow = sum(1 for _r in _group if _r.get("transfer_speed") == "SLOW")
        _lines.append(
            f"| {_label} | {len(_group)} | {_fmt_ms(_median)} ({_range}) "
            f"| {_fmt_gbps(_gb_med)} | {_n_fast} | {_n_med} | {_n_slow} |"
        )
    _lines.append("")

    # ── Host inventory (unique containers) ──
    _lines.append("## Host inventory (unique containers)\n")
    _seen: set[str] = set()
    for r in sorted(records, key=lambda x: x.get("attempt_file", "")):
        _host = r.get("host_diagnostics", {}) if isinstance(r.get("host_diagnostics"), dict) else {}
        _cid = str(_host.get("container_key", "") or _host.get("modal_container_id", ""))
        if not _cid or _cid in _seen:
            continue
        _seen.add(_cid)
        _cpu = _host.get("cpu", {}) if isinstance(_host.get("cpu"), dict) else {}
        _gpu = _host.get("gpu", {}) if isinstance(_host.get("gpu"), dict) else {}
        _vm = _host.get("vm", {}) if isinstance(_host.get("vm"), dict) else {}
        _numa = _host.get("numa", {}) if isinstance(_host.get("numa"), dict) else {}
        _numa_nodes = _numa.get("nodes")
        _numa_txt = "yes"
        if isinstance(_numa_nodes, list):
            _numa_txt = f"yes({len(_numa_nodes)} nodes)"
        elif not _numa:
            _numa_txt = "no"
        _pcie = ""
        if isinstance(_gpu.get("pcie_link_gen_current"), int) and isinstance(_gpu.get("pcie_link_width_current"), int):
            _pcie = f"PCIe{_gpu['pcie_link_gen_current']} x{_gpu['pcie_link_width_current']}"
        _lines.append(
            f"- container `{_cid[:24]}`: provider={_host.get('modal_cloud_provider', '?')} "
            f"region={_host.get('modal_region', '?')} · "
            f"cpu=`{_cpu.get('model_name', '?')}` (family {_cpu.get('cpu_family', '?')}/model "
            f"{_cpu.get('model', '?')}/stepping {_cpu.get('stepping', '?')}, "
            f"{_cpu.get('sockets', '?')} socket(s)/{_cpu.get('cores', '?')} core(s)/"
            f"{_cpu.get('threads', '?')} thread(s)) · kernel={_host.get('kernel', '?')} · "
            f"numa={_numa_txt} · gpu=`{_gpu.get('name', '?')}` "
            f"uuid=`{str(_gpu.get('uuid', '?'))[:24]}` bus={_gpu.get('pci_bus_id', '?')} "
            f"{_pcie} driver={_gpu.get('driver_version', '?')} cuda={_gpu.get('cuda_version', '?')} · "
            f"vm={_vm.get('vm_family', '?')} "
            f"machine={_vm.get('gcp_machine_type', _vm.get('aws_instance_type', '?'))} "
            f"dmi={_vm.get('dmi_product_name', '?')}"
        )
    _lines.append("")
    return "\n".join(_lines)


BACKING_A_APP = os.environ.get(
    "COMFYMODAL_V2_BACKING_A_APP", "stable-modal-comfy-v2-backing-a-shadow"
)
BACKING_B_APP = os.environ.get(
    "COMFYMODAL_V2_BACKING_B_APP", "stable-modal-comfy-v2-backing-b-shadow"
)


def _extract_synth_probe(result: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the per-run ``synth_h2d_probe`` trace event metadata."""
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("name") == "synth_h2d_probe":
            metadata = event.get("metadata", {})
            return dict(metadata) if isinstance(metadata, dict) else {}
    return None


def _host_gpu_uuid(record: dict[str, Any]) -> str:
    host = record.get("host_diagnostics", {}) if isinstance(record.get("host_diagnostics"), dict) else {}
    gpu = host.get("gpu", {}) if isinstance(host.get("gpu"), dict) else {}
    return str(gpu.get("uuid", ""))[:16]


async def _run_backing_ab(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    gap_seconds: float,
    app_a: str,
    app_b: str,
    class_name: str,
    gpu: str,
    target_cold: int,
    max_attempts_per_arm: int,
    skip_first: int = 2,
    teardown: str = "minimal",
    _runner: Any = None,
) -> dict[str, Any]:
    """Interleaved A/B UNET-backing cold study.

    Arm A = current CPU-snapshot UNET (safetensors/Volume-backed hypothesis).
    Arm B = anonymous-RAM snapshot (UNET cloned into fresh anonymous CPU
    memory before snapshot capture).  Two separate shadow deployments; runs
    strictly interleaved A,B,A,B,... so placement/scheduling noise is shared.
    Each arm discards its first *skip_first* attempts (snapshot/cache build
    + the run after) and collects *target_cold* valid cold runs
    (restore_count==1 && request_count==1 && fresh identity), single-use
    containers, minimal teardown, 25 s gaps.  Every attempt is preserved as
    ``attempt_<seq>.json`` with the per-run synthetic 2 GB anonymous H2D
    probe, the real UNET synchronized transfer, host diagnostics and (on the
    snapshot-build runs) the /proc/self/maps backing evidence.
    """
    print(
        f"[v2.backing_ab] mode=start gap={gap_seconds}s target={target_cold} "
        f"max_per_arm={max_attempts_per_arm} skip_first={skip_first} "
        f"teardown={teardown} app_a={app_a} app_b={app_b}",
        flush=True,
    )
    arms: tuple[tuple[str, str], ...] = (("A", app_a), ("B", app_b))
    per_arm: dict[str, dict[str, Any]] = {
        label: {"app": app, "attempts": [], "cold": 0, "skipped": 0,
                "prev_identity": None}
        for label, app in arms
    }
    records: list[dict[str, Any]] = []
    total_attempts = 0
    round_robin_idx = 0

    while total_attempts < max_attempts_per_arm * len(arms):
        chosen: tuple[str, str] | None = None
        for _ in range(len(arms)):
            label, app = arms[round_robin_idx % len(arms)]
            round_robin_idx += 1
            st = per_arm[label]
            if st["cold"] < target_cold and len(st["attempts"]) < max_attempts_per_arm:
                chosen = (label, app)
                break
        if chosen is None:
            break
        label, app = chosen
        st = per_arm[label]
        os.environ["COMFYMODAL_V2_APP_NAME"] = app
        index = total_attempts
        total_attempts += 1
        arm_attempt = len(st["attempts"])
        st["attempts"].append(arm_attempt)
        _run_id = f"backing-ab-{label}-{arm_attempt}-{index}-{uuid.uuid4().hex[:8]}"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _variance_origin(
            index, pretouch=0, app_name=app, teardown=teardown,
            pin_transfer=0, quiesced_transfer=0,
        )
        origin["variance_mode"] = "backing_ab"
        origin["COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"] = "1"

        artifact: dict[str, Any] = {}
        try:
            if _runner is not None:
                artifact = await _runner(
                    index=index, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
            else:
                artifact = await _run_one(
                    index=index, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": index, "run_id": _run_id, "request_id": "",
                "identity": {}, "result": {}, "timing": {},
                "variance": {
                    "quiesced_transfer": 0, "teardown_mode": teardown,
                    "cold_valid": False, "cold": False,
                    "failures": [f"run raised: {str(exc)[:300]}"],
                },
                "start_ts": _start_ts, "end_ts": datetime.now(timezone.utc).isoformat(),
                "remote_entry_ts": "unavailable", "mode": "backing_ab",
                "error": str(exc)[:300],
            }

        identity = artifact.get("identity", {}) or {}
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        cold_check = _validate_cold_identity(
            identity, run_index=index, pretouch=0, prev_identity=st["prev_identity"],
        )
        artifact["run_id"] = _run_id
        artifact["attempt_file"] = f"attempt_{index:04d}.json"
        artifact["arm"] = label
        artifact["arm_attempt"] = arm_attempt
        artifact["mode"] = "backing_ab"
        artifact["start_ts"] = artifact.get("start_ts") or _start_ts
        artifact["end_ts"] = artifact.get("end_ts") or datetime.now(timezone.utc).isoformat()
        artifact["remote_entry_ts"] = artifact.get("remote_entry_ts") or _remote_entry_wall_iso(result)
        artifact["excluded_snapshot_builder"] = arm_attempt < skip_first
        if not artifact.get("error"):
            artifact["variance"] = {
                "quiesced_transfer": 0,
                "teardown_mode": teardown,
                "cold_valid": cold_check["cold_valid"],
                "cold": cold_check["cold"],
                "failures": cold_check["failures"],
                "freshness_checked": cold_check["freshness_checked"],
            }
        classification = _classify_attempt(artifact)
        artifact["classification"] = classification
        record = extract_run_metrics(artifact)
        record["classification"] = classification
        record["attempt_file"] = artifact["attempt_file"]
        record["arm"] = label
        record["arm_attempt"] = arm_attempt
        record["provider"] = identity.get("cloud", "")
        record["actual_region"] = identity.get("region", "")
        record["excluded_snapshot_builder"] = arm_attempt < skip_first
        record["host_diagnostics"] = artifact.get("host_diagnostics", {})
        record["synth_h2d"] = _extract_synth_probe(result)
        record["unet_backing_evidence"] = artifact.get("unet_backing_evidence", {})
        record["gpu_uuid"] = _host_gpu_uuid(record)
        _metrics = record.get("metrics", {}) if isinstance(record.get("metrics"), dict) else {}
        _p = _metrics.get("page_traversal", {}) if isinstance(_metrics.get("page_traversal"), dict) else {}
        _transfer_ms = _p.get("cpu_to_gpu_transfer_wall_ms")
        record["transfer_speed"] = _classify_transfer_speed(_transfer_ms)
        record["transfer_ms"] = _transfer_ms
        record["attempt_log"] = (
            f"[backing_ab] arm={label} index={index} class={classification} "
            f"speed={record['transfer_speed']}"
        )
        (output_dir / artifact["attempt_file"]).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        records.append(record)

        if arm_attempt < skip_first:
            st["skipped"] += 1
            status = "SKIPPED(snapshot-builder)"
        elif cold_check["cold"] and cold_check["cold_valid"]:
            st["cold"] += 1
            st["prev_identity"] = identity
            status = "COLD"
        else:
            status = "NOT-COLD"
        _synth = record.get("synth_h2d") or {}
        print(
            f"[v2.backing_ab] arm={label} index={index} id={_run_id} "
            f"provider={identity.get('cloud', '?')} region={identity.get('region', '?')} "
            f"status={status} speed={record['transfer_speed']} "
            f"synth={_fmt_ms(_synth.get('wall_ms'))} "
            f"valid={st['cold']}/{target_cold}",
            flush=True,
        )
        if total_attempts < max_attempts_per_arm * len(arms):
            print(f"[v2.backing_ab] phase=gap seconds={gap_seconds}", flush=True)
            await asyncio.sleep(gap_seconds)

    summary: dict[str, Any] = {
        "mode": "backing_ab",
        "app_a": app_a,
        "app_b": app_b,
        "class_name": class_name,
        "gpu": gpu,
        "gap_seconds": gap_seconds,
        "target_cold": target_cold,
        "max_attempts_per_arm": max_attempts_per_arm,
        "skip_first": skip_first,
        "teardown_mode": teardown,
        "total_attempts": total_attempts,
        "arms": {
            label: {
                "attempts": len(st["attempts"]),
                "skipped_snapshot_builders": st["skipped"],
                "valid_cold": st["cold"],
            }
            for label, st in per_arm.items()
        },
        "records": records,
    }
    (output_dir / "summary.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
        encoding="utf-8",
    )
    _report_md = _render_backing_ab_report(summary)
    (output_dir / "backing_ab_report.md").write_text(_report_md, encoding="utf-8")
    print(f"[v2.backing_ab] report={output_dir / 'backing_ab_report.md'}", flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "total_attempts": total_attempts,
        "arms": summary["arms"],
    }, default=str), flush=True)
    print(_report_md, flush=True)

    _short: list[str] = [
        f"arm {label}: {st['cold']}/{target_cold} valid cold in {len(st['attempts'])} attempts"
        for label, st in per_arm.items()
        if st["cold"] < target_cold
    ]
    if _short:
        raise RuntimeError(
            f"backing_ab: incomplete arms ({'; '.join(_short)}); "
            f"attempts preserved in {output_dir}"
        )
    return summary


def _render_backing_ab_report(summary: dict[str, Any]) -> str:
    """Render the interleaved A/B UNET-backing study report (markdown)."""
    records = summary.get("records", []) or []
    _lines: list[str] = []
    _lines.append("# V2 UNET-Backing A/B Cold Study\n")
    _lines.append(
        f"- Arm A `{summary.get('app_a', '')}` = current CPU-snapshot UNET; "
        f"Arm B `{summary.get('app_b', '')}` = anonymous-RAM snapshot. "
        f"Interleaved A,B,A,B,... · GPU `{summary.get('gpu', '')}` · "
        f"gap `{summary.get('gap_seconds')}s` · teardown `{summary.get('teardown_mode', '')}`"
    )
    _lines.append(
        f"- Protocol: first {summary.get('skip_first', 2)} attempts per arm "
        f"excluded (snapshot/cache build + the run after); "
        f"{summary.get('target_cold', 0)} valid cold per arm.  Transfer classes: "
        f"FAST <2.5 s, MEDIUM 2.5–5 s, SLOW >5 s.  Synth probe = 2 GiB touched "
        f"anonymous contiguous float32 H2D immediately before the real transfer.\n"
    )
    _lines.append("| arm | attempt | class | provider | region | GPU uuid | synth H2D (ms) | synth GB/s | UNET tfr (ms) | UNET GB/s | speed | restore (ms) | sched (ms) | sampler wait (ms) |")
    _lines.append("|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in sorted(records, key=lambda x: (x.get("arm", ""), x.get("attempt_file", ""))):
        _metrics = r.get("metrics", {}) if isinstance(r.get("metrics"), dict) else {}
        _t = _metrics.get("transfer", {}) if isinstance(_metrics.get("transfer"), dict) else {}
        _p = _metrics.get("page_traversal", {}) if isinstance(_metrics.get("page_traversal"), dict) else {}
        _rst = _metrics.get("restore", {}) if isinstance(_metrics.get("restore"), dict) else {}
        _sp = _metrics.get("sampler", {}) if isinstance(_metrics.get("sampler"), dict) else {}
        _synth = r.get("synth_h2d", {}) if isinstance(r.get("synth_h2d"), dict) else {}
        _tag = "SKIP" if r.get("excluded_snapshot_builder") else r.get("classification", "")
        _lines.append(
            f"| {r.get('arm', '?')} | {r.get('attempt_file', '')} | {_tag} "
            f"| {r.get('provider', '?')} | {r.get('actual_region', '?')} "
            f"| {r.get('gpu_uuid', '?')} "
            f"| {_fmt_ms(_synth.get('wall_ms'))} "
            f"| {_fmt_gbps(_synth.get('gb_per_s'))} "
            f"| {_fmt_ms(_p.get('cpu_to_gpu_transfer_wall_ms'))} "
            f"| {_fmt_gbps(_p.get('cpu_to_gpu_transfer_gb_per_s'))} "
            f"| {r.get('transfer_speed', '?')} "
            f"| {_fmt_ms(_rst.get('restore_total_ms'))} "
            f"| {_fmt_ms(_t.get('pre_python_modal_scheduling_ms'))} "
            f"| {_fmt_ms(_sp.get('sampler_lane_wait_ms'))} |"
        )
    _lines.append("")

    # ── Per-arm summary (valid cold runs only) ──
    _lines.append("## Per arm (valid cold runs)\n")
    _lines.append("| arm | n | UNET tfr ms (median/range) | UNET GB/s (median) | synth ms (median/range) | synth GB/s (median) | FAST | MEDIUM | SLOW |")
    _lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for _arm in ("A", "B"):
        _group = [r for r in records
                  if r.get("arm") == _arm and not r.get("excluded_snapshot_builder")]
        _tfr = sorted(float(r["transfer_ms"]) for r in _group if isinstance(r.get("transfer_ms"), (int, float)))
        _synth_vals = [
            float(s.get("wall_ms")) for r in _group
            if isinstance(r.get("synth_h2d"), dict) and isinstance((s := r["synth_h2d"]).get("wall_ms"), (int, float))
        ]
        _synth_vals.sort()
        _tfr_med = _tfr[len(_tfr) // 2] if _tfr else None
        _tfr_range = f"{_tfr[0]:.0f}–{_tfr[-1]:.0f}" if _tfr else "?"
        _syn_med = _synth_vals[len(_synth_vals) // 2] if _synth_vals else None
        _syn_range = f"{_synth_vals[0]:.0f}–{_synth_vals[-1]:.0f}" if _synth_vals else "?"
        _tfr_gb = [float(r.get("metrics", {}).get("page_traversal", {}).get("cpu_to_gpu_transfer_gb_per_s")) for r in _group]
        _tfr_gb = sorted(g for g in _tfr_gb if g == g and g is not None)
        _syn_gb = [
            float(s.get("gb_per_s")) for r in _group
            if isinstance(r.get("synth_h2d"), dict) and isinstance((s := r["synth_h2d"]).get("gb_per_s"), (int, float))
        ]
        _syn_gb = sorted(g for g in _syn_gb if g == g)
        _n_fast = sum(1 for r in _group if r.get("transfer_speed") == "FAST")
        _n_med = sum(1 for r in _group if r.get("transfer_speed") == "MEDIUM")
        _n_slow = sum(1 for r in _group if r.get("transfer_speed") == "SLOW")
        _lines.append(
            f"| {_arm} | {len(_group)} | {_fmt_ms(_tfr_med)} ({_tfr_range}) "
            f"| {_fmt_gbps(_tfr_gb[len(_tfr_gb)//2] if _tfr_gb else None)} "
            f"| {_fmt_ms(_syn_med)} ({_syn_range}) "
            f"| {_fmt_gbps(_syn_gb[len(_syn_gb)//2] if _syn_gb else None)} "
            f"| {_n_fast} | {_n_med} | {_n_slow} |"
        )
    _lines.append("")

    # ── Backing evidence (snapshot-build attempts + per-run at-transfer) ──
    _lines.append("## Backing evidence (/proc/self/maps)\n")
    for _arm in ("A", "B"):
        _build_recs = [r for r in records
                       if r.get("arm") == _arm and r.get("excluded_snapshot_builder")]
        _ev = None
        for _r in _build_recs:
            _ev = _r.get("unet_backing_evidence", {})
            if _ev:
                break
        _lines.append(f"### Arm {_arm} (snapshot-build run)\n")
        if not _ev:
            _lines.append("(no backing evidence captured)\n")
            continue
        _lines.append(f"```json\n{json.dumps(_ev, indent=1, default=str)}\n```\n")
    _lines.append("### Per-run UNET backing at transfer time\n")
    _lines.append("| arm | attempt | tensors | anonymous | volume-file | unknown | predominant |")
    _lines.append("|---|---:|---:|---:|---:|---:|---|")
    for r in sorted(records, key=lambda x: (x.get("arm", ""), x.get("attempt_file", ""))):
        _synth = r.get("synth_h2d", {}) if isinstance(r.get("synth_h2d"), dict) else {}
        _ub = _synth.get("unet_backing", {}) if isinstance(_synth.get("unet_backing"), dict) else {}
        _counts = _ub.get("counts", {}) if isinstance(_ub.get("counts"), dict) else {}
        _tag = "SKIP" if r.get("excluded_snapshot_builder") else r.get("classification", "")
        _lines.append(
            f"| {r.get('arm', '?')} | {r.get('attempt_file', '')} ({_tag}) "
            f"| {_ub.get('tensors', '?')} | {_counts.get('anonymous', '?')} "
            f"| {_counts.get('volume', '?')} | {_counts.get('unknown', '?')} "
            f"| {_ub.get('predominant', '?')} |"
        )
    _lines.append("")
    return "\n".join(_lines)


PROVIDER_AWS_APP = os.environ.get(
    "COMFYMODAL_V2_PROVIDER_AWS_APP", "stable-modal-comfy-v2-provider-aws-shadow"
)
PROVIDER_GCP_APP = os.environ.get(
    "COMFYMODAL_V2_PROVIDER_GCP_APP", "stable-modal-comfy-v2-provider-gcp-shadow"
)


def _extract_page_path_probe(result: dict[str, Any]) -> dict[str, Any] | None:
    """Extract the per-run ``page_path_probe`` trace event metadata."""
    trace = result.get("trace", {}) if isinstance(result, dict) else {}
    events = trace.get("events", []) if isinstance(trace, dict) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("name") == "page_path_probe":
            metadata = event.get("metadata", {})
            return dict(metadata) if isinstance(metadata, dict) else {}
    return None


def _provider_from_cloud(cloud: str) -> str:
    """Map an identity cloud string to an arm provider ('aws'/'gcp'/'')."""
    _c = str(cloud or "").upper()
    if "AWS" in _c:
        return "aws"
    if "GCP" in _c:
        return "gcp"
    return ""


async def _run_provider_ab(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    gap_seconds: float,
    app_aws: str,
    app_gcp: str,
    class_name: str,
    gpu: str,
    target_cold: int,
    max_attempts_per_arm: int,
    skip_first: int = 2,
    teardown: str = "minimal",
    _runner: Any = None,
) -> dict[str, Any]:
    """Interleaved AWS-vs-GCP provider cold study with page-path isolation.

    Two shadow deployments pinned to cloud providers (``cloud=`` kwarg, no
    region pin): Arm aws and Arm gcp.  Strictly interleaved aws,gcp,aws,gcp,...
    so placement/scheduling noise is shared.  Each arm discards its first
    *skip_first* attempts (snapshot/cache build + the run after) and collects
    *target_cold* valid cold runs (restore_count==1 && request_count==1 &&
    fresh identity).  Any measured attempt whose reported provider does not
    match its arm is rejected (preserved, not counted).  Caps at
    *max_attempts_per_arm* attempts per arm.  Every attempt carries the
    page-path record (mincore residency before/after traversal, traversal
    bandwidth, real UNET H2D, contiguous 12.31 GB synthetic H2D, 454-storage
    synthetic H2D) plus host diagnostics and timing.
    """
    print(
        f"[v2.provider_ab] mode=start gap={gap_seconds}s target={target_cold} "
        f"max_per_arm={max_attempts_per_arm} skip_first={skip_first} "
        f"teardown={teardown} app_aws={app_aws} app_gcp={app_gcp}",
        flush=True,
    )
    arms: tuple[tuple[str, str], ...] = (("aws", app_aws), ("gcp", app_gcp))
    per_arm: dict[str, dict[str, Any]] = {
        label: {"app": app, "attempts": [], "cold": 0, "skipped": 0,
                "rejected": 0, "prev_identity": None}
        for label, app in arms
    }
    records: list[dict[str, Any]] = []
    total_attempts = 0
    round_robin_idx = 0

    while total_attempts < max_attempts_per_arm * len(arms):
        chosen: tuple[str, str] | None = None
        for _ in range(len(arms)):
            label, app = arms[round_robin_idx % len(arms)]
            round_robin_idx += 1
            st = per_arm[label]
            if st["cold"] < target_cold and len(st["attempts"]) < max_attempts_per_arm:
                chosen = (label, app)
                break
        if chosen is None:
            break
        label, app = chosen
        st = per_arm[label]
        os.environ["COMFYMODAL_V2_APP_NAME"] = app
        index = total_attempts
        total_attempts += 1
        arm_attempt = len(st["attempts"])
        st["attempts"].append(arm_attempt)
        _run_id = f"provider-ab-{label}-{arm_attempt}-{index}-{uuid.uuid4().hex[:8]}"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _variance_origin(
            index, pretouch=0, app_name=app, teardown=teardown,
            pin_transfer=0, quiesced_transfer=0,
        )
        origin["variance_mode"] = "provider_ab"
        origin["COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"] = "1"

        artifact: dict[str, Any] = {}
        try:
            if _runner is not None:
                artifact = await _runner(
                    index=index, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
            else:
                artifact = await _run_one(
                    index=index, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": index, "run_id": _run_id, "request_id": "",
                "identity": {}, "result": {}, "timing": {},
                "variance": {
                    "quiesced_transfer": 0, "teardown_mode": teardown,
                    "cold_valid": False, "cold": False,
                    "failures": [f"run raised: {str(exc)[:300]}"],
                },
                "start_ts": _start_ts, "end_ts": datetime.now(timezone.utc).isoformat(),
                "remote_entry_ts": "unavailable", "mode": "provider_ab",
                "error": str(exc)[:300],
            }

        identity = artifact.get("identity", {}) or {}
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        actual_provider = _provider_from_cloud(identity.get("cloud", ""))
        cold_check = _validate_cold_identity(
            identity, run_index=index, pretouch=0, prev_identity=st["prev_identity"],
        )
        artifact["run_id"] = _run_id
        artifact["attempt_file"] = f"attempt_{index:04d}.json"
        artifact["provider_arm"] = label
        artifact["arm_attempt"] = arm_attempt
        artifact["mode"] = "provider_ab"
        artifact["start_ts"] = artifact.get("start_ts") or _start_ts
        artifact["end_ts"] = artifact.get("end_ts") or datetime.now(timezone.utc).isoformat()
        artifact["remote_entry_ts"] = artifact.get("remote_entry_ts") or _remote_entry_wall_iso(result)
        artifact["excluded_snapshot_builder"] = arm_attempt < skip_first
        artifact["provider_mismatch"] = bool(actual_provider and actual_provider != label)
        if not artifact.get("error"):
            artifact["variance"] = {
                "quiesced_transfer": 0,
                "teardown_mode": teardown,
                "cold_valid": cold_check["cold_valid"],
                "cold": cold_check["cold"],
                "failures": cold_check["failures"],
                "freshness_checked": cold_check["freshness_checked"],
            }
        classification = _classify_attempt(artifact)
        artifact["classification"] = classification
        record = extract_run_metrics(artifact)
        record["classification"] = classification
        record["attempt_file"] = artifact["attempt_file"]
        record["provider_arm"] = label
        record["arm_attempt"] = arm_attempt
        record["provider"] = identity.get("cloud", "")
        record["actual_region"] = identity.get("region", "")
        record["excluded_snapshot_builder"] = arm_attempt < skip_first
        record["provider_mismatch"] = artifact["provider_mismatch"]
        record["host_diagnostics"] = artifact.get("host_diagnostics", {})
        record["page_path"] = _extract_page_path_probe(result)
        record["gpu_uuid"] = _host_gpu_uuid(record)
        _metrics = record.get("metrics", {}) if isinstance(record.get("metrics"), dict) else {}
        _p = _metrics.get("page_traversal", {}) if isinstance(_metrics.get("page_traversal"), dict) else {}
        _transfer_ms = _p.get("cpu_to_gpu_transfer_wall_ms")
        record["transfer_speed"] = _classify_transfer_speed(_transfer_ms)
        record["transfer_ms"] = _transfer_ms
        record["attempt_log"] = (
            f"[provider_ab] arm={label} index={index} class={classification} "
            f"speed={record['transfer_speed']} actual={actual_provider or '?'}"
        )
        (output_dir / artifact["attempt_file"]).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        records.append(record)

        if arm_attempt < skip_first:
            st["skipped"] += 1
            status = "SKIPPED(snapshot-builder)"
        elif artifact["provider_mismatch"]:
            st["rejected"] += 1
            status = f"REJECTED(provider={actual_provider or '?'})"
        elif cold_check["cold"] and cold_check["cold_valid"]:
            st["cold"] += 1
            st["prev_identity"] = identity
            status = "COLD"
        else:
            status = "NOT-COLD"
        print(
            f"[v2.provider_ab] arm={label} index={index} id={_run_id} "
            f"provider={identity.get('cloud', '?')} region={identity.get('region', '?')} "
            f"status={status} speed={record['transfer_speed']} "
            f"valid={st['cold']}/{target_cold}",
            flush=True,
        )
        if total_attempts < max_attempts_per_arm * len(arms):
            print(f"[v2.provider_ab] phase=gap seconds={gap_seconds}", flush=True)
            await asyncio.sleep(gap_seconds)

    summary: dict[str, Any] = {
        "mode": "provider_ab",
        "app_aws": app_aws,
        "app_gcp": app_gcp,
        "class_name": class_name,
        "gpu": gpu,
        "gap_seconds": gap_seconds,
        "target_cold": target_cold,
        "max_attempts_per_arm": max_attempts_per_arm,
        "skip_first": skip_first,
        "teardown_mode": teardown,
        "total_attempts": total_attempts,
        "arms": {
            label: {
                "attempts": len(st["attempts"]),
                "skipped_snapshot_builders": st["skipped"],
                "rejected_provider_mismatch": st["rejected"],
                "valid_cold": st["cold"],
            }
            for label, st in per_arm.items()
        },
        "records": records,
    }
    (output_dir / "summary.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "records"}, default=str, indent=2),
        encoding="utf-8",
    )
    _report_md = _render_provider_ab_report(summary)
    (output_dir / "provider_ab_report.md").write_text(_report_md, encoding="utf-8")
    print(f"[v2.provider_ab] report={output_dir / 'provider_ab_report.md'}", flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "total_attempts": total_attempts,
        "arms": summary["arms"],
    }, default=str), flush=True)
    print(_report_md, flush=True)

    _short: list[str] = [
        f"arm {label}: {st['cold']}/{target_cold} valid cold in {len(st['attempts'])} attempts"
        for label, st in per_arm.items()
        if st["cold"] < target_cold
    ]
    if _short:
        raise RuntimeError(
            f"provider_ab: incomplete arms ({'; '.join(_short)}); "
            f"attempts preserved in {output_dir}"
        )
    return summary


def _render_provider_ab_report(summary: dict[str, Any]) -> str:
    """Render the interleaved AWS/GCP provider + page-path report (markdown)."""
    records = summary.get("records", []) or []
    _lines: list[str] = []
    _lines.append("# V2 Provider (AWS vs GCP) + Page-Path Cold Study\n")
    _lines.append(
        f"- Arm aws `{summary.get('app_aws', '')}` = cloud-pinned AWS (no region); "
        f"Arm gcp `{summary.get('app_gcp', '')}` = cloud-pinned GCP (no region). "
        f"Interleaved aws,gcp,aws,gcp,... · GPU `{summary.get('gpu', '')}` · "
        f"gap `{summary.get('gap_seconds')}s` · teardown `{summary.get('teardown_mode', '')}`"
    )
    _lines.append(
        f"- Protocol: first {summary.get('skip_first', 2)} attempts per arm excluded "
        f"(snapshot/cache build + the run after); {summary.get('target_cold', 0)} valid "
        f"cold per arm; provider-mismatch attempts rejected.  Per-run ordering: "
        f"mincore-before -> native traversal -> mincore-after -> real UNET H2D -> "
        f"12.31 GB contiguous synthetic H2D -> 454-storage synthetic H2D "
        f"(synthetic cases run after the real transfer and are allocated/measured/"
        f"freed separately).  Transfer classes: FAST <2.5 s, MEDIUM 2.5–5 s, SLOW >5 s.\n"
    )
    _lines.append("| arm | attempt | class | provider | region | GPU uuid | resid-before % | traversal (ms) | trav GB/s | resid-after % | real H2D (ms) | real GB/s | 12.3G contig (ms) | contig GB/s | 454-stor (ms) | 454 GB/s | restore (ms) | sched (ms) | cmd→resp (ms) |")
    _lines.append("|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in sorted(records, key=lambda x: (x.get("provider_arm", ""), x.get("attempt_file", ""))):
        _metrics = r.get("metrics", {}) if isinstance(r.get("metrics"), dict) else {}
        _t = _metrics.get("transfer", {}) if isinstance(_metrics.get("transfer"), dict) else {}
        _p = _metrics.get("page_traversal", {}) if isinstance(_metrics.get("page_traversal"), dict) else {}
        _rst = _metrics.get("restore", {}) if isinstance(_metrics.get("restore"), dict) else {}
        _pp = r.get("page_path", {}) if isinstance(r.get("page_path"), dict) else {}
        _rb = _pp.get("residency_before", {}) if isinstance(_pp.get("residency_before"), dict) else {}
        _ra = _pp.get("residency_after_traversal", {}) if isinstance(_pp.get("residency_after_traversal"), dict) else {}
        _tr = _pp.get("traversal", {}) if isinstance(_pp.get("traversal"), dict) else {}
        _real = _pp.get("real_unet_h2d", {}) if isinstance(_pp.get("real_unet_h2d"), dict) else {}
        _cont = _pp.get("contiguous_h2d", {}) if isinstance(_pp.get("contiguous_h2d"), dict) else {}
        _multi = _pp.get("multi_storage_h2d", {}) if isinstance(_pp.get("multi_storage_h2d"), dict) else {}
        _tag = "SKIP" if r.get("excluded_snapshot_builder") else r.get("classification", "")
        if r.get("provider_mismatch"):
            _tag = "REJECTED"
        _rb_pct = f"{float(_rb.get('resident_fraction', 0) or 0) * 100:.1f}" if _rb.get("total_pages") else "?"
        _ra_pct = f"{float(_ra.get('resident_fraction', 0) or 0) * 100:.1f}" if _ra.get("total_pages") else "?"
        _lines.append(
            f"| {r.get('provider_arm', '?')} | {r.get('attempt_file', '')} | {_tag} "
            f"| {r.get('provider', '?')} | {r.get('actual_region', '?')} | {r.get('gpu_uuid', '?')} "
            f"| {_rb_pct} | {_fmt_ms(_tr.get('wall_ms'))} | {_fmt_gbps(_tr.get('effective_gb_per_s'))} "
            f"| {_ra_pct} | {_fmt_ms(_real.get('wall_ms'))} | {_fmt_gbps(_real.get('effective_gb_per_s'))} "
            f"| {_fmt_ms(_cont.get('wall_ms'))} | {_fmt_gbps(_cont.get('gb_per_s'))} "
            f"| {_fmt_ms(_multi.get('wall_ms'))} | {_fmt_gbps(_multi.get('gb_per_s'))} "
            f"| {_fmt_ms(_rst.get('restore_total_ms'))} "
            f"| {_fmt_ms(_t.get('pre_python_modal_scheduling_ms'))} "
            f"| {_fmt_ms(_t.get('command_to_response_ms'))} |"
        )
    _lines.append("")

    # ── Per-provider summary (valid cold runs only) ──
    _lines.append("## Per provider (valid cold runs)\n")
    _lines.append("| arm | n | real H2D ms (med/range) | real GB/s (med) | >5 s count | traversal ms (med/range) | resid-before % (med) | resid-after % (med) | contig 12.3G ms (med) | contig GB/s (med) | 454-stor ms (med) | 454 GB/s (med) | restore ms (med) | sched ms (med) | cmd→resp ms (med) |")
    _lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for _arm in ("aws", "gcp"):
        _group = [r for r in records
                  if r.get("provider_arm") == _arm and not r.get("excluded_snapshot_builder")
                  and not r.get("provider_mismatch")]
        _vals = {k: [] for k in ("real", "trav", "cont", "multi", "restore", "sched", "cmd")}
        _rb_med = _ra_med = None
        for r in _group:
            _pp = r.get("page_path", {}) if isinstance(r.get("page_path"), dict) else {}
            _real = _pp.get("real_unet_h2d", {}) if isinstance(_pp.get("real_unet_h2d"), dict) else {}
            _tr = _pp.get("traversal", {}) if isinstance(_pp.get("traversal"), dict) else {}
            _cont = _pp.get("contiguous_h2d", {}) if isinstance(_pp.get("contiguous_h2d"), dict) else {}
            _multi = _pp.get("multi_storage_h2d", {}) if isinstance(_pp.get("multi_storage_h2d"), dict) else {}
            _rb = _pp.get("residency_before", {}) if isinstance(_pp.get("residency_before"), dict) else {}
            _ra = _pp.get("residency_after_traversal", {}) if isinstance(_pp.get("residency_after_traversal"), dict) else {}
            _metrics = r.get("metrics", {}) if isinstance(r.get("metrics"), dict) else {}
            _t = _metrics.get("transfer", {}) if isinstance(_metrics.get("transfer"), dict) else {}
            _rst = _metrics.get("restore", {}) if isinstance(_metrics.get("restore"), dict) else {}
            for _k, _v in (("real", _real.get("wall_ms")), ("trav", _tr.get("wall_ms")),
                           ("cont", _cont.get("wall_ms")), ("multi", _multi.get("wall_ms")),
                           ("restore", _rst.get("restore_total_ms")),
                           ("sched", _t.get("pre_python_modal_scheduling_ms")),
                           ("cmd", _t.get("command_to_response_ms"))):
                if isinstance(_v, (int, float)):
                    _vals[_k].append(float(_v))
            _rb_f = _rb.get("resident_fraction")
            _ra_f = _ra.get("resident_fraction")
            if isinstance(_rb_f, (int, float)):
                _rb_med = _rb_f if _rb_med is None else (_rb_med + _rb_f) / 2
            if isinstance(_ra_f, (int, float)):
                _ra_med = _ra_f if _ra_med is None else (_ra_med + _ra_f) / 2

        def _med(xs):
            _s = sorted(xs)
            return _s[len(_s) // 2] if _s else None

        def _rng(xs):
            _s = sorted(xs)
            return f"{_s[0]:.0f}–{_s[-1]:.0f}" if _s else "?"

        _real_vals = _vals["real"]
        _over5 = sum(1 for v in _real_vals if v > 5000.0)
        _gb = {}
        for r in _group:
            _pp = r.get("page_path", {}) if isinstance(r.get("page_path"), dict) else {}
            _real = _pp.get("real_unet_h2d", {}) if isinstance(_pp.get("real_unet_h2d"), dict) else {}
            _cont = _pp.get("contiguous_h2d", {}) if isinstance(_pp.get("contiguous_h2d"), dict) else {}
            _multi = _pp.get("multi_storage_h2d", {}) if isinstance(_pp.get("multi_storage_h2d"), dict) else {}
            for _k, _src in (("real_gb", _real), ("cont_gb", _cont), ("multi_gb", _multi)):
                _v = _src.get("effective_gb_per_s") if _k == "real_gb" else _src.get("gb_per_s")
                if isinstance(_v, (int, float)):
                    _gb.setdefault(_k, []).append(float(_v))
        _lines.append(
            f"| {_arm} | {len(_group)} | {_fmt_ms(_med(_real_vals))} ({_rng(_real_vals)}) "
            f"| {_fmt_gbps(_med(_gb.get('real_gb', [])))} | {_over5}/{len(_real_vals)} "
            f"| {_fmt_ms(_med(_vals['trav']))} ({_rng(_vals['trav'])}) "
            f"| {f'{_rb_med * 100:.1f}' if _rb_med is not None else '?'} "
            f"| {f'{_ra_med * 100:.1f}' if _ra_med is not None else '?'} "
            f"| {_fmt_ms(_med(_vals['cont']))} | {_fmt_gbps(_med(_gb.get('cont_gb', [])))} "
            f"| {_fmt_ms(_med(_vals['multi']))} | {_fmt_gbps(_med(_gb.get('multi_gb', [])))} "
            f"| {_fmt_ms(_med(_vals['restore']))} | {_fmt_ms(_med(_vals['sched']))} "
            f"| {_fmt_ms(_med(_vals['cmd']))} |"
        )
    _lines.append("")
    return "\n".join(_lines)


async def _run_variance_matrix(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    gap_seconds: float,
    app_name: str,
    class_name: str,
    gpu: str,
    target_per_condition: int,
    max_total_attempts: int,
    slow_threshold_ms: float,
    teardown: str = "full",
    pin_transfer: int = 0,
    _runner: Any = None,
) -> dict[str, Any]:
    """Four-condition round-robin cold scheduler.

    Round-robins across (diagnostics off/on) x (pretouch off/on).  Keeps
    attempting each condition until it reaches *target_per_condition* valid
    cold runs or the global attempt cap is hit.  Every attempt — including
    failed, warm/invalid, slow and snapshot-capture runs — is preserved as
    ``attempt_<seq>.json`` with a unique attempt ID and the full result trace.
    Produces one consolidated ``variance_matrix_handoff.md`` + ``summary.json``.
    """
    print(
        f"[v2.variance_matrix] mode=start gap={gap_seconds}s target={target_per_condition} "
        f"max_attempts={max_total_attempts} slow_threshold_ms={slow_threshold_ms} "
        f"teardown={teardown} pin_transfer={pin_transfer} app={app_name}",
        flush=True,
    )
    per_cond: dict[str, dict[str, Any]] = {}
    for diag, pretouch in MATRIX_CONDITIONS:
        label = MATRIX_CONDITION_LABEL(diag, pretouch)
        per_cond[label] = {"diag": diag, "pretouch": pretouch, "attempts": [],
                           "cold_count": 0, "prev_identity": None}

    records: list[dict[str, Any]] = []
    total_attempts = 0
    global_seq = 0
    round_robin_idx = 0
    target_met = False

    while total_attempts < max_total_attempts:
        # ── Round-robin pick the next condition that still needs cold runs ──
        chosen: tuple[int, int] | None = None
        for _ in range(len(MATRIX_CONDITIONS)):
            cond = MATRIX_CONDITIONS[round_robin_idx % len(MATRIX_CONDITIONS)]
            round_robin_idx += 1
            label = MATRIX_CONDITION_LABEL(*cond)
            if per_cond[label]["cold_count"] < target_per_condition:
                chosen = cond
                break
        if chosen is None:
            target_met = True
            break  # every condition has reached its target

        diag, pretouch = chosen
        label = MATRIX_CONDITION_LABEL(diag, pretouch)
        state = per_cond[label]
        total_attempts += 1
        global_seq += 1
        attempt_seq_in_cond = len(state["attempts"])
        attempt_id = f"matrix-{label}-{attempt_seq_in_cond}-{global_seq}-{uuid.uuid4().hex[:8]}"
        attempt_file = f"attempt_{global_seq:04d}.json"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _matrix_origin(global_seq, diag, pretouch, app_name, teardown=teardown, pin_transfer=pin_transfer)

        artifact: dict[str, Any] = {}
        try:
            if _runner is not None:
                artifact = await _runner(
                    index=global_seq, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
            else:
                artifact = await _run_one(
                    index=global_seq, workflow=workflow, modal_options=modal_options,
                    workspace=workspace, transport=transport, output_dir=output_dir,
                    _extra_origin=origin, _defer_waterfall=True,
                )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": global_seq, "run_id": attempt_id, "request_id": "",
                "identity": {}, "result": {}, "timing": {},
                "variance": {"pretouch": pretouch, "pin_transfer": pin_transfer,
                             "teardown_mode": teardown,
                             "cold_valid": False, "cold": False,
                             "failures": [f"run raised: {str(exc)[:300]}"]},
                "start_ts": _start_ts, "end_ts": datetime.now(timezone.utc).isoformat(),
                "remote_entry_ts": "unavailable", "mode": "variance_matrix",
                "error": str(exc)[:300],
            }

        # ── Augment with matrix metadata and write the raw attempt file ──
        identity = artifact.get("identity", {}) or {}
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        cold_check = _validate_cold_identity(
            identity, run_index=global_seq, pretouch=pretouch, prev_identity=state["prev_identity"],
        )
        artifact.setdefault("run_id", attempt_id)
        artifact["attempt_id"] = attempt_id
        artifact["attempt_file"] = attempt_file
        artifact["condition_label"] = label
        artifact["diag"] = diag
        artifact["mode"] = "variance_matrix"
        artifact["start_ts"] = artifact.get("start_ts") or _start_ts
        artifact["end_ts"] = artifact.get("end_ts") or datetime.now(timezone.utc).isoformat()
        artifact["remote_entry_ts"] = artifact.get("remote_entry_ts") or _remote_entry_wall_iso(result)
        if not artifact.get("error"):
            artifact["variance"] = {
                "pretouch": pretouch,
                "pin_transfer": pin_transfer,
                "teardown_mode": teardown,
                "cold_valid": cold_check["cold_valid"],
                "cold": cold_check["cold"],
                "failures": cold_check["failures"],
                "freshness_checked": cold_check["freshness_checked"],
            }
        classification = _classify_attempt(artifact)
        artifact["classification"] = classification
        # Extract metrics FIRST so the fixed slow flags can use the trace-derived
        # UNET activation duration (not only raw artifact.timing).
        record = extract_run_metrics(artifact)
        slow_flags = _classify_slow(record)
        artifact["slow_flags"] = slow_flags
        record["slow_flags"] = slow_flags
        record["classification"] = classification
        record["attempt_id"] = attempt_id
        record["attempt_file"] = attempt_file
        record["condition_label"] = label
        record["diag"] = diag
        # Runner logs / stderr are embedded when the runner supplied them;
        # otherwise the full result trace in the attempt JSON is the log.
        artifact["runner_log"] = artifact.get("runner_log", "")
        artifact["attempt_log"] = artifact.get("attempt_log",
                                               f"[matrix] cond={label} class={classification}")
        record["attempt_log"] = artifact["attempt_log"]
        (output_dir / attempt_file).write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )

        records.append(record)

        if classification == "cold":
            state["cold_count"] += 1
            state["prev_identity"] = identity
        print(
            f"[v2.variance_matrix] seq={global_seq} id={attempt_id} cond={label} "
            f"class={classification} cold={state['cold_count']}/{target_per_condition}",
            flush=True,
        )

        if total_attempts < max_total_attempts:
            needs = any(
                per_cond[MATRIX_CONDITION_LABEL(*c)]["cold_count"] < target_per_condition
                for c in MATRIX_CONDITIONS
            )
            if needs:
                print(f"[v2.variance_matrix] phase=gap seconds={gap_seconds}", flush=True)
                await asyncio.sleep(gap_seconds)

    meta = {
        "mode": "variance_matrix",
        "app_name": app_name,
        "class_name": class_name,
        "gpu": gpu,
        "gap_seconds": gap_seconds,
        "target_per_condition": target_per_condition,
        "max_total_attempts": max_total_attempts,
        "slow_threshold_ms": slow_threshold_ms,
        "teardown_mode": teardown,
    }
    summary = build_matrix_summary(
        records, MATRIX_CONDITIONS, meta=meta, slow_threshold_ms=slow_threshold_ms,
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    handoff = render_matrix_report(summary, output_dir)
    (output_dir / "variance_matrix_handoff.md").write_text(handoff, encoding="utf-8")
    print(json.dumps({
        "output_dir": str(output_dir),
        "mode": "variance_matrix",
        "total_attempts": summary["total_attempts"],
        "total_cold": summary["total_cold"],
        "target_per_condition": target_per_condition,
        "target_met": target_met,
        "per_condition_cold": {k: p["cold_count"] for k, p in summary["per_condition"].items()},
    }, default=str), flush=True)

    if not target_met:
        raise RuntimeError(
            "variance_matrix: reached the total-attempt cap before every condition "
            f"collected {target_per_condition} valid cold runs; attempts preserved in "
            f"{output_dir}"
        )
    return summary


def _volume_read_validity(attempt: dict[str, Any]) -> tuple[bool, list[str], bool]:
    """Validity for one mounted-Volume read attempt.

    Valid only when: no method error, stat size > 0, ``bytes_read`` equals
    ``stat_size_bytes`` on BOTH passes, both pass timings are positive, and the
    cold identity gate is satisfied whenever a freshness token is available.
    Returns ``(valid, failures, cold_gate_available)``.
    """
    failures: list[str] = []
    result = attempt.get("result") or {}
    if attempt.get("error"):
        failures.append(f"run error: {attempt['error']}")
    status = result.get("status")
    if status != "ok":
        failures.append(f"method error: status={status!r} error={result.get('error') or 'none'}")
    stat_size = result.get("stat_size_bytes")
    if not isinstance(stat_size, int) or stat_size <= 0:
        failures.append(f"stat_size_bytes invalid: {stat_size!r}")
    passes = result.get("passes") or []
    if len(passes) != 2:
        failures.append(f"expected 2 passes, got {len(passes)}")
    for p in passes:
        label = p.get("label", "?")
        if stat_size is not None and p.get("bytes_read") != stat_size:
            failures.append(
                f"{label}: bytes_read={p.get('bytes_read')} != stat_size={stat_size}"
            )
        wall_ms = p.get("wall_ms")
        if not isinstance(wall_ms, (int, float)) or wall_ms <= 0:
            failures.append(f"{label}: non-positive wall_ms={wall_ms!r}")
    identity = attempt.get("identity") or {}
    cold_gate_available = bool(_cold_identity_key(identity))
    cold_check = attempt.get("cold_check") or {}
    if cold_gate_available and not cold_check.get("cold"):
        failures.append(
            "cold identity gate failed: "
            + "; ".join(str(f) for f in cold_check.get("failures", [])[:3])
        )
    return len(failures) == 0, failures, cold_gate_available


def _volume_read_pass_stats(
    records: list[dict[str, Any]], key: str, label: str,
) -> dict[str, Any]:
    """collect numeric values for one pass metric across valid attempts."""
    values: list[float] = []
    for r in records:
        if not r.get("valid"):
            continue
        result = r.get("result") or {}
        passes = result.get("passes") or []
        for p in passes:
            if p.get("label") != label:
                continue
            v = p.get(key)
            if isinstance(v, (int, float)) and v > 0:
                values.append(float(v))
    return compute_stats(values)


def _volume_read_summary(
    records: list[dict[str, Any]],
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    valid = [r for r in records if r.get("valid")]
    dnf = [r for r in records if r.get("dnf")]
    cold = [r for r in records if (r.get("cold_check") or {}).get("cold")]
    gate_available = [r for r in records if r.get("cold_gate_available")]
    stat_size: int | None = None
    for r in records:
        result = r.get("result") or {}
        if isinstance(result.get("stat_size_bytes"), int) and result["stat_size_bytes"] > 0:
            stat_size = result["stat_size_bytes"]
            break
    return {
        "mode": "volume_read",
        "meta": meta or {},
        "run_count": len(records),
        "valid_count": len(valid),
        "dnf_count": len(dnf),
        "invalid_count": len(records) - len(valid) - len(dnf),
        "cold_count": len(cold),
        "cold_gate_available_count": len(gate_available),
        "stat_size_bytes": stat_size,
        "first_pass": {
            "wall_ms": _volume_read_pass_stats(
                records, "wall_ms", VOLUME_READ_PASS_LABELS[0],
            ),
            "decimal_GBps": _volume_read_pass_stats(
                records, "decimal_GBps", VOLUME_READ_PASS_LABELS[0],
            ),
            "binary_GiBps": _volume_read_pass_stats(
                records, "binary_GiBps", VOLUME_READ_PASS_LABELS[0],
            ),
        },
        "warm_pass": {
            "wall_ms": _volume_read_pass_stats(
                records, "wall_ms", VOLUME_READ_PASS_LABELS[1],
            ),
            "decimal_GBps": _volume_read_pass_stats(
                records, "decimal_GBps", VOLUME_READ_PASS_LABELS[1],
            ),
            "binary_GiBps": _volume_read_pass_stats(
                records, "binary_GiBps", VOLUME_READ_PASS_LABELS[1],
            ),
        },
        "runs": [{
            "run_index": r["run_index"],
            "run_id": r.get("run_id"),
            "valid": r.get("valid"),
            "dnf": r.get("dnf"),
            "cold": bool((r.get("cold_check") or {}).get("cold")),
            "cold_gate_available": r.get("cold_gate_available"),
            "failures": r.get("failures"),
            "identity": r.get("identity"),
            "result": r.get("result"),
        } for r in records],
    }


def _render_volume_read_table(summary: dict[str, Any]) -> str:
    def _cell(stats: dict[str, Any]) -> str:
        median = stats.get("median")
        if median is None:
            return "n/a"
        return f"{median:.3f}"

    meta = summary.get("meta") or {}
    lines = [
        "=== V2 mounted-Volume raw sequential-read benchmark ===",
        f"file={meta.get('filename', '')} "
        f"chunk={meta.get('chunk_bytes', '')} "
        f"stat_size={summary.get('stat_size_bytes')} "
        f"runs={summary.get('run_count')}",
        f"valid={summary.get('valid_count')} "
        f"invalid={summary.get('invalid_count')} "
        f"dnf={summary.get('dnf_count')} "
        f"cold={summary.get('cold_count')}",
        "metric                    first(p50)   warm(p50)",
        f"read_loop_wall_ms         {_cell(summary.get('first_pass', {}).get('wall_ms') or {}):>10}   {_cell(summary.get('warm_pass', {}).get('wall_ms') or {}):>10}",
        f"decimal_GBps              {_cell(summary.get('first_pass', {}).get('decimal_GBps') or {}):>10}   {_cell(summary.get('warm_pass', {}).get('decimal_GBps') or {}):>10}",
        f"binary_GiBps              {_cell(summary.get('first_pass', {}).get('binary_GiBps') or {}):>10}   {_cell(summary.get('warm_pass', {}).get('binary_GiBps') or {}):>10}",
    ]
    return "\n".join(lines)


async def _run_volume_read(
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    run_count: int,
    gap_seconds: float,
    filename: str,
    chunk_bytes: int,
    app_name: str,
    class_name: str,
    gpu: str,
) -> dict[str, Any]:
    """Run the mounted-Volume raw sequential-read benchmark.

    One remote call per attempt against the existing V2 deployment.  Each
    attempt returns two read passes (primary mounted-volume + immediate
    warm-cache) with identity tokens; cold identity is validated with the
    shared ``_validate_cold_identity`` gate.  Failed attempts are recorded DNF
    (no hidden retries).  Writes per-attempt JSON + ``summary.json``.
    """
    os.environ["COMFYMODAL_V2_APP_NAME"] = app_name
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = class_name
    os.environ["COMFYMODAL_V2_GPU"] = gpu
    print(
        f"[v2.volume_read] mode=start runs={run_count} gap={gap_seconds}s "
        f"file={filename} chunk={chunk_bytes} app={app_name}",
        flush=True,
    )
    handle = await asyncio.to_thread(
        transport._v2_handle, workspace=workspace, gpu=gpu,
    )
    records: list[dict[str, Any]] = []
    prev_identity: dict[str, Any] | None = None

    for index in range(run_count):
        _run_id = f"volume-read-{index}-{uuid.uuid4().hex[:8]}"
        _req_id = f"v2-volume-read-{index}-{uuid.uuid4().hex[:12]}"
        _start_ts = datetime.now(timezone.utc).isoformat()
        artifact: dict[str, Any] = {
            "run_index": index,
            "run_id": _run_id,
            "request_id": _req_id,
            "mode": "volume_read",
            "start_ts": _start_ts,
            "target": {"app_name": app_name, "class_name": class_name, "gpu": gpu},
            "config": {
                "filename": filename,
                "chunk_bytes": chunk_bytes,
                "gap_seconds": gap_seconds,
            },
            "identity": {},
            "cold_check": {},
            "cold_gate_available": False,
            "result": {},
            "valid": False,
            "dnf": False,
            "failures": [],
            "error": None,
        }
        identity: dict[str, Any] = {}
        try:
            fn = handle.run_volume_read_benchmark
            remote = getattr(fn, "remote", None)
            if remote is not None and callable(getattr(remote, "aio", None)):
                result = remote.aio(
                    request_id=_req_id, filename=filename, chunk_bytes=chunk_bytes,
                )
                if asyncio.iscoroutine(result):
                    result = await result
            elif asyncio.iscoroutinefunction(fn):
                result = await fn(
                    request_id=_req_id, filename=filename, chunk_bytes=chunk_bytes,
                )
            else:
                result = await asyncio.to_thread(
                    fn, request_id=_req_id, filename=filename, chunk_bytes=chunk_bytes,
                )
            if asyncio.iscoroutine(result):
                result = await result
            if not isinstance(result, dict):
                raise RuntimeError(f"remote returned non-dict: {type(result).__name__}")
            artifact["result"] = result
            identity = result.get("identity") or {}
            artifact["identity"] = identity
            cold_check = _validate_cold_identity(
                identity, run_index=index, pretouch=0, prev_identity=prev_identity,
            )
            artifact["cold_check"] = cold_check
            artifact["cold_gate_available"] = bool(_cold_identity_key(identity))
            valid, failures, _gate = _volume_read_validity(artifact)
            artifact["valid"] = valid
            artifact["failures"] = failures
        except Exception as exc:  # noqa: BLE001
            artifact["dnf"] = True
            artifact["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            artifact["failures"] = [artifact["error"]]

        artifact["end_ts"] = datetime.now(timezone.utc).isoformat()
        (output_dir / f"run_{index}.json").write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        records.append(artifact)

        status = "DNF" if artifact["dnf"] else ("VALID" if artifact["valid"] else "INVALID")
        print(
            f"[v2.volume_read] run={index} status={status} "
            f"cold={(artifact.get('cold_check') or {}).get('cold')} "
            f"gate_available={artifact['cold_gate_available']} "
            f"instance={identity.get('restored_instance_id', '')[:12]}",
            flush=True,
        )
        if artifact["failures"]:
            print(
                f"[v2.volume_read] run={index} failures={artifact['failures']}",
                flush=True,
            )
        if (artifact.get("cold_check") or {}).get("cold"):
            prev_identity = identity
        if index + 1 < run_count:
            print(f"[v2.volume_read] phase=gap seconds={gap_seconds}", flush=True)
            await asyncio.sleep(gap_seconds)

    meta = {
        "mode": "volume_read",
        "app_name": app_name,
        "class_name": class_name,
        "gpu": gpu,
        "run_count": run_count,
        "gap_seconds": gap_seconds,
        "filename": filename,
        "chunk_bytes": chunk_bytes,
        "cold_identity": (
            "variance-cold gate (restore_count==1, request_count==1, "
            "restored_instance_id nonempty, fresh container token); "
            "attempts without a freshness token never claim cold"
        ),
    }
    summary = _volume_read_summary(records, meta=meta)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    print(_render_volume_read_table(summary), flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "run_count": summary["run_count"],
        "valid_count": summary["valid_count"],
        "invalid_count": summary["invalid_count"],
        "dnf_count": summary["dnf_count"],
        "cold_count": summary["cold_count"],
    }, default=str), flush=True)
    return summary


def _restore_only_validity(attempt: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validity for one UNET-absent snapshot restore-only probe.

    Valid only when every decisive piece of evidence is present AND
    consistent: UNET-absence invariant (``unet_present=0``, no retained
    UNET payload, no reconstructed/snapshot UNET, exclusion gate on),
    non-empty snapshot identity, cloud/region/gpu placement, cold restore
    identity gate, container-observed Python restore timestamps (first
    restored Python instruction, restore start/end, total), method-entry
    timestamp, RSS, the locally captured dispatch timestamp, and the Modal
    log-server pre-Python ``Restoring Function from memory snapshot.``
    banner timestamp.  Any missing decisive timestamp/identity FAILS
    validity — never inferred.  Returns ``(valid, failures)``.
    """
    failures: list[str] = []
    result = attempt.get("result") or {}
    if attempt.get("error"):
        failures.append(f"run error: {attempt['error']}")
    status = result.get("status")
    if status != "ok":
        failures.append(
            f"method error: status={status!r} error={result.get('error') or 'none'}"
        )
    if result.get("mode") != RESTORE_ONLY_MODE:
        failures.append(f"mode mismatch: {result.get('mode')!r} != {RESTORE_ONLY_MODE!r}")
    invariant = result.get("invariant") or {}
    if invariant.get("unet_present") != 0:
        failures.append(
            f"invariant.unet_present={invariant.get('unet_present')!r}, expected 0"
        )
    if invariant.get("retained_unet_payload") != 0:
        failures.append(
            f"invariant.retained_unet_payload={invariant.get('retained_unet_payload')!r}, expected 0"
        )
    if invariant.get("reconstructed_unet_present") != 0:
        failures.append(
            f"invariant.reconstructed_unet_present={invariant.get('reconstructed_unet_present')!r}, expected 0"
        )
    if invariant.get("snapshot_exclude_unet_gate") != 1:
        failures.append(
            f"invariant.snapshot_exclude_unet_gate={invariant.get('snapshot_exclude_unet_gate')!r}, expected 1"
        )
    # Retained-container evidence (clip_vae eviction retain role): the
    # CpuSnapshotModels container must be present AND retained with
    # unet=None, carrying fresh CLIP and VAE.
    if invariant.get("cpu_snapshot_models_present") != 1:
        failures.append(
            "invariant.cpu_snapshot_models_present="
            f"{invariant.get('cpu_snapshot_models_present')!r}, expected 1"
        )
    if invariant.get("container_retained") != 1:
        failures.append(
            f"invariant.container_retained={invariant.get('container_retained')!r}, "
            "expected 1 (container retained with unet absent)"
        )
    if invariant.get("clip_present") != 1:
        failures.append(
            f"invariant.clip_present={invariant.get('clip_present')!r}, expected 1"
        )
    if invariant.get("vae_present") != 1:
        failures.append(
            f"invariant.vae_present={invariant.get('vae_present')!r}, expected 1"
        )
    snapshot_identity = str(result.get("snapshot_identity") or "")
    if not snapshot_identity:
        failures.append(
            "snapshot_identity empty/absent (cannot tie the probe to one snapshot)"
        )
    placement = result.get("placement") or {}
    for _k in ("cloud", "region", "gpu"):
        if not str(placement.get(_k) or ""):
            failures.append(f"placement.{_k} is empty/absent")
    timing = result.get("restore_timing") or {}
    resume_ns = _num(timing.get("remote_python_resume_wall_unix_ns"))
    start_ns = _num(timing.get("restore_method_start_wall_unix_ns"))
    end_ns = _num(timing.get("restore_method_end_wall_unix_ns"))
    total_ms = _num(timing.get("restore_total_ms"))
    if resume_ns is None or resume_ns <= 0:
        failures.append(
            "restore_timing.remote_python_resume_wall_unix_ns missing "
            "(first Python restore instruction not directly observed)"
        )
    if start_ns is None or start_ns <= 0:
        failures.append("restore_timing.restore_method_start_wall_unix_ns missing")
    if end_ns is None or end_ns <= 0:
        failures.append("restore_timing.restore_method_end_wall_unix_ns missing")
    if total_ms is None or total_ms <= 0:
        failures.append("restore_timing.restore_total_ms invalid")
    entry_ns = _num(result.get("entry_wall_unix_ns"))
    if entry_ns is None or entry_ns <= 0:
        failures.append("entry_wall_unix_ns missing")
    rss = result.get("rss") or {}
    rss_val = _num(rss.get("rss_mib"))
    if rss_val is None:
        rss_val = _num(rss.get("status_vmrss_mib"))
    if rss_val is None or rss_val <= 0:
        failures.append("rss missing/unavailable")
    identity = attempt.get("identity") or {}
    restored_instance_id = str(identity.get("restored_instance_id") or "")
    if not restored_instance_id:
        failures.append("restored_instance_id empty/absent")
    cold_check = attempt.get("cold_check") or {}
    if not cold_check.get("cold"):
        failures.append(
            "cold identity gate failed: "
            + "; ".join(str(f) for f in cold_check.get("failures", [])[:3])
        )
    banner_ms = attempt.get("banner_epoch_ms")
    if banner_ms is None or _num(banner_ms) is None or _num(banner_ms) <= 0:
        failures.append(
            "banner_epoch_ms missing (Modal pre-Python 'Restoring Function "
            "from memory snapshot.' not directly observed)"
        )
    dispatch_ms = attempt.get("dispatch_unix_ms")
    if dispatch_ms is None or _num(dispatch_ms) is None or _num(dispatch_ms) <= 0:
        failures.append("dispatch_unix_ms missing")
    return len(failures) == 0, failures


def _restore_only_intervals(attempt: dict[str, Any]) -> dict[str, Any]:
    """Requested intervals for one probe (best-effort; None when underivable)."""
    result = attempt.get("result") or {}
    timing = result.get("restore_timing") or {}
    resume_ns = _num(timing.get("remote_python_resume_wall_unix_ns"))
    entry_ns = _num(result.get("entry_wall_unix_ns"))
    banner_ms = _num(attempt.get("banner_epoch_ms"))
    dispatch_ms = _num(attempt.get("dispatch_unix_ms"))

    def _ms(ns: float | None) -> float | None:
        if ns is None:
            return None
        return round(ns / 1_000_000.0, 3)

    out: dict[str, Any] = {
        "dispatch_to_banner_ms": (
            round(banner_ms - dispatch_ms, 3)
            if banner_ms is not None and dispatch_ms is not None else None
        ),
        "pre_python_restore_ms": (
            round(_ms(resume_ns) - banner_ms, 3)
            if resume_ns is not None and banner_ms is not None else None
        ),
        "python_restore_total_ms": _num(timing.get("restore_total_ms")),
        "python_resume_to_method_entry_ms": (
            round(_ms(entry_ns) - _ms(resume_ns), 3)
            if entry_ns is not None and resume_ns is not None else None
        ),
        "banner_to_method_entry_ms": (
            round(_ms(entry_ns) - banner_ms, 3)
            if entry_ns is not None and banner_ms is not None else None
        ),
        "dispatch_to_method_entry_ms": (
            round(_ms(entry_ns) - dispatch_ms, 3)
            if entry_ns is not None and dispatch_ms is not None else None
        ),
    }
    return out


def _render_restore_only_table(summary: dict[str, Any]) -> str:
    meta = summary.get("meta") or {}
    lines = [
        "=== V2 UNET-absent snapshot restore-only benchmark ===",
        "app=%s gpu=%s target_valid=%s" % (
            meta.get("app_name", ""), meta.get("gpu", ""), meta.get("target_valid", ""),
        ),
        "attempts=%s valid=%s invalid=%s dnf=%s target_reached=%s" % (
            summary.get("attempt_count"), summary.get("valid_count"),
            summary.get("invalid_count"), summary.get("dnf_count"),
            summary.get("target_reached"),
        ),
        "run  status prePy_ms pyRestore_ms resume2entry_ms cloud/region",
    ]
    for r in summary.get("runs", []):
        result = r.get("result") or {}
        intervals = _restore_only_intervals(r)
        placement = result.get("placement") or {}

        def _cell_ms(key: str, width: int) -> str:
            value = intervals.get(key)
            if value is None:
                return " " * width
            try:
                return f"{float(value):>{width}.3f}"
            except (TypeError, ValueError):
                return " " * width

        status = "VALID" if r.get("valid") else ("DNF" if r.get("dnf") else "INVALID")
        lines.append(
            f"{r.get('run_index', '?'):<5} "
            f"{status:<6} "
            f"{_cell_ms('pre_python_restore_ms', 9)} "
            f"{_cell_ms('python_restore_total_ms', 13)} "
            f"{_cell_ms('python_resume_to_method_entry_ms', 16)} "
            f"{placement.get('cloud', '')}/{placement.get('region', '')}"
        )
    return "\n".join(lines)


# ── Restore-only banner log pairing ────────────────────────────────────────
# The pre-Python ``Restoring Function from memory snapshot.`` banner lives in
# the Modal SYSTEM/INFO log stream (api_pb2.FILE_DESCRIPTOR_INFO), while the
# probe's own method-entry anchor is a stdout print.  The default
# (UNSPECIFIED) log fetch sees stdout but not the platform system lines, so
# banner retrieval must merge BOTH streams and pair the nearest strictly
# preceding exact system banner to the request's own stdout anchor.
_RESTORE_ONLY_SOURCE_STDOUT = 1      # api_pb2.FILE_DESCRIPTOR_STDOUT
_RESTORE_ONLY_SOURCE_INFO = 3        # api_pb2.FILE_DESCRIPTOR_INFO
_RESTORE_ONLY_LOG_RETRY_COUNT = 6
_RESTORE_ONLY_BACKFILL_LIMIT = 6
_RESTORE_ONLY_RUN_FILE_RE = re.compile(r"^run_(\d+)\.json$")


def _restore_only_tasklog_entry(
    item: Any, *, fallback_source: str,
) -> dict[str, Any] | None:
    """Convert one Modal TaskLogs item into a log entry dict.

    Timestamp prefers ``timestamp_ns / 1e6`` (int64 wall ns) and falls back to
    ``timestamp * 1000`` (float seconds).  The ``source`` label is derived from
    the item's ``file_descriptor`` when present (system/INFO=3, stdout=1),
    otherwise the fetch-specific *fallback_source*.  Returns ``None`` when no
    usable timestamp or data is present.
    """
    ts_ns = getattr(item, "timestamp_ns", None)
    ts = getattr(item, "timestamp", None)
    epoch_ms: float | None = None
    if isinstance(ts_ns, int) and ts_ns > 0:
        epoch_ms = ts_ns / 1_000_000.0
    elif isinstance(ts, (int, float)) and ts > 0:
        epoch_ms = float(ts) * 1000.0
    if epoch_ms is None:
        return None
    raw = getattr(item, "data", b"")
    if isinstance(raw, str):
        text = raw
    else:
        text = (raw or b"").decode("utf-8", "replace")
    fd = getattr(item, "file_descriptor", None)
    if fd == _RESTORE_ONLY_SOURCE_INFO:
        source = "system_info"
    elif fd == _RESTORE_ONLY_SOURCE_STDOUT:
        source = "stdout"
    else:
        source = fallback_source or "unknown"
    return {
        "epoch_ms": epoch_ms,
        "text": text,
        "source": source,
        "timestamp_ns": int(ts_ns or 0),
        # Container correlation metadata preserved verbatim from the log item
        # (best-effort; empty when the server does not populate them).
        "container_id": str(getattr(item, "container_id", "") or ""),
        "container_name": str(getattr(item, "container_name", "") or ""),
    }


def _merge_restore_only_entries(
    entry_lists: list[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Merge per-source entry lists, dedupe, and sort ascending by timestamp.

    Dedupe key is ``(timestamp_ns, text)`` when ns is present, else
    ``(epoch_ms, text)``.  When one physical line appears in more than one
    source fetch the system/INFO-tagged entry wins so the platform banner can
    be matched as a system-source line.
    """
    _source_priority = {"system_info": 0, "unknown": 1, "stdout": 2}
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    for entries in entry_lists or ():
        for entry in entries or ():
            if not isinstance(entry, dict) or entry.get("epoch_ms") is None:
                continue
            if (entry.get("timestamp_ns") or 0) > 0:
                key = (int(entry["timestamp_ns"]), entry.get("text", ""))
            else:
                key = (round(float(entry["epoch_ms"]), 6), entry.get("text", ""))
            previous = merged.get(key)
            if previous is None or _source_priority.get(
                entry.get("source", "unknown"), 9
            ) < _source_priority.get(previous.get("source", "unknown"), 9):
                merged[key] = entry
    return sorted(
        merged.values(), key=lambda e: (float(e["epoch_ms"]), e.get("text", ""))
    )


def _restore_only_banner_candidate_summary(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compact, JSON-safe summary of exact banner candidates for diagnostics."""
    return [
        {
            "epoch_ms": round(float(e["epoch_ms"]), 3),
            "timestamp_ns": int(e.get("timestamp_ns") or 0),
            "source": e.get("source", ""),
            "container_id": e.get("container_id", ""),
            "text": (e.get("text") or "")[:160],
        }
        for e in candidates[:20]
    ]


def _pair_restore_only_banner(
    entries: list[dict[str, Any]],
    *,
    anchor: str,
    banner_text: str = RESTORE_ONLY_RESTORING_BANNER,
    banner_source: str = "system_info",
    dispatch_unix_ms: int | None = None,
    remote_python_resume_wall_unix_ns: int | None = None,
    task_scoped: bool = False,
    container_task_id: str | None = None,
) -> dict[str, Any]:
    """Pair the probe's banner evidence within caller-supplied time bounds.

    Standard mode (default) requires the request's stdout *anchor* and pairs
    it to the nearest strictly preceding exact system banner.

    Task-scoped mode (``task_scoped=True`` — used ONLY when the caller holds
    the exact Modal ``container_task_id`` and the task-scoped system query
    yielded exact banner lines) treats the system banner itself as direct
    evidence correlated by that task id: the stdout anchor is NOT required
    (``anchor_found`` is reported as observed).  The LATEST exact system
    banner satisfying ``dispatch <= banner <= remote_python_resume`` is
    selected; zero in-bounds candidates or multiple indistinguishable
    candidates (identical timestamps) fail closed, and candidate diagnostics
    are preserved on failure.  ``pair_status=paired_task_scoped`` and
    ``correlation=container_task_id`` mark success.  Never infers.
    """
    if task_scoped:
        return _pair_restore_only_banner_task_scoped(
            entries,
            anchor=anchor,
            banner_text=banner_text,
            banner_source=banner_source,
            dispatch_unix_ms=dispatch_unix_ms,
            remote_python_resume_wall_unix_ns=remote_python_resume_wall_unix_ns,
            container_task_id=container_task_id,
        )
    idx = next(
        (i for i, e in enumerate(entries) if anchor in (e.get("text") or "")),
        None,
    )
    if idx is None:
        return {
            "banner_epoch_ms": None, "pair_status": "anchor_missing",
            "anchor_found": False,
        }
    bi = max(
        (
            i for i in range(idx)
            if (entries[i].get("source") or "") == banner_source
            and (entries[i].get("text") or "").strip() == banner_text
        ),
        default=None,
    )
    if bi is None:
        return {
            "banner_epoch_ms": None, "pair_status": "banner_missing",
            "anchor_found": True,
        }
    banner_ms = float(entries[bi]["epoch_ms"])
    bounds_failures: list[str] = []
    if dispatch_unix_ms is not None and banner_ms < float(dispatch_unix_ms):
        bounds_failures.append(
            f"banner {banner_ms:.3f}ms precedes dispatch {dispatch_unix_ms}ms"
        )
    if (
        remote_python_resume_wall_unix_ns is not None
        and remote_python_resume_wall_unix_ns > 0
        and banner_ms > remote_python_resume_wall_unix_ns / 1_000_000.0
    ):
        bounds_failures.append(
            f"banner {banner_ms:.3f}ms after python resume "
            f"{remote_python_resume_wall_unix_ns / 1_000_000.0:.3f}ms"
        )
    if bounds_failures:
        return {
            "banner_epoch_ms": None, "pair_status": "bounds_failed",
            "anchor_found": True, "banner_candidate_epoch_ms": round(banner_ms, 3),
            "bounds_failures": bounds_failures,
            "dispatch_unix_ms": dispatch_unix_ms,
            "remote_python_resume_wall_unix_ns": remote_python_resume_wall_unix_ns,
        }
    return {
        "banner_epoch_ms": round(banner_ms, 3),
        "banner_log_line": (entries[bi].get("text") or "")[:160],
        "banner_timestamp_ns": int(entries[bi].get("timestamp_ns") or 0),
        "banner_source": entries[bi].get("source", ""),
        "method_entry_epoch_ms": round(float(entries[idx]["epoch_ms"]), 3),
        "method_entry_timestamp_ns": int(entries[idx].get("timestamp_ns") or 0),
        "pair_status": "paired",
        "anchor_found": True,
        "bounds_checked": True,
    }


def _pair_restore_only_banner_task_scoped(
    entries: list[dict[str, Any]],
    *,
    anchor: str,
    banner_text: str,
    banner_source: str,
    dispatch_unix_ms: int | None,
    remote_python_resume_wall_unix_ns: int | None,
    container_task_id: str | None,
) -> dict[str, Any]:
    """Task-id-correlated banner pairing (no stdout anchor required).

    Direct evidence: the system banner lines were returned by the task-scoped
    ``LogsFilters(source=FILE_DESCRIPTOR_INFO, task_id=container_task_id,
    search_text=banner)`` query, so they are correlated to this exact Modal
    task/container.  The LATEST exact system banner inside
    ``dispatch <= banner <= remote_python_resume`` is selected.  Zero
    in-bounds candidates or multiple indistinguishable candidates (identical
    timestamps) fail closed.  ``anchor_found`` is reported as observed, not
    assumed.  Candidate diagnostics are always preserved on failure.
    """
    anchor_idx = next(
        (i for i, e in enumerate(entries) if anchor in (e.get("text") or "")),
        None,
    )
    anchor_found = anchor_idx is not None
    candidates = [
        e for e in entries
        if (e.get("source") or "") == banner_source
        and (e.get("text") or "").strip() == banner_text
    ]
    candidate_count = len(candidates)
    diagnostics: dict[str, Any] = {
        "correlation": container_task_id,
        "candidate_count": candidate_count,
        "anchor_found": anchor_found,
        "banner_candidates": _restore_only_banner_candidate_summary(candidates),
    }
    if not candidates:
        return {
            "banner_epoch_ms": None,
            "pair_status": "task_scoped_banner_missing",
            **diagnostics,
        }
    bounded: list[dict[str, Any]] = []
    bounds_failures: list[str] = []
    for e in candidates:
        banner_ms = float(e["epoch_ms"])
        if dispatch_unix_ms is not None and banner_ms < float(dispatch_unix_ms):
            bounds_failures.append(
                f"banner {banner_ms:.3f}ms precedes dispatch {dispatch_unix_ms}ms"
            )
            continue
        if (
            remote_python_resume_wall_unix_ns is not None
            and remote_python_resume_wall_unix_ns > 0
            and banner_ms > remote_python_resume_wall_unix_ns / 1_000_000.0
        ):
            bounds_failures.append(
                f"banner {banner_ms:.3f}ms after python resume "
                f"{remote_python_resume_wall_unix_ns / 1_000_000.0:.3f}ms"
            )
            continue
        bounded.append(e)
    diagnostics["bounded_candidate_count"] = len(bounded)
    diagnostics["bounds_failures"] = bounds_failures
    if not bounded:
        return {
            "banner_epoch_ms": None,
            "pair_status": "task_scoped_bounds_failed",
            **diagnostics,
        }
    distinct_timestamps = {float(e["epoch_ms"]) for e in bounded}
    diagnostics["distinct_timestamps"] = len(distinct_timestamps)
    if len(bounded) > 1 and len(distinct_timestamps) != len(bounded):
        return {
            "banner_epoch_ms": None,
            "pair_status": "task_scoped_candidates_indistinguishable",
            **diagnostics,
        }
    selected = max(bounded, key=lambda e: float(e["epoch_ms"]))
    return {
        "banner_epoch_ms": round(float(selected["epoch_ms"]), 3),
        "banner_log_line": (selected.get("text") or "")[:160],
        "banner_timestamp_ns": int(selected.get("timestamp_ns") or 0),
        "banner_source": selected.get("source", ""),
        "banner_container_id": selected.get("container_id", ""),
        "method_entry_epoch_ms": (
            round(float(entries[anchor_idx]["epoch_ms"]), 3) if anchor_found else None
        ),
        "method_entry_timestamp_ns": (
            int(entries[anchor_idx].get("timestamp_ns") or 0) if anchor_found else 0
        ),
        "pair_status": "paired_task_scoped",
        "correlation": container_task_id,
        "anchor_found": anchor_found,
        "candidate_count": candidate_count,
        "bounded_candidate_count": len(bounded),
        "distinct_timestamps": len(distinct_timestamps),
        "bounds_checked": True,
        "banner_candidates": _restore_only_banner_candidate_summary(bounded),
    }


def _restore_only_log_window(
    dispatch_unix_ms: int | None,
    remote_python_resume_wall_unix_ns: int | None,
    end_unix_ms: int | None = None,
) -> tuple[Any, Any]:
    """Tight explicit ``since``/``until`` bounds for restore-only log queries.

    ``since`` = dispatch - 120s; ``until`` = Python resume + 120s, falling
    back to the artifact end timestamp + 120s when resume is unavailable.
    Returns ``(None, None)`` when no bound can be derived.
    """
    since_dt: Any = None
    if dispatch_unix_ms is not None and dispatch_unix_ms > 0:
        since_dt = datetime.fromtimestamp(
            dispatch_unix_ms / 1000.0 - 120.0, tz=timezone.utc
        )
    until_ms: float | None = None
    if (
        remote_python_resume_wall_unix_ns is not None
        and remote_python_resume_wall_unix_ns > 0
    ):
        until_ms = remote_python_resume_wall_unix_ns / 1_000_000.0 + 120_000.0
    elif end_unix_ms is not None and end_unix_ms > 0:
        until_ms = float(end_unix_ms) + 120_000.0
    until_dt: Any = None
    if until_ms is not None:
        until_dt = datetime.fromtimestamp(until_ms / 1000.0, tz=timezone.utc)
    return since_dt, until_dt


async def _restore_only_tail_query(
    client: Any,
    app_id: str,
    *,
    since: Any,
    until: Any,
    fallback_source: str,
    filters: Any = None,
    n: int = 20000,
) -> list[dict[str, Any]]:
    """Run one bounded ``tail_logs`` query and convert items to log entries."""
    from modal._logs import tail_logs  # noqa: PLC0415

    entries: list[dict[str, Any]] = []
    async for batch in tail_logs(
        client, app_id, n, since=since, until=until, filters=filters,
    ):
        for item in batch.items:
            entry = _restore_only_tasklog_entry(item, fallback_source=fallback_source)
            if entry is not None:
                entries.append(entry)
    return entries


async def _fetch_restore_only_banner_timing(
    workspace: dict[str, Any],
    app_name: str,
    request_id: str,
    *,
    dispatch_unix_ms: int | None = None,
    remote_python_resume_wall_unix_ns: int | None = None,
    container_task_id: str | None = None,
    end_unix_ms: int | None = None,
) -> dict[str, Any]:
    """Tail Modal app logs for THIS probe's pre-Python restore banner.

    When *container_task_id* is available the queries are scoped to that task
    with ``LogsFilters``: the stdout/default anchor query uses
    ``task_id=container_task_id, search_text=<anchor>`` and the platform
    banner query uses ``source=FILE_DESCRIPTOR_INFO, task_id=container_task_id,
    search_text=<banner>``.  If the task-scoped system query returns no banner,
    a bounded fallback queries ``source=FILE_DESCRIPTOR_INFO`` with only the
    same tight time window and the banner ``search_text`` (no task filter).
    Without *container_task_id* the legacy dual-stream (default + INFO) queries
    run.  All queries use a tight explicit ``since`` = dispatch-120s and
    ``until`` = Python resume + 120s (or artifact end + 120s), and fetch up to
    20000 entries so historical lines are not displaced by newer logs.

    Merged entries are sorted ascending (``timestamp_ns`` preferred) and the
    probe's own ``request_method_entry`` stdout anchor is paired to the
    nearest strictly preceding exact system banner.  When bounds are supplied
    the banner must satisfy ``dispatch <= banner <= remote_python_resume`` —
    the pairing fails closed otherwise.  Never infers a banner;
    ``banner_epoch_ms`` is ``None`` on any failure.  The result records which
    scope matched (``banner_scope``).
    """
    try:
        import modal as _m
        from modal.cli.app import resolve_app_identifier
        from modal._logs import LogsFilters, tail_logs
        from modal.client import _Client
        from modal_proto import api_pb2  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(
            f"[v2.restore_only] banner fetch unavailable: {type(exc).__name__}",
            flush=True,
        )
        return {"banner_epoch_ms": None, "fetch_error": type(exc).__name__}
    try:
        client = await _Client.from_credentials(
            workspace["token_id"], workspace["token_secret"],
        )
        app_id, _, _ = await resolve_app_identifier(app_name, None, client)
    except Exception as exc:  # noqa: BLE001
        print(
            f"[v2.restore_only] banner fetch identity error: {type(exc).__name__}",
            flush=True,
        )
        return {"banner_epoch_ms": None, "fetch_error": type(exc).__name__}
    anchor = f"v2.restore_only_probe request_method_entry request_id={request_id}"
    since_dt, until_dt = _restore_only_log_window(
        dispatch_unix_ms, remote_python_resume_wall_unix_ns, end_unix_ms,
    )
    task_id = str(container_task_id or "").strip() or None
    _n = 20000
    last_paired: dict[str, Any] | None = None
    for _attempt in range(_RESTORE_ONLY_LOG_RETRY_COUNT):
        anchor_entries: list[dict[str, Any]] = []
        banner_entries: list[dict[str, Any]] = []
        banner_scope = "unscoped_only"
        try:
            if task_id is not None:
                # Task-scoped anchor query (default source).
                anchor_entries = await _restore_only_tail_query(
                    client, app_id, since=since_dt, until=until_dt,
                    fallback_source="stdout",
                    filters=LogsFilters(task_id=task_id, search_text=anchor),
                    n=_n,
                )
                # Task-scoped platform system banner query.
                banner_entries = await _restore_only_tail_query(
                    client, app_id, since=since_dt, until=until_dt,
                    fallback_source="system_info",
                    filters=LogsFilters(
                        source=api_pb2.FILE_DESCRIPTOR_INFO,
                        task_id=task_id,
                        search_text=RESTORE_ONLY_RESTORING_BANNER,
                    ),
                    n=_n,
                )
                banner_scope = "task_scoped"
                if not any(
                    RESTORE_ONLY_RESTORING_BANNER in (e.get("text") or "")
                    for e in banner_entries
                ):
                    # Bounded fallback: same tight window + banner search_text,
                    # no task filter.
                    banner_entries = await _restore_only_tail_query(
                        client, app_id, since=since_dt, until=until_dt,
                        fallback_source="system_info",
                        filters=LogsFilters(
                            source=api_pb2.FILE_DESCRIPTOR_INFO,
                            search_text=RESTORE_ONLY_RESTORING_BANNER,
                        ),
                        n=_n,
                    )
                    banner_scope = "fallback_unscoped"
            else:
                # Legacy dual-stream queries (no task scoping available).
                anchor_entries = await _restore_only_tail_query(
                    client, app_id, since=since_dt, until=until_dt,
                    fallback_source="stdout",
                    n=_n,
                )
                banner_entries = await _restore_only_tail_query(
                    client, app_id, since=since_dt, until=until_dt,
                    fallback_source="system_info",
                    filters=LogsFilters(source=api_pb2.FILE_DESCRIPTOR_INFO),
                    n=_n,
                )
        except Exception as exc:  # noqa: BLE001
            print(
                f"[v2.restore_only] banner fetch tail error: {type(exc).__name__}",
                flush=True,
            )
            return {"banner_epoch_ms": None, "fetch_error": type(exc).__name__}
        merged = _merge_restore_only_entries([banner_entries, anchor_entries])
        # Task-scoped pairing applies ONLY when the task-scoped INFO query
        # itself yielded exact system banner lines (banner_scope=task_scoped):
        # the banner is then direct evidence correlated by container_task_id
        # and the stdout anchor is not required.  Fallback/unscoped scopes
        # keep the anchor-requiring pairing.
        paired = _pair_restore_only_banner(
            merged,
            anchor=anchor,
            dispatch_unix_ms=dispatch_unix_ms,
            remote_python_resume_wall_unix_ns=remote_python_resume_wall_unix_ns,
            task_scoped=(task_id is not None and banner_scope == "task_scoped"),
            container_task_id=task_id,
        )
        paired["sources_fetched"] = ["system_info", "stdout"]
        paired["entry_count"] = len(merged)
        paired["banner_scope"] = banner_scope
        paired["container_task_id_scoped"] = int(task_id is not None)
        paired["container_task_id_used"] = task_id or ""
        last_paired = paired
        if paired.get("pair_status") in (
            "bounds_failed",
            "task_scoped_bounds_failed",
            "task_scoped_candidates_indistinguishable",
        ):
            print(
                f"[v2.restore_only] banner pairing failed for "
                f"request_id={request_id}: {paired.get('pair_status')} "
                f"{paired.get('bounds_failures') or paired.get('distinct_timestamps')}",
                flush=True,
            )
            return paired
        if paired.get("banner_epoch_ms") is not None:
            return paired
        # Anchor or banner not yet ingested — bounded retry (no inference).
        await asyncio.sleep(2.0)
    if last_paired is not None:
        # Preserve the real (fail-closed) pairing cause for observability.
        return last_paired
    print(
        f"[v2.restore_only] banner pairing failed for request_id={request_id}",
        flush=True,
    )
    return {
        "banner_epoch_ms": None,
        "pair_status": "unpaired_after_retries",
        "anchor_found": None,
        "sources_fetched": ["system_info", "stdout"],
        "entry_count": 0,
        "banner_scope": "none",
        "container_task_id_scoped": int(task_id is not None),
        "container_task_id_used": task_id or "",
    }


async def _run_snapshot_restore_only(
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    run_count: int,
    max_attempts: int,
    gap_seconds: float,
    app_name: str,
    class_name: str,
    gpu: str,
    conditioning_cache_nonce: str = "",
) -> dict[str, Any]:
    """UNET-absent snapshot restore-only benchmark.

    Collects EXACTLY *run_count* valid reused-snapshot restore-only probes
    against the deployed UNET-absent-snapshot app, with a hard stop the
    moment the target is reached.  Each probe is one remote call to the
    no-op ``run_snapshot_restore_only_probe`` method; every probe is a
    candidate (no beautification/throwaway probes).  Invalid/DNF probes
    never count toward the target and are preserved as artifacts.  A
    total-attempt cap (*max_attempts*) bounds the loop — if the target is
    not reached the benchmark returns non-zero (evidence insufficient).

    Per probe the harness captures the local command dispatch timestamp,
    then after the response tails the Modal app logs for the pre-Python
    ``Restoring Function from memory snapshot.`` banner anchored to this
    probe's own method-entry line.  A missing decisive timestamp/identity
    fails that probe's validity — never inferred.  Writes per-attempt JSON,
    ``summary.json`` and ``restore_only_report.json``.
    """
    os.environ["COMFYMODAL_V2_APP_NAME"] = app_name
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = class_name
    os.environ["COMFYMODAL_V2_GPU"] = gpu
    print(
        f"[v2.restore_only] mode=start target_valid={run_count} "
        f"max_attempts={max_attempts} gap={gap_seconds}s app={app_name}",
        flush=True,
    )
    handle = await asyncio.to_thread(
        transport._v2_handle, workspace=workspace, gpu=gpu,
    )
    records: list[dict[str, Any]] = []
    prev_identity: dict[str, Any] | None = None
    valid_count = 0

    for index in range(max_attempts):
        _run_id = f"restore-only-{index}-{uuid.uuid4().hex[:8]}"
        _req_id = f"v2-restore-only-{index}-{uuid.uuid4().hex[:12]}"
        _dispatch_wall_ms = int(time.time() * 1000)
        artifact: dict[str, Any] = {
            "run_index": index,
            "run_id": _run_id,
            "request_id": _req_id,
            "mode": RESTORE_ONLY_MODE,
            "dispatch_unix_ms": _dispatch_wall_ms,
            "dispatch_iso": datetime.fromtimestamp(
                _dispatch_wall_ms / 1000.0, tz=timezone.utc
            ).isoformat(),
            "start_ts": datetime.now(timezone.utc).isoformat(),
            "target": {"app_name": app_name, "class_name": class_name, "gpu": gpu},
            "config": {
                "target_valid": run_count,
                "max_attempts": max_attempts,
                "gap_seconds": gap_seconds,
                "snapshot_exclude_unet": 1,
                "evict_retain_role": "clip_vae",
                # Semantic-neutral conditioning-cache nonce (when active):
                # recorded as run evidence only — the no-op probe never
                # executes the workflow or touches the conditioning cache.
                "conditioning_cache_nonce": conditioning_cache_nonce,
            },
            "identity": {},
            "cold_check": {},
            "cold_gate_available": False,
            "banner": {},
            "banner_epoch_ms": None,
            "result": {},
            "valid": False,
            "dnf": False,
            "failures": [],
            "error": None,
        }
        identity: dict[str, Any] = {}
        try:
            fn = handle.run_snapshot_restore_only_probe
            remote = getattr(fn, "remote", None)
            if remote is not None and callable(getattr(remote, "aio", None)):
                result = remote.aio(request_id=_req_id)
                if asyncio.iscoroutine(result):
                    result = await result
            elif asyncio.iscoroutinefunction(fn):
                result = await fn(request_id=_req_id)
            else:
                result = await asyncio.to_thread(fn, request_id=_req_id)
            if asyncio.iscoroutine(result):
                result = await result
            if not isinstance(result, dict):
                raise RuntimeError(f"remote returned non-dict: {type(result).__name__}")
            artifact["result"] = result
            identity = result.get("identity") or {}
            artifact["identity"] = identity
            cold_check = _validate_cold_identity(
                identity, run_index=index, pretouch=0, prev_identity=prev_identity,
            )
            artifact["cold_check"] = cold_check
            artifact["cold_gate_available"] = bool(_cold_identity_key(identity))
            # Banner must satisfy dispatch <= banner <= Python-resume (when
            # the resume wall timestamp is directly observed by the container).
            # Task-scoped log queries are used when the container task id is
            # present in the probe identity.
            _resume_wall_ns = _num(
                ((result or {}).get("restore_timing") or {})
                .get("remote_python_resume_wall_unix_ns")
            )
            _task_id = str(identity.get("container_task_id") or "") or None
            banner = await _fetch_restore_only_banner_timing(
                workspace, app_name, _req_id,
                dispatch_unix_ms=_dispatch_wall_ms,
                remote_python_resume_wall_unix_ns=(
                    int(_resume_wall_ns) if _resume_wall_ns is not None else None
                ),
                container_task_id=_task_id,
            )
            artifact["banner"] = banner
            artifact["banner_epoch_ms"] = banner.get("banner_epoch_ms")
            valid, failures = _restore_only_validity(artifact)
            artifact["valid"] = valid
            artifact["failures"] = failures
            if valid:
                valid_count += 1
        except Exception as exc:  # noqa: BLE001
            artifact["dnf"] = True
            artifact["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            artifact["failures"] = [artifact["error"]]

        artifact["end_ts"] = datetime.now(timezone.utc).isoformat()
        (output_dir / f"run_{index}.json").write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        records.append(artifact)
        status = "DNF" if artifact["dnf"] else ("VALID" if artifact["valid"] else "INVALID")
        print(
            f"[v2.restore_only] attempt={index} status={status} "
            f"valid_total={valid_count}/{run_count} "
            f"cold={(artifact.get('cold_check') or {}).get('cold')} "
            f"banner_ms={artifact.get('banner_epoch_ms')} "
            f"instance={identity.get('restored_instance_id', '')[:12]}",
            flush=True,
        )
        if artifact["failures"]:
            print(
                f"[v2.restore_only] attempt={index} failures={artifact['failures']}",
                flush=True,
            )
        if artifact["valid"]:
            prev_identity = identity
        if valid_count >= run_count:
            print(
                f"[v2.restore_only] target reached: {valid_count} valid probes; "
                "hard stop",
                flush=True,
            )
            break
        if index + 1 < max_attempts:
            print(
                f"[v2.restore_only] phase=gap seconds={gap_seconds}",
                flush=True,
            )
            await asyncio.sleep(gap_seconds)

    valid = [r for r in records if r.get("valid")]
    summary: dict[str, Any] = {
        "mode": RESTORE_ONLY_MODE,
        "meta": {
            "app_name": app_name,
            "class_name": class_name,
            "gpu": gpu,
            "target_valid": run_count,
            "max_attempts": max_attempts,
            "gap_seconds": gap_seconds,
            "snapshot_exclude_unet": 1,
            "evict_retain_role": "clip_vae",
            "provider_region_pinned": False,
            "cold_identity": (
                "restore-only gate: restore_count==1, request_count==1, "
                "nonempty fresh restored_instance_id; invariant unet_present==0 "
                "with no retained/reconstructed UNET payload; container present "
                "and retained (container_retained==1) with clip_present==1 and "
                "vae_present==1; the Modal pre-Python 'Restoring Function from "
                "memory snapshot.' banner must be directly observed per probe; "
                "any missing decisive timestamp/identity fails validity, never "
                "inferred"
            ),
        },
        "attempt_count": len(records),
        "valid_count": len(valid),
        "dnf_count": len([r for r in records if r.get("dnf")]),
        "invalid_count": len(records) - len(valid) - len([r for r in records if r.get("dnf")]),
        "target_reached": len(valid) >= run_count,
        "runs": [{
            "run_index": r["run_index"],
            "run_id": r.get("run_id"),
            "request_id": r.get("request_id"),
            "valid": r.get("valid"),
            "dnf": r.get("dnf"),
            "cold": bool((r.get("cold_check") or {}).get("cold")),
            "failures": r.get("failures"),
            "dispatch_unix_ms": r.get("dispatch_unix_ms"),
            "banner_epoch_ms": r.get("banner_epoch_ms"),
            "intervals": _restore_only_intervals(r),
            "identity": r.get("identity"),
            "result": r.get("result"),
        } for r in records],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    (output_dir / "restore_only_report.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    print(_render_restore_only_table(summary), flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "attempt_count": summary["attempt_count"],
        "valid_count": summary["valid_count"],
        "invalid_count": summary["invalid_count"],
        "dnf_count": summary["dnf_count"],
        "target_reached": summary["target_reached"],
    }, default=str), flush=True)
    return summary


def _restore_only_load_attempts(output_dir: Path) -> list[tuple[int, dict[str, Any]]]:
    """Load ``run_<n>.json`` restore-only artifacts in strict numeric order.

    Only bare ``run_<digits>.json`` files are considered (backfilled copies
    named ``backfilled_run_<n>.json`` never match).  Returns ``(index, artifact)``
    pairs sorted by the numeric file index; a gap in the numeric sequence is
    preserved so the caller can fail closed on an incomplete prefix.
    """
    indexed: list[tuple[int, dict[str, Any]]] = []
    for f in output_dir.glob("run_*.json"):
        match = _RESTORE_ONLY_RUN_FILE_RE.match(f.name)
        if match is None:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, dict):
            continue
        indexed.append((int(match.group(1)), data))
    indexed.sort(key=lambda pair: pair[0])
    return indexed


def _restore_only_end_unix_ms(artifact: dict[str, Any]) -> int | None:
    """Best-effort artifact end epoch-ms for the tight ``until`` log bound.

    Parses the artifact's ``end_ts`` (ISO UTC), falling back to ``start_ts``.
    Returns ``None`` when neither is parseable.
    """
    for key in ("end_ts", "start_ts"):
        raw = artifact.get(key)
        if isinstance(raw, str) and raw.strip():
            try:
                return int(datetime.fromisoformat(raw).timestamp() * 1000.0)
            except ValueError:
                continue
    return None


async def _backfill_snapshot_restore_only(
    workspace: dict[str, Any],
    source_dir: Path,
    limit: int = _RESTORE_ONLY_BACKFILL_LIMIT,
) -> dict[str, Any]:
    """REPORT-ONLY backfill of an existing restore-only run directory.

    Re-fetches banner evidence for the FIRST *limit* attempts (exactly indices
    ``0..limit-1``) and re-runs ``_restore_only_validity``.  This is log
    retrieval ONLY: it never creates a ``ModalTransport`` and never touches
    remote function handles (no ``run_snapshot_restore_only_probe``, no
    Function.remote/spawn).  The raw ``run_<n>.json`` artifacts are preserved
    untouched; backfilled copies are written as ``backfilled_run_<n>.json``
    plus a new ``backfilled_summary.json`` / ``backfilled_restore_only_report.json``
    containing exactly *limit* selected records.

    Raises ``RuntimeError`` when any of the first *limit* attempts cannot be
    validated after backfill — later attempts are never substituted.
    """
    if limit < 1:
        raise RuntimeError(f"restore-only backfill limit must be >= 1, got {limit}")
    indexed = _restore_only_load_attempts(source_dir)
    if len(indexed) < limit:
        raise RuntimeError(
            f"restore-only backfill requires at least {limit} source attempts, "
            f"found {len(indexed)}"
        )
    selected = indexed[:limit]
    selected_indices = [idx for idx, _ in selected]
    if selected_indices != list(range(limit)):
        raise RuntimeError(
            "restore-only backfill requires the first source attempts to be "
            f"exactly [0..{limit - 1}], got {selected_indices}"
        )
    excluded_indices = [idx for idx, _ in indexed[limit:]]
    source_attempt_count = len(indexed)

    app_name = ""
    class_name = ""
    gpu = ""
    backfilled: list[dict[str, Any]] = []
    for i, (run_index, artifact) in enumerate(selected):
        target = artifact.get("target") or {}
        if i == 0:
            app_name = str(
                target.get("app_name")
                or os.environ.get("COMFYMODAL_V2_APP_NAME", RESTORE_ONLY_APP_NAME)
            )
            class_name = str(target.get("class_name") or CLASS_NAME)
            gpu = str(target.get("gpu") or GPU)
        request_id = str(artifact.get("request_id") or "")
        dispatch_ms = _num(artifact.get("dispatch_unix_ms"))
        resume_ns = _num(
            ((artifact.get("result") or {}).get("restore_timing") or {})
            .get("remote_python_resume_wall_unix_ns")
        )
        # Task-scoped log queries via the stored probe identity + a tight
        # ``until`` bound derived from the artifact's own end timestamp.
        _task_id = str((artifact.get("identity") or {}).get("container_task_id") or "") or None
        _end_ms = _restore_only_end_unix_ms(artifact)
        banner = await _fetch_restore_only_banner_timing(
            workspace,
            app_name,
            request_id,
            dispatch_unix_ms=int(dispatch_ms) if dispatch_ms is not None else None,
            remote_python_resume_wall_unix_ns=(
                int(resume_ns) if resume_ns is not None else None
            ),
            container_task_id=_task_id,
            end_unix_ms=_end_ms,
        )
        copy_artifact = copy.deepcopy(artifact)
        copy_artifact["banner"] = banner
        copy_artifact["banner_epoch_ms"] = banner.get("banner_epoch_ms")
        copy_artifact["backfilled"] = True
        copy_artifact["backfill_source_file"] = f"run_{run_index}.json"
        valid, failures = _restore_only_validity(copy_artifact)
        copy_artifact["valid"] = valid
        copy_artifact["failures"] = failures
        if not valid:
            # Persist full failure diagnostics BEFORE raising so the parent can
            # inspect exactly why the attempt stayed invalid (banner fetch
            # result, filters used, failures, bounds).
            _diag: dict[str, Any] = {
                "run_index": run_index,
                "request_id": request_id,
                "failures": failures,
                "dispatch_unix_ms": dispatch_ms,
                "remote_python_resume_wall_unix_ns": resume_ns,
                "container_task_id": _task_id,
                "end_unix_ms": _end_ms,
                "banner": banner,
                "backfilled_artifact": copy_artifact,
            }
            (source_dir / f"backfill_failure_attempt_{run_index}.json").write_text(
                json.dumps(_diag, default=str, indent=2), encoding="utf-8"
            )
            raise RuntimeError(
                f"restore-only backfill FAILED for attempt {run_index}: "
                + "; ".join(failures)
            )
        (source_dir / f"backfilled_run_{run_index}.json").write_text(
            json.dumps(copy_artifact, default=str, indent=2), encoding="utf-8"
        )
        backfilled.append(copy_artifact)

    runs = [{
        "run_index": r.get("run_index"),
        "run_id": r.get("run_id"),
        "request_id": r.get("request_id"),
        "valid": r.get("valid"),
        "dnf": r.get("dnf"),
        "cold": bool((r.get("cold_check") or {}).get("cold")),
        "failures": r.get("failures"),
        "dispatch_unix_ms": r.get("dispatch_unix_ms"),
        "banner_epoch_ms": r.get("banner_epoch_ms"),
        "intervals": _restore_only_intervals(r),
        "identity": r.get("identity"),
        "result": r.get("result"),
        "banner": r.get("banner"),
    } for r in backfilled]

    # Machine-readable distribution / cohort data over the six selected probes.
    _interval_keys = (
        "dispatch_to_banner_ms", "pre_python_restore_ms", "python_restore_total_ms",
        "python_resume_to_method_entry_ms", "banner_to_method_entry_ms",
        "dispatch_to_method_entry_ms",
    )
    distribution: dict[str, Any] = {}
    for key in _interval_keys:
        distribution[key] = compute_stats(
            v for v in (_num(r["intervals"].get(key)) for r in runs) if v is not None
        )
    cohort: dict[str, Any] = {
        "selected_count": len(runs),
        "source_attempt_count": source_attempt_count,
        "excluded_overrun_count": len(excluded_indices),
        "banner_epoch_ms": compute_stats(
            v for v in (_num(r.get("banner_epoch_ms")) for r in runs) if v is not None
        ),
        "dispatch_unix_ms": compute_stats(
            v for v in (_num(r.get("dispatch_unix_ms")) for r in runs) if v is not None
        ),
    }

    summary: dict[str, Any] = {
        "mode": "snapshot_restore_only_backfill",
        "meta": {
            "app_name": app_name,
            "class_name": class_name,
            "gpu": gpu,
            "target_valid": limit,
            "limit": limit,
            "source_attempt_count": source_attempt_count,
            "selected_attempts": selected_indices,
            "excluded_instrumentation_overrun_attempts": excluded_indices,
            "protocol_note": (
                f"Original run issued {source_attempt_count} probes because the "
                "pre-fix banner fetcher used the default log source only and "
                "never saw the Modal system/INFO 'Restoring Function from "
                "memory snapshot.' lines, so every candidate was marked "
                "invalid.  This backfill re-fetches system/INFO + stdout logs "
                "(bounded; log retrieval only, no probe invocation) for the "
                f"FIRST {limit} attempts "
                f"[{selected_indices[0]}..{selected_indices[-1]}] and "
                "re-validates them.  Attempts "
                f"{excluded_indices} are excluded as instrumentation overrun "
                "and are never substituted for the first six."
            ),
            "backfill": True,
            "no_remote_invocation": True,
            "source_dir": str(source_dir),
            "raw_evidence_preserved": True,
            "snapshot_exclude_unet": 1,
            "evict_retain_role": "clip_vae",
            "provider_region_pinned": False,
            "cold_identity": (
                "restore-only gate: restore_count==1, request_count==1, "
                "nonempty fresh restored_instance_id; invariant unet_present==0 "
                "with no retained/reconstructed UNET payload; container present "
                "and retained (container_retained==1) with clip_present==1 and "
                "vae_present==1; the Modal pre-Python 'Restoring Function from "
                "memory snapshot.' system banner must be directly observed per "
                "probe within dispatch <= banner <= python-resume; any missing "
                "decisive timestamp/identity fails validity, never inferred"
            ),
        },
        "attempt_count": len(backfilled),
        "valid_count": len([r for r in backfilled if r.get("valid")]),
        "dnf_count": 0,
        "invalid_count": 0,
        "target_reached": len(backfilled) == limit,
        "source_attempt_count": source_attempt_count,
        "selected_attempts": selected_indices,
        "excluded_instrumentation_overrun_attempts": excluded_indices,
        "distribution": distribution,
        "cohort": cohort,
        "runs": runs,
    }
    (source_dir / "backfilled_summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    (source_dir / "backfilled_restore_only_report.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    print(_render_restore_only_table(summary), flush=True)
    print(json.dumps({
        "output_dir": str(source_dir),
        "mode": "snapshot_restore_only_backfill",
        "source_attempt_count": source_attempt_count,
        "selected_attempts": selected_indices,
        "excluded_instrumentation_overrun_attempts": excluded_indices,
        "valid_count": summary["valid_count"],
        "target_reached": summary["target_reached"],
    }, default=str), flush=True)
    return summary


async def _run_variance_cold(
    workflow: dict[str, Any],
    modal_options: dict[str, Any],
    workspace: dict[str, Any],
    transport: ModalTransport,
    output_dir: Path,
    *,
    run_count: int,
    gap_seconds: float,
    pretouch: int,
    app_name: str,
    class_name: str,
    gpu: str,
    teardown: str = "full",
    pin_transfer: int = 0,
    quiesced_transfer: int = 0,
    _runner: Any = None,
) -> dict[str, Any]:
    """Run the variance-cold sequence: one request at a time with a gap.

    Every run artifact (including slow/invalid runs) is preserved with run ID,
    mode, identity, provider/region/image/task/container IDs, runtime
    fingerprint/thread counts, exact timestamps, and the full result trace.
    Produces ``summary.json`` and ``variance_cold_report.md``.
    """
    print(
        f"[v2.variance_cold] mode=start runs={run_count} gap={gap_seconds}s "
        f"pretouch={pretouch} teardown={teardown} pin_transfer={pin_transfer} app={app_name}",
        flush=True,
    )
    records: list[dict[str, Any]] = []
    prev_identity: dict[str, Any] | None = None

    for index in range(run_count):
        _run_id = f"variance-cold-p{pretouch}-{index}-{uuid.uuid4().hex[:8]}"
        _start_ts = datetime.now(timezone.utc).isoformat()
        origin = _variance_origin(index, pretouch, app_name, teardown=teardown, pin_transfer=pin_transfer, quiesced_transfer=quiesced_transfer)

        artifact: dict[str, Any] = {}
        try:
            if _runner is not None:
                artifact = await _runner(
                    index=index,
                    workflow=workflow,
                    modal_options=modal_options,
                    workspace=workspace,
                    transport=transport,
                    output_dir=output_dir,
                    _extra_origin=origin,
                    _defer_waterfall=True,
                )
            else:
                artifact = await _run_one(
                    index=index,
                    workflow=workflow,
                    modal_options=modal_options,
                    workspace=workspace,
                    transport=transport,
                    output_dir=output_dir,
                    _extra_origin=origin,
                    _defer_waterfall=True,
                )
        except Exception as exc:  # noqa: BLE001
            artifact = {
                "run_index": index,
                "run_id": _run_id,
                "request_id": "",
                "identity": {},
                "result": {},
                "timing": {},
                "variance": {
                    "pretouch": pretouch,
                    "pin_transfer": pin_transfer,
                    "teardown_mode": teardown,
                    "cold_valid": False,
                    "cold": False,
                    "failures": [f"run raised: {str(exc)[:300]}"],
                },
                "start_ts": _start_ts,
                "end_ts": datetime.now(timezone.utc).isoformat(),
                "remote_entry_ts": "unavailable",
                "mode": "variance_cold",
                "error": str(exc)[:300],
            }
            # Preserve failed/invalid runs in artifacts.
            (output_dir / f"run_{index}.json").write_text(
                json.dumps(artifact, default=str, indent=2), encoding="utf-8"
            )
            records.append(extract_run_metrics(artifact))
            print(f"[v2.variance_cold] run={index} ERROR {str(exc)[:200]}", flush=True)
            prev_identity = None
            if index + 1 < run_count:
                await asyncio.sleep(gap_seconds)
            continue

        identity = artifact.get("identity", {}) or {}
        cold_check = _validate_cold_identity(
            identity, run_index=index, pretouch=pretouch, prev_identity=prev_identity,
        )
        result = artifact.get("result", {}) if isinstance(artifact.get("result"), dict) else {}
        artifact["run_id"] = _run_id
        artifact["mode"] = "variance_cold"
        artifact["start_ts"] = _start_ts
        artifact["end_ts"] = datetime.now(timezone.utc).isoformat()
        artifact["remote_entry_ts"] = _remote_entry_wall_iso(result)
        artifact["variance"] = {
            "pretouch": pretouch,
            "pin_transfer": pin_transfer,
            "teardown_mode": teardown,
            "cold_valid": cold_check["cold_valid"],
            "cold": cold_check["cold"],
            "failures": cold_check["failures"],
            "freshness_checked": cold_check["freshness_checked"],
        }
        # Re-write the augmented artifact (run_<index>.json was written by _run_one).
        (output_dir / f"run_{index}.json").write_text(
            json.dumps(artifact, default=str, indent=2), encoding="utf-8"
        )
        records.append(extract_run_metrics(artifact))

        status = "COLD" if cold_check["cold"] else "NOT-COLD"
        print(
            f"[v2.variance_cold] run={index} id={_run_id} status={status} "
            f"instance={identity.get('restored_instance_id', '')[:12]} "
            f"task={identity.get('container_task_id', '')[:16]}",
            flush=True,
        )
        if cold_check["failures"]:
            print(f"[v2.variance_cold] run={index} failures={cold_check['failures']}", flush=True)

        # Freshness baseline for the next run: only advance when this run was
        # cold so a warm run never becomes the "previous" baseline.
        if cold_check["cold"]:
            prev_identity = identity

        if index + 1 < run_count:
            print(f"[v2.variance_cold] phase=gap seconds={gap_seconds}", flush=True)
            await _intentional_cold_wait(gap_seconds)

    meta = {
        "mode": "variance_cold",
        "app_name": app_name,
        "class_name": class_name,
        "gpu": gpu,
        "run_count": run_count,
        "gap_seconds": gap_seconds,
        "pretouch": pretouch,
        "teardown_mode": teardown,
        "slow_threshold_ms": float(os.environ.get("V2_VARIANCE_SLOW_THRESHOLD_MS", "0") or 0),
    }
    summary = build_summary(records, meta=meta)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    report_md = render_variance_report(summary)
    (output_dir / "variance_cold_report.md").write_text(report_md, encoding="utf-8")
    print(f"[v2.variance_cold] report={output_dir / 'variance_cold_report.md'}", flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "run_count": summary["run_count"],
        "cold_count": summary["cold_count"],
        "warm_or_invalid_count": summary["warm_or_invalid_count"],
        "pretouch": pretouch,
        "root_cause": summary["root_cause"].get("dominant"),
    }, default=str), flush=True)
    print(report_md, flush=True)

    if summary["cold_count"] < run_count:
        raise RuntimeError(
            f"variance_cold: only {summary['cold_count']}/{run_count} runs were "
            "confirmed cold; warm/reused runs are not valid cold evidence"
        )
    return summary


def _report_only_from_dir(output_dir: Path) -> dict[str, Any]:
    """Render a report from an existing artifacts directory without Modal.

    Used when Modal/network is unavailable so the harness/report generator
    remains testable locally.  Also the entry point for offline report
    regeneration from a prior run.

    Detects a variance-cold MATRIX directory (one containing ``attempt_*.json``
    plus a ``summary.json``) and renders the consolidated matrix handoff.  A
    plain variance-cold directory (``run_*.json``) keeps the existing
    ``variance_cold_report.md`` behavior.
    """
    attempt_files = sorted(output_dir.glob("attempt_*.json"))
    if attempt_files and (output_dir / "summary.json").is_file():
        return _report_only_matrix_from_dir(output_dir, attempt_files)

    # ── Variance-cold (run_*.json) path ──
    records = load_runs_from_dir(output_dir)
    meta = {
        "mode": "variance_cold",
        "app_name": os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME),
        "class_name": CLASS_NAME,
        "gpu": GPU,
        "run_count": len(records),
        "gap_seconds": VARIANCE_COLD_GAP_SECONDS,
        "pretouch": int(os.environ.get("V2_VARIANCE_PRETOUCH", "0") or 0),
        "slow_threshold_ms": float(os.environ.get("V2_VARIANCE_SLOW_THRESHOLD_MS", "0") or 0),
        "limitation": "Report generated offline from existing artifacts; no new Modal "
                      "runs were performed (Modal/network may be unavailable).",
    }
    summary = build_summary(records, meta=meta)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    report_md = render_variance_report(summary)
    (output_dir / "variance_cold_report.md").write_text(report_md, encoding="utf-8")
    print(f"[v2.variance_cold] offline_report={output_dir / 'variance_cold_report.md'}", flush=True)
    print(report_md, flush=True)
    return summary


def _report_only_matrix_from_dir(output_dir: Path, attempt_files: list[Path]) -> dict[str, Any]:
    """Render the consolidated variance-matrix handoff from existing attempt files.

    Loads every ``attempt_*.json``, extracts metrics, builds the matrix summary
    (condition labels taken from the artifacts; fixed slow threshold taken from
    the existing ``summary.json`` or the 60000 ms default), and overwrites
    ``summary.json`` + ``variance_matrix_handoff.md``.
    """
    records: list[dict[str, Any]] = []
    conditions_set: set[tuple[int, int]] = set()
    for f in attempt_files:
        try:
            artifact = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(artifact, dict):
            continue
        rec = extract_run_metrics(artifact)
        rec["classification"] = artifact.get("classification")
        rec["attempt_id"] = artifact.get("attempt_id")
        rec["attempt_file"] = artifact.get("attempt_file") or f.name
        rec["condition_label"] = artifact.get("condition_label")
        diag = artifact.get("diag")
        pretouch = 0
        _var = artifact.get("variance")
        if isinstance(_var, dict):
            try:
                pretouch = int(_var.get("pretouch", 0))
            except (TypeError, ValueError):
                pretouch = 0
        if diag is not None:
            conditions_set.add((int(diag), pretouch))
        records.append(rec)

    conditions = sorted(conditions_set) if conditions_set else list(MATRIX_CONDITIONS)

    # Fixed slow threshold: reuse the existing summary value, else 60000 default.
    slow_threshold_ms = MATRIX_SLOW_THRESHOLD_MS
    try:
        _existing = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
        if isinstance(_existing, dict):
            _t = _existing.get("slow_threshold_ms")
            if _t and float(_t) > 0:
                slow_threshold_ms = float(_t)
    except Exception:  # noqa: BLE001
        pass

    meta = {
        "mode": "variance_matrix",
        "app_name": os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME),
        "class_name": CLASS_NAME,
        "gpu": GPU,
        "gap_seconds": VARIANCE_COLD_GAP_SECONDS,
        "target_per_condition": MATRIX_TARGET_COLD_PER_CONDITION,
        "slow_threshold_ms": slow_threshold_ms,
        "limitation": "Matrix report generated offline from existing artifacts; "
                      "no new Modal runs were performed.",
    }
    summary = build_matrix_summary(
        records, conditions, meta=meta, slow_threshold_ms=slow_threshold_ms,
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, default=str, indent=2), encoding="utf-8"
    )
    handoff = render_matrix_report(summary, output_dir)
    (output_dir / "variance_matrix_handoff.md").write_text(handoff, encoding="utf-8")
    print(f"[v2.variance_matrix] offline_report={output_dir / 'variance_matrix_handoff.md'}", flush=True)
    print(json.dumps({
        "output_dir": str(output_dir),
        "mode": "variance_matrix",
        "total_attempts": summary["total_attempts"],
        "total_cold": summary["total_cold"],
        "per_condition_cold": {k: p["cold_count"] for k, p in summary["per_condition"].items()},
    }, default=str), flush=True)
    return summary


def _batch_a_raise_authorized(batch_b_acceptance: bool,
                              batch_c_acceptance: bool) -> bool:
    """Batch-A is the authoritative raise layer only when NO stricter batch
    layer is enabled.

    Batch-B preserves every Batch-A gate and Batch-C wraps Batch-B, so when
    either is enabled a Batch-A failure must be reported (the block is still
    rendered) but deferred to the stricter layer instead of aborting the run.
    """
    return not (batch_b_acceptance or batch_c_acceptance)


def _batch_b_raise_authorized(batch_c_acceptance: bool) -> bool:
    """Batch-B is the authoritative raise layer only when Batch-C is disabled.

    Batch-C wraps Batch-B (never duplicates it) and fails unconditionally when
    Batch-B fails, so a Batch-B failure must be deferred to Batch-C when it is
    enabled.  The Batch-B block is still rendered in that case.
    """
    return not batch_c_acceptance


async def _prime_registry_proof() -> None:
    """Load the full node registry once and persist the store entry for the
    canonical benchmark workflow (no Modal transport, no remote calls).

    Registry work happens HERE — at deploy time, before any user benchmark
    trigger — so externally-invoked benchmark commands reach Modal without
    paying the 17-90 s import (D1 zero-gap)."""
    _load_t0 = time.perf_counter()
    if not await _ensure_full_node_registry():
        raise RuntimeError(
            "[v2.harness] node registry initialization failed; cannot prime "
            "the registry-proof store"
        )
    _load_ms = round((time.perf_counter() - _load_t0) * 1000.0, 3)
    workflow, modal_options = _load_workflow()
    _opts = normalize_production_options(modal_options)
    _plan = build_execution_plan(
        workflow,
        prompt_id=f"v2-prime-{uuid.uuid4().hex[:8]}",
        client_id="v2-prime-registry-proof",
        modal_options=modal_options,
        production_options=_opts if _opts.get("enabled") else None,
        gpu=GPU,
        workspace=None,
        request_metadata={"benchmark_app": APP_NAME, "prime_registry_proof": True},
        trace=None,
        validate=False,
        collect_validation_proof=_PLAN_VALIDATION_PROOF,
        comfyui_root=_COMFYUI_ROOT_DIR,
    )
    _covered = _registry_proof_store_covers(
        workflow,
        modal_options=modal_options,
        production_options=_opts if _opts.get("enabled") else None,
    )
    _store_path = ""
    try:
        from comfymodal_runtime.registry_proof_store import store_path as _sp
        _store_path = str(_sp())
    except Exception:
        pass
    print(json.dumps({
        "prime_registry_proof": True,
        "registry_load_ms": round(_load_ms, 1),
        "workflow_hash": str(_plan.workflow_hash)[:16],
        "store_entry_persisted": bool(_covered),
        "store_path": _store_path,
        "prime_ok": bool(_covered),
    }, default=str), flush=True)
    if not _covered:
        raise RuntimeError(
            "registry-proof priming failed: no store entry persisted "
            "(deploy-frozen .deployed_state.json identity required)"
        )


async def main(bypass_cpu_snapshot_unet: bool = False, cpu_snapshot_unet_ab: bool = False,
               acceptance: bool = False, variance_cold: bool = False,
               variance_matrix: bool = False, transfer_ab: bool = False,
               region_ab: str | None = None, host_ab: bool = False,
               backing_ab: bool = False, provider_ab: bool = False,
               volume_read: bool = False,
               snapshot_restore_only: bool = False,
               snapshot_restore_only_backfill: str | None = None,
               variance_pretouch: int = 0, report_only: str | None = None,
               gap_seconds: float | None = None, run_count: int | None = None,
               teardown: str = "full", pin_transfer: int = 0,
               quiesced_transfer: int = 0,
               batch_a_acceptance: bool = False,
               batch_b_acceptance: bool = False,
               batch_c_acceptance: bool = False,
               prime_registry_proof: bool = False,
               unique_prompt_suffix: str = "",
               conditioning_cache_nonce: str = "") -> None:
    os.environ.setdefault("COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE", "1")
    os.environ["COMFYMODAL_V2_APP_NAME"] = APP_NAME
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = CLASS_NAME
    os.environ["COMFYMODAL_V2_GPU"] = GPU

    # Host boot origin: module-global stamp captured on the FIRST line of the
    # benchmark process (before the heavy import block).  Emitted once per
    # process so the command→python-first-line boot interval is measurable.
    print(
        f"[v2.host] python_first_line_wall_unix_ns={_PYTHON_FIRST_LINE_NS}",
        flush=True,
    )

    # --conditioning-cache-nonce: semantic-neutral exact-conditioning cache
    # nonce.  Forces a cache MISS under a fresh value WITHOUT changing the
    # workflow/prompt/seed/sampler sent to ComfyUI.  Carried ONLY in the
    # request origin (never in the workflow), so the workflow stays
    # byte-identical.  Zero behavior change when unused.
    if conditioning_cache_nonce:
        print(
            f"[v2.conditioning_cache_nonce] nonce={conditioning_cache_nonce}",
            flush=True,
        )

    # ── Offline report regeneration (no Modal / network needed) ──────────
    if report_only:
        _report_dir = Path(report_only)
        if not _report_dir.is_absolute():
            _candidate = ROOT.parent.parent / "comfymodal-data" / "benchmarks" / "runs" / report_only
            if _candidate.is_dir():
                _report_dir = _candidate
        if not _report_dir.is_dir():
            raise RuntimeError(f"report-only directory not found: {report_only}")
        _report_only_from_dir(_report_dir)
        return

    # ── Restore-only BACKFILL (report-only; log retrieval, no probes) ─────
    # Re-fetches system/INFO + stdout banner evidence for the FIRST six
    # attempts of a prior restore-only run directory and re-validates them.
    # Never creates ModalTransport / never invokes remote function handles.
    # Exits nonzero unless exactly *limit* valid probes are recovered.
    if snapshot_restore_only_backfill:
        _bf_dir = Path(snapshot_restore_only_backfill)
        if not _bf_dir.is_absolute():
            _candidate = (
                ROOT.parent.parent / "comfymodal-data" / "benchmarks" / "runs"
                / snapshot_restore_only_backfill
            )
            if _candidate.is_dir():
                _bf_dir = _candidate
        if not _bf_dir.is_dir():
            raise RuntimeError(
                "restore-only backfill directory not found: "
                f"{snapshot_restore_only_backfill}"
            )
        _bf_workspace = _load_workspace()
        _bf_limit = RESTORE_ONLY_RUN_COUNT if run_count is None else int(run_count)
        _bf_summary = await _backfill_snapshot_restore_only(
            _bf_workspace, _bf_dir, limit=_bf_limit,
        )
        if _bf_summary.get("valid_count") != _bf_limit:
            raise RuntimeError(
                "restore-only backfill incomplete: "
                f"{_bf_summary.get('valid_count')}/{_bf_limit} valid"
            )
        return

    if prime_registry_proof:
        await _prime_registry_proof()
        return

    # ── One-time full node-registry preload (D1 local-dispatch fix) ───────
    # Previously the full registry load (~17-21s; 87.9s measured on this host)
    # ran inside _run_one between the local_receive stamp and the worker_start
    # stamp on run 1, inflating local_receive_to_worker_start_ms by the entire
    # preload duration.  Preload once here, before the first benchmark
    # iteration, so every per-run local_receive→worker_start window reflects
    # production (a long-lived server with the registry already loaded);
    # _run_one's await then short-circuits via the ready fast path.  The
    # preload is harness setup, reported as node_registry_preload_ms — never
    # scheduling (C3 semantics preserved).
    #
    # D1 zero-gap: when a store entry for the current deploy-frozen generation
    # already exists (primed at deploy time via --prime-registry-proof), the
    # registry import is skipped entirely.
    _store_primed = False
    try:
        from comfymodal_runtime.registry_proof_store import has_generation_entry as _has_gen
        _store_primed = bool(_has_gen())
    except Exception:
        _store_primed = False
    if not _store_primed:
        _nri_preload_start_ns = time.perf_counter_ns()
        if not await _ensure_full_node_registry():
            raise RuntimeError(
                "[v2.harness] node registry initialization failed; "
                "cannot build an authoritative plan validation proof"
            )
        _nri_preload_ms = round((time.perf_counter_ns() - _nri_preload_start_ns) / 1_000_000, 3)
        print(
            f"[v2.harness] node_registry_preload_ms={_fmt_v2_metric(_nri_preload_ms)}",
            flush=True,
        )
    else:
        _nri_preload_ms = 0.0
        print("[v2.harness] node_registry_preload_skipped store_generation_entry=yes", flush=True)

    requested_shape = runtime_shape_config().identity_payload()
    shape_guard = _runtime_shape_guard(requested_shape)
    print(json.dumps({"runtime_shape": requested_shape, "guard": shape_guard}, sort_keys=True), flush=True)
    workspace = _load_workspace()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

    # ── Mounted-Volume raw sequential-read mode (explicit opt-in) ──────────
    if volume_read:
        _vr_app = os.environ.get("COMFYMODAL_V2_APP_NAME", APP_NAME) or APP_NAME
        os.environ["COMFYMODAL_V2_APP_NAME"] = _vr_app
        _vr_gap = VOLUME_READ_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _vr_runs = VOLUME_READ_RUN_COUNT if run_count is None else int(run_count)
        _vr_dir = ROOT.parent.parent / "comfymodal-data" / "benchmarks" / "runs" / f"volume_read_{timestamp}"
        _vr_dir.mkdir(parents=True, exist_ok=True)
        await _run_volume_read(
            workspace=workspace,
            transport=ModalTransport(),
            output_dir=_vr_dir,
            run_count=_vr_runs,
            gap_seconds=_vr_gap,
            filename=VOLUME_READ_FILENAME,
            chunk_bytes=VOLUME_READ_CHUNK_BYTES,
            app_name=_vr_app,
            class_name=CLASS_NAME,
            gpu=GPU,
        )
        return

    # ── UNET-absent snapshot restore-only mode (explicit opt-in) ───────────
    # Exactly RESTORE_ONLY_RUN_COUNT (default 6) valid reused-snapshot probes
    # against the deployment built with COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1,
    # hard-stopped once reached; invalid probes never count; no
    # beautification probes.  Provider/region unpinned by design.
    if snapshot_restore_only:
        _ro_app = (
            os.environ.get("COMFYMODAL_V2_APP_NAME", RESTORE_ONLY_APP_NAME)
            or RESTORE_ONLY_APP_NAME
        )
        os.environ["COMFYMODAL_V2_APP_NAME"] = _ro_app
        _ro_target = RESTORE_ONLY_RUN_COUNT if run_count is None else int(run_count)
        _ro_max = RESTORE_ONLY_MAX_ATTEMPTS
        if os.environ.get("V2_RESTORE_ONLY_MAX_ATTEMPTS"):
            _ro_max = int(os.environ["V2_RESTORE_ONLY_MAX_ATTEMPTS"])
        _ro_gap = RESTORE_ONLY_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _ro_dir = ROOT.parent.parent / "comfymodal-data" / "benchmarks" / "runs" / f"restore_only_{timestamp}"
        _ro_dir.mkdir(parents=True, exist_ok=True)
        await _run_snapshot_restore_only(
            workspace=workspace,
            transport=ModalTransport(),
            output_dir=_ro_dir,
            run_count=_ro_target,
            max_attempts=_ro_max,
            gap_seconds=_ro_gap,
            app_name=_ro_app,
            class_name=CLASS_NAME,
            gpu=GPU,
            conditioning_cache_nonce=conditioning_cache_nonce,
        )
        return

    workflow, modal_options = _load_workflow()
    # --unique-prompt-suffix: append a fresh token to every literal prompt
    # text source so the exact-conditioning cache key (entry text + canonical
    # workflow hash) is unique per run — a deterministic MISS vehicle with
    # no manual cache-state deletion.  Zero behavior change when unused.
    if unique_prompt_suffix:
        _ups_n = _apply_unique_prompt_suffix(workflow, unique_prompt_suffix)
        print(
            f"[v2.unique_prompt_suffix] suffix={unique_prompt_suffix} "
            f"applied to {_ups_n} text sources",
            flush=True,
        )
    output_dir = ROOT.parent.parent / "comfymodal-data" / "benchmarks" / "runs" / f"v2_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    transport = ModalTransport()

    # ── Variance-cold mode (explicit opt-in; unique shadow app name) ──────
    if variance_cold:
        _vc_app = os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME) or VARIANCE_APP_NAME
        os.environ["COMFYMODAL_V2_APP_NAME"] = _vc_app
        _vc_gap = VARIANCE_COLD_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _vc_runs = VARIANCE_RUN_COUNT if run_count is None else int(run_count)
        await _run_variance_cold(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
            run_count=_vc_runs, gap_seconds=_vc_gap, pretouch=int(variance_pretouch),
            app_name=_vc_app, class_name=CLASS_NAME, gpu=GPU, teardown=teardown,
            pin_transfer=int(pin_transfer), quiesced_transfer=int(quiesced_transfer),
        )
        return

    # ── Variance-cold MATRIX (four-condition round-robin) ───────────────
    if variance_matrix:
        _vm_app = os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME) or VARIANCE_APP_NAME
        os.environ["COMFYMODAL_V2_APP_NAME"] = _vm_app
        _vm_gap = VARIANCE_COLD_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _target = MATRIX_TARGET_COLD_PER_CONDITION
        _max_attempts = MATRIX_MAX_TOTAL_ATTEMPTS
        if os.environ.get("V2_MATRIX_TARGET_PER_CONDITION"):
            _target = int(os.environ["V2_MATRIX_TARGET_PER_CONDITION"])
        if os.environ.get("V2_MATRIX_MAX_TOTAL_ATTEMPTS"):
            _max_attempts = int(os.environ["V2_MATRIX_MAX_TOTAL_ATTEMPTS"])
        # Fixed slow threshold: nonzero default, or fail fast — never derived.
        _slow = _resolve_slow_threshold()
        await _run_variance_matrix(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
            gap_seconds=_vm_gap, app_name=_vm_app, class_name=CLASS_NAME, gpu=GPU,
            target_per_condition=_target, max_total_attempts=_max_attempts,
            slow_threshold_ms=_slow, teardown=teardown, pin_transfer=int(pin_transfer),
        )
        return

    # ── UNET-transfer contention A/B (interleaved overlap vs quiesced) ──
    if transfer_ab:
        _ta_app = os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME) or VARIANCE_APP_NAME
        os.environ["COMFYMODAL_V2_APP_NAME"] = _ta_app
        _ta_gap = VARIANCE_COLD_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _ta_target = int(os.environ.get("V2_TRANSFER_AB_TARGET_COLD", "10"))
        _ta_max = int(os.environ.get("V2_TRANSFER_AB_MAX_ATTEMPTS_PER_CONDITION", "15"))
        await _run_transfer_ab(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
            gap_seconds=_ta_gap, app_name=_ta_app, class_name=CLASS_NAME, gpu=GPU,
            target_per_condition=_ta_target, max_attempts_per_condition=_ta_max,
            teardown=teardown,
        )
        return

    # ── Provider AWS-vs-GCP + page-path isolation study ─────────────────
    if provider_ab:
        _pa_gap = VARIANCE_COLD_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _pa_target = int(os.environ.get("V2_PROVIDER_AB_TARGET_COLD", "7"))
        _pa_max = int(os.environ.get("V2_PROVIDER_AB_MAX_ATTEMPTS_PER_ARM", "12"))
        _pa_skip = int(os.environ.get("V2_PROVIDER_AB_SKIP_FIRST", "2"))
        await _run_provider_ab(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
            gap_seconds=_pa_gap, app_aws=PROVIDER_AWS_APP, app_gcp=PROVIDER_GCP_APP,
            class_name=CLASS_NAME, gpu=GPU,
            target_cold=_pa_target, max_attempts_per_arm=_pa_max,
            skip_first=_pa_skip, teardown=teardown,
        )
        return

    # ── UNET-backing A/B (interleaved current vs anonymous-RAM snapshot) ──
    if backing_ab:
        _ba_gap = VARIANCE_COLD_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _ba_target = int(os.environ.get("V2_BACKING_AB_TARGET_COLD", "7"))
        _ba_max = int(os.environ.get("V2_BACKING_AB_MAX_ATTEMPTS_PER_ARM", "12"))
        _ba_skip = int(os.environ.get("V2_BACKING_AB_SKIP_FIRST", "2"))
        await _run_backing_ab(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
            gap_seconds=_ba_gap, app_a=BACKING_A_APP, app_b=BACKING_B_APP,
            class_name=CLASS_NAME, gpu=GPU,
            target_cold=_ba_target, max_attempts_per_arm=_ba_max,
            skip_first=_ba_skip, teardown=teardown,
        )
        return

    # ── Host-characteristics cold study (unpinned placement) ────────────
    if host_ab:
        _ha_app = os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME) or VARIANCE_APP_NAME
        os.environ["COMFYMODAL_V2_APP_NAME"] = _ha_app
        _ha_gap = VARIANCE_COLD_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _ha_target = int(os.environ.get("V2_HOST_AB_TARGET_COLD", "12"))
        _ha_max = int(os.environ.get("V2_HOST_AB_MAX_ATTEMPTS", "18"))
        _ha_skip = int(os.environ.get("V2_HOST_AB_SKIP_FIRST", "2"))
        await _run_host_ab(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
            gap_seconds=_ha_gap, app_name=_ha_app,
            class_name=CLASS_NAME, gpu=GPU,
            target_cold=_ha_target, max_attempts=_ha_max, skip_first=_ha_skip,
            teardown=teardown,
        )
        return

    # ── Region-pinned cold comparison (one pinned region per invocation) ──
    if region_ab:
        _ra_app = os.environ.get("COMFYMODAL_V2_VARIANCE_APP_NAME", VARIANCE_APP_NAME) or VARIANCE_APP_NAME
        os.environ["COMFYMODAL_V2_APP_NAME"] = _ra_app
        _ra_region = str(region_ab or os.environ.get("COMFYMODAL_V2_REGION", "") or "").strip()
        if not _ra_region:
            raise RuntimeError(
                "region_ab: no pinned region; pass --region-ab REGION or set "
                "COMFYMODAL_V2_REGION (the deployment must be pinned to the same region)"
            )
        _ra_gap = VARIANCE_COLD_GAP_SECONDS if gap_seconds is None else float(gap_seconds)
        _ra_target = int(os.environ.get("V2_REGION_AB_TARGET_COLD", "10"))
        _ra_max = int(os.environ.get("V2_REGION_AB_MAX_ATTEMPTS", "15"))
        await _run_region_ab(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
            gap_seconds=_ra_gap, region=_ra_region, app_name=_ra_app,
            class_name=CLASS_NAME, gpu=GPU,
            target_cold=_ra_target, max_attempts=_ra_max,
            teardown=teardown,
        )
        return

    if acceptance:
        await _run_acceptance_sequence(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
        )
        return

    if cpu_snapshot_unet_ab:
        await _run_ab_compare(
            workflow=workflow, modal_options=modal_options,
            workspace=workspace, transport=transport, output_dir=output_dir,
        )
        return

    artifacts = []
    for index in range(RUN_COUNT):
        artifacts.append(await _run_one(
            index=index,
            workflow=workflow,
            modal_options=modal_options,
            workspace=workspace,
            transport=transport,
            output_dir=output_dir,
            bypass_cpu_snapshot_unet=bypass_cpu_snapshot_unet,
            _defer_waterfall=(RUN_COUNT == 1),
            # Carried into the remote trace metadata via request_origin_info
            # (pre-existing _extra_origin mechanism; unknown keys are ignored
            # by the allowlist so production behavior is unchanged).
            _extra_origin=_benchmark_origin_extra(
                unique_prompt_suffix, conditioning_cache_nonce
            ),
        ))
        # Batch-A acceptance validation: RUN 1 artifact only, strict, no
        # retry and no extra samples.  Never runs unless batch_a_acceptance
        # is enabled (opt-in flag/env); printing happens only in this mode.
        # The raise is authoritative ONLY when no stricter layer is enabled
        # (Batch-B preserves Batch-A's gates; Batch-C wraps Batch-B), so an
        # A-only failure must not abort before the stricter layer runs.
        if index == 0 and batch_a_acceptance:
            from tools.batch_a_acceptance import render_acceptance_block, validate_batch_a
            _bga_res = validate_batch_a(artifacts[-1])
            print(render_acceptance_block(_bga_res), flush=True)
            if not _bga_res.passed and _batch_a_raise_authorized(
                batch_b_acceptance, batch_c_acceptance
            ):
                raise RuntimeError("batch-a acceptance: RUN 1 FAILED Batch-A gates")
        # Batch-B acceptance validation: RUN 1 artifact only, strict, no
        # retry and no extra samples.  Never runs unless batch_b_acceptance
        # is enabled (opt-in flag/env); printing happens only in this mode.
        # The raise is authoritative ONLY when Batch-C is disabled (Batch-C
        # wraps Batch-B, never duplicates it), so a B-only failure must not
        # abort before the stricter Batch-C layer is evaluated.
        if index == 0 and batch_b_acceptance:
            from tools.batch_b_acceptance import (
                batch_b_config_from_env,
                render_batch_b_block,
                validate_batch_b,
            )
            _bgb_cfg = batch_b_config_from_env()
            _bgb_res = validate_batch_b(
                artifacts[-1],
                expect_runtime_state_skip=_bgb_cfg["expect_runtime_state_skip"],
                snapshot_hygiene_enabled=_bgb_cfg["snapshot_hygiene_enabled"],
                snapshot_manifest_enabled=_bgb_cfg["snapshot_manifest_enabled"],
                stage13_tolerance_ms=_bgb_cfg["stage13_tolerance_ms"],
                expect_stage13=_bgb_cfg["expect_stage13"],
                expect_slow_h2d_forensic=_bgb_cfg["expect_slow_h2d_forensic"],
            )
            print(render_batch_b_block(_bgb_res), flush=True)
            if not _bgb_res.passed and _batch_b_raise_authorized(
                batch_c_acceptance
            ):
                raise RuntimeError("batch-b acceptance: RUN 1 FAILED Batch-B gates")
        # Batch-C acceptance validation: RUN 1 artifact only, strict, no
        # retry and no extra samples.  Never runs unless batch_c_acceptance
        # is enabled (opt-in flag/env); printing happens only in this mode.
        # Batch-C wraps Batch-B (never duplicates it) and adds the strict
        # plan-validation fast-path lane when
        # COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH=1.
        if index == 0 and batch_c_acceptance:
            from tools.batch_c_acceptance import (
                batch_c_config_from_env,
                render_batch_c_block,
                validate_batch_c,
            )
            _bgc_cfg = batch_c_config_from_env()
            _bgc_res = validate_batch_c(
                artifacts[-1],
                expect_plan_fast_path=_bgc_cfg["expect_plan_fast_path"],
                expect_runtime_state_skip=_bgc_cfg["expect_runtime_state_skip"],
                snapshot_hygiene_enabled=_bgc_cfg["snapshot_hygiene_enabled"],
                snapshot_manifest_enabled=_bgc_cfg["snapshot_manifest_enabled"],
                stage13_tolerance_ms=_bgc_cfg["stage13_tolerance_ms"],
                expect_stage13=_bgc_cfg["expect_stage13"],
                expect_slow_h2d_forensic=_bgc_cfg["expect_slow_h2d_forensic"],
            )
            print(render_batch_c_block(_bgc_res), flush=True)
            if not _bgc_res.passed:
                raise RuntimeError("batch-c acceptance: RUN 1 FAILED Batch-C gates")
        if index + 1 < RUN_COUNT:
            await _intentional_cold_wait(GAP_SECONDS)
    trace_errors = [
        a for a in artifacts if a.get("_trace_handoff_error")
    ]
    summary = {
        "target": {"app_name": APP_NAME, "class_name": CLASS_NAME, "gpu": GPU},
        "runtime_shape": {
            "requested": requested_shape,
            "guard": shape_guard,
        },
        "run_count": len(artifacts),
        "gap_seconds": GAP_SECONDS,
        "node_registry_preload_ms": _nri_preload_ms,
        "intentional_cold_waits": list(_COLD_WAITS),
        "trace_handoff_errors": len(trace_errors),
        "waterfall_runs": sum(1 for item in artifacts if item.get("waterfall")),
        "runs": [{
            "run_index": item["run_index"],
            "request_id": item.get("request_id", item.get("prompt_id", "")),
            "identity": item["identity"],
            "runtime_shape": item.get("runtime_shape", {}),
            "timing": item["timing"],
        } for item in artifacts],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, default=str, indent=2), encoding="utf-8")
    # Prefer the host-reconciled rebuild (TOTAL WALL denominator) when present;
    # the remote-built partial stays available in the artifact under "waterfall".
    _report_sources = []
    for _item in artifacts:
        if _item.get("waterfall_local"):
            _report_sources.append(("reconciled", _item["waterfall_local"]))
        elif _item.get("waterfall"):
            _report_sources.append(("remote", _item["waterfall"]))
    _reports = [report for _source, report in _report_sources]
    _reconciled_count = sum(1 for _source, _ in _report_sources if _source == "reconciled")
    print(json.dumps({"output_dir": str(output_dir), **summary}, default=str, indent=2))
    if len(_reports) == 1:
        if _reconciled_count == 1:
            print("WATERFALL (host-reconciled)", flush=True)
        print(render_waterfall(_reports[0]), flush=True)
    elif len(_reports) > 1:
        print(render_comparison(_reports), flush=True)

    # ── Campaign manifest (deterministic experiment persistence) ───────
    # Best-effort: collects every per-run record saved above into one
    # campaign_manifest.json.  Never affects the run results or exit path.
    try:
        from comfymodal_runtime.experiment_result_store import write_campaign_manifest
        _records = globals().get("_EXPERIMENT_RECORDS") or []
        if _records:
            _manifest_path = write_campaign_manifest(_records, output_dir=output_dir)
            print(f"[v2.experiment] campaign manifest={_manifest_path}", flush=True)
    except Exception as _manifest_exc:  # noqa: BLE001
        print(
            f"[v2.experiment] campaign manifest skipped: "
            f"{type(_manifest_exc).__name__}: {_manifest_exc}",
            flush=True,
        )

    # Signal failure if any trace handoff failed (run files are preserved)
    if trace_errors:
        error_details = "; ".join(
            f"run_{a['run_index']}: {a['_trace_handoff_error']}"
            for a in trace_errors
        )
        raise RuntimeError(
            f"{len(trace_errors)} trace handoff error(s): {error_details}"
        )


if __name__ == "__main__":
    _parser = argparse.ArgumentParser(description="V2 direct benchmark runner")
    _parser.add_argument(
        "--bypass-cpu-snapshot-unet",
        action="store_true",
        default=False,
        help="Insert diagnostic_bypass_cpu_snapshot_unet=True into compatibility_flags "
             "so the snapshot CLIP serves graph demands but UNET loads "
             "through the original loader (A/B diagnostic mode)",
    )
    _parser.add_argument(
        "--cpu-snapshot-unet-ab",
        action="store_true",
        default=False,
        help="Run A/B comparison: one reuse + one bypass request, compare "
             "unet_runtime_state from trace events, print and save diff "
             "(does not require same remote process)",
    )
    _parser.add_argument(
        "--acceptance",
        action="store_true",
        default=False,
        help="Run explicit acceptance mode: A fresh, B immediate reuse, "
             "C fresh restored. Validates identity, timing, asset proofs, "
             "and acceptance criteria. Exits non-zero on failure.",
    )
    _parser.add_argument(
        "--variance-cold",
        action="store_true",
        default=False,
        help="Run variance-cold mode: one request at a time with a fixed gap, "
             "asserting true cold identity from request-scoped "
             "remote_method_entry (restore_count==1, request_count==1, "
             "nonempty restored_instance_id, fresh container identity). "
             "Opt-in; never the default.",
    )
    _parser.add_argument(
        "--variance-matrix",
        action="store_true",
        default=False,
        help="Run the variance-cold MATRIX: round-robin across four conditions "
             "(diagnostics off/on) x (pretouch off/on), continuing until each "
             "condition collects the target number of valid cold runs. "
             "Preserves every attempt and emits one consolidated handoff report. "
             "Opt-in; never the default.",
    )
    _parser.add_argument(
        "--variance-pretouch",
        type=int,
        choices=(0, 1),
        default=None,
        help="UNET pretouch mode for variance-cold runs: 0=disabled, 1=enabled. "
             "Defaults to env V2_VARIANCE_PRETOUCH (0 when unset).",
    )
    _parser.add_argument(
        "--report-only",
        default=None,
        metavar="DIR",
        help="Render a variance-cold report from an existing artifacts "
             "directory without contacting Modal (offline/testable).",
    )
    _parser.add_argument(
        "--gap-seconds",
        type=float,
        default=None,
        help="Override the inter-run gap (defaults to V2_VARIANCE_COLD_GAP_SECONDS=25).",
    )
    _parser.add_argument(
        "--run-count",
        type=int,
        default=None,
        help="Explicitly override the benchmark run count. Required as --run-count 1 for E22 arms.",
    )
    _parser.add_argument(
        "--teardown",
        choices=("full", "minimal"),
        default=os.environ.get("V2_TEARDOWN_MODE", "full").strip().lower() or "full",
        help="Request teardown mode: full (default) or minimal "
             "(COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN; skip unload/cleanup/GC/CUDA). "
             "Defaults to env V2_TEARDOWN_MODE.",
    )
    _parser.add_argument(
        "--pin-transfer",
        type=int,
        choices=(0, 1),
        default=int(os.environ.get("V2_PIN_TRANSFER", "0") or 0),
        help="Pin the CPU-snapshot UNET storages with cudaHostRegister before "
             "the transfer (COMFYMODAL_V2_PIN_UNET_TRANSFER) so the H2D copy "
             "uses the true DMA path: 0=disabled (default), 1=enabled. "
             "Defaults to env V2_PIN_TRANSFER.",
    )
    _parser.add_argument(
        "--quiesced-transfer",
        type=int,
        choices=(0, 1),
        default=int(os.environ.get("V2_QUIESCED_TRANSFER", "0") or 0),
        help="Quiesce the early UNET transfer (request-scoped "
             "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER): the request waits for "
             "the synchronized transfer to complete before graph/prefill "
             "execution begins and samples per-thread CPU deltas during the "
             "transfer. 0=overlap (A, default), 1=quiesced (B). "
             "Defaults to env V2_QUIESCED_TRANSFER.",
    )
    _parser.add_argument(
        "--transfer-ab",
        action="store_true",
        default=False,
        help="Run the interleaved UNET-transfer contention A/B: A (overlap) "
             "and B (quiesced transfer) alternating with 25s cold gaps until "
             "each condition collects 10 valid cold runs (cap 15 attempts "
             "per condition). Preserves every attempt and writes "
             "transfer_ab_report.md.",
    )
    _parser.add_argument(
        "--region-ab",
        default=None,
        metavar="REGION",
        help="Run the region-pinned cold transfer comparison for one pinned "
             "region (e.g. us-east-2 or us-east4; the deployment must be "
             "pinned to the same region via COMFYMODAL_V2_REGION). Excludes "
             "the first 2 attempts (snapshot/cache build + the run after), "
             "then collects 10 valid cold runs (cap 15 attempts). Writes "
             "region_ab_report.md.",
    )
    _parser.add_argument(
        "--host-ab",
        action="store_true",
        default=False,
        help="Run the unpinned host-characteristics cold study: no region pin, "
             "every attempt carries remote host_diagnostics (provider, region, "
             "CPU model/family/stepping, sockets/cores/threads, NUMA, kernel, "
             "GPU UUID/PCI bus/PCIe gen+width, driver/CUDA, VM family). "
             "Excludes the first 2 attempts (snapshot/cache build + the run "
             "after), then collects 12 valid cold runs (cap 18 attempts; "
             "V2_HOST_AB_TARGET_COLD / V2_HOST_AB_MAX_ATTEMPTS / "
             "V2_HOST_AB_SKIP_FIRST). Writes host_ab_report.md.",
    )
    _parser.add_argument(
        "--backing-ab",
        action="store_true",
        default=False,
        help="Run the interleaved UNET-backing A/B cold study: Arm A = current "
             "CPU-snapshot UNET, Arm B = anonymous-RAM snapshot (clone every "
             "UNET parameter/buffer into fresh anonymous CPU memory before "
             "snapshot capture).  Two separate shadow deployments "
             "(COMFYMODAL_V2_BACKING_A_APP / _BACKING_B_APP), strictly "
             "interleaved A,B,A,B,..; each arm discards its first 2 attempts "
             "and collects 7 valid cold runs (cap 12 per arm; "
             "V2_BACKING_AB_TARGET_COLD / _MAX_ATTEMPTS_PER_ARM / _SKIP_FIRST). "
             "Per-run synthetic 2 GiB anonymous H2D probe + /proc/self/maps "
             "backing evidence. Writes backing_ab_report.md.",
    )
    _parser.add_argument(
        "--provider-ab",
        action="store_true",
        default=False,
        help="Run the interleaved AWS-vs-GCP provider + page-path isolation "
             "study: Arm aws = cloud-pinned AWS (no region), Arm gcp = "
             "cloud-pinned GCP (no region); shadow deployments "
             "(COMFYMODAL_V2_PROVIDER_AWS_APP / _PROVIDER_GCP_APP), strictly "
             "interleaved, per-arm skip-first-2, 7 valid cold per arm, cap 12 "
             "attempts per arm, provider-mismatch attempts rejected "
             "(V2_PROVIDER_AB_TARGET_COLD / _MAX_ATTEMPTS_PER_ARM / "
             "_SKIP_FIRST).  Per-run page-path record: mincore residency "
             "before/after native one-byte-per-page traversal, real UNET H2D "
             "immediately after traversal, then 12.31 GB contiguous synthetic "
             "H2D and a 454-storage synthetic H2D (isolated, after the real "
             "transfer). Writes provider_ab_report.md.",
    )
    _parser.add_argument(
        "--volume-read",
        action="store_true",
        default=False,
        help="Run the mounted-Volume raw sequential-read benchmark: pure "
             "read speed of diffusion_models/"
             "z_image_turbo_bf16.safetensors from the mounted models volume. "
             "No graph execution, model loading, GPU work, hashing, or /tmp "
             "writes.  Each attempt performs two buffered os.read passes "
             "(primary + warm-cache).  V2_VOLUME_READ_RUN_COUNT (default 3) "
             "controls attempts; a 25s cold gap is applied between attempts. "
             "Opt-in; never the default.",
    )
    _parser.add_argument(
        "--snapshot-restore-only",
        action="store_true",
        default=False,
        help="Run the UNET-absent snapshot restore-only benchmark: exactly "
             "V2_RESTORE_ONLY_RUN_COUNT (default 6) valid reused-snapshot "
             "restore-only probes against the deployment built with "
             "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1.  Every probe is a "
             "candidate (no beautification probes); invalid/DNF probes never "
             "count; the loop hard-stops as soon as the target of valid "
             "probes is reached (bounded by V2_RESTORE_ONLY_MAX_ATTEMPTS, "
             "default 40).  Per probe captures command dispatch timestamp, "
             "the Modal pre-Python 'Restoring Function from memory snapshot.' "
             "banner (via app-log tailing anchored to the probe's own "
             "method-entry line), the container-observed first-Python-restore "
             "timestamp, restore timing, method entry, identity and RSS.  A "
             "missing decisive timestamp/identity fails that probe.  "
             "Provider/region unpinned.  Opt-in; never the default.",
    )
    _parser.add_argument(
        "--snapshot-restore-only-backfill",
        default=None,
        metavar="DIR",
        help="REPORT-ONLY backfill for an existing restore-only run directory: "
             "re-fetch system/INFO + stdout banner evidence for the FIRST "
             "V2_RESTORE_ONLY_RUN_COUNT (default 6) attempts (indices 0..5), "
             "re-run validity, and write backfilled_run_<n>.json copies plus "
             "backfilled_summary.json / backfilled_restore_only_report.json.  "
             "Log retrieval ONLY — never creates ModalTransport and never "
             "invokes the remote probe.  Fails (nonzero exit) unless exactly "
             "six valid probes are recovered; never substitutes later "
             "attempts.  Opt-in; never the default.",
    )
    _parser.add_argument(
        "--experiment",
        default="",
        help="V2 A/B campaign experiment label stored in every persisted "
             "experiment record (default: '').",
    )
    _parser.add_argument(
        "--arm",
        default="",
        help="V2 A/B campaign arm label (e.g. pinned_staging) stored in every "
             "persisted experiment record (default: '').",
    )
    _parser.add_argument(
        "--run-role",
        choices=("sample", "validation_discard", "probe"),
        default="sample",
        help="Role of every run in this invocation for campaign persistence: "
             "sample (retained), validation_discard (discarded), or probe "
             "(default: sample).",
    )
    _parser.add_argument(
        "--batch-a-acceptance",
        action="store_true",
        default=False,
        help="Batch-A validation mode: after RUN 1, validate the strict "
             "Batch-A gates (fresh, status, reconciliation<=50ms, G1 single "
             "UNET read/bind/H2D, models reload skip, node timestamps, "
             "terminal cleanup stamps, host telemetry overhead<=20ms, no slow "
             "forensic trigger) and print the BATCH A ACCEPTANCE block. "
             "Fails (non-zero exit) when gates fail. Opt-in; never the "
             "default. Also enabled by COMFYMODAL_V2_BATCH_A_ACCEPTANCE=1.",
    )
    _parser.add_argument(
        "--batch-b-acceptance",
        action="store_true",
        default=False,
        help="Batch-B validation mode: after RUN 1, validate the strict "
             "Batch-B gates (Batch-A preserved, runtime-state skip guard, "
             "snapshot hygiene, snapshot manifest, stage-13 decomposition "
             "reconciliation, host telemetry) and print the BATCH B "
             "ACCEPTANCE block.  Fails (non-zero exit) when gates fail. "
             "Opt-in; never the default.  Also enabled by "
             "COMFYMODAL_V2_BATCH_B_ACCEPTANCE=1.",
    )
    _parser.add_argument(
        "--batch-c-acceptance",
        action="store_true",
        default=False,
        help="Batch-C validation mode: after RUN 1, validate the strict "
             "Batch-C gates (Batch-B preserved plus the plan-validation "
             "fast-path lane: future_fast_path_eligible, plan_proof_decision "
             "plan_validation_fast_path, consumed=True, no legacy_validation_"
             "fallback, no certificate volume_read fallback, deployment hash / "
             "custom-nodes generation / dependency proof matches) and print "
             "the BATCH C ACCEPTANCE block.  Fails (non-zero exit) when gates "
              "fail.  Opt-in; never the default.  Also enabled by "
              "COMFYMODAL_V2_BATCH_C_ACCEPTANCE=1 (and automatically by "
              "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH=1).",
    )
    _parser.add_argument(
        "--prime-registry-proof",
        action="store_true",
        default=False,
        help="Load the full node registry ONCE and persist the registry-proof/validation "
             "store entry for the canonical benchmark workflow. No Modal calls, no "
             "submission. Intended to run at deploy time (deploy_and_run_v2_single.bat) "
             "so every later user-equivalent benchmark command skips the registry import.",
    )
    _parser.add_argument(
        "--unique-prompt-suffix",
        default="",
        help="Append a unique token to every prompt text source in the workflow so "
             "the exact-conditioning cache key is unique per run (deterministic miss). "
             "Pass a fresh token per run (e.g. uuid/timestamp).",
    )
    _parser.add_argument(
        "--conditioning-cache-nonce",
        default="",
        help="Semantic-neutral exact-conditioning cache nonce: forces a cache "
             "MISS under a fresh value WITHOUT changing the workflow/prompt/"
             "seed/sampler sent to ComfyUI. Pass a fresh uuid per run. "
             "Never used for --unique-prompt-suffix semantics.",
    )
    _parser.add_argument(
        "--verify-d6-profile",
        action="store_true",
        default=False,
        help="Fail-fast local check of the D6 fast-path deploy profile against "
             "the actual _runtime_env() construction. Exits 0 on exact match, "
             "1 on mismatch. Aborts BEFORE any deploy.",
    )
    _parser.add_argument(
        "--verify-e10-profile",
        action="store_true",
        default=False,
        help="Fail-fast local check of the complete E10 bucket-first B profile "
             "against the actual _runtime_env() deployment mapping. Exits "
             "before deploy or any Modal call.",
    )
    _parser.add_argument(
        "--verify-e10-remote-profile",
        action="store_true",
        default=False,
        help="Read the deployed container's exact E10 bucket-first environment "
             "through run_env_probe and fail before any graph request.",
    )
    _parser.add_argument(
        "--verify-run-preflight",
        action="store_true",
        default=False,
        help="Fail-fast local request preflight for run_v2_single.bat, run "
             "BEFORE Modal submission: validates the request environment "
             "(app, class, CPU/MEM/baselines, runtime-shape fingerprint, D1 "
             "proof coverage, run count) against the deployed identity "
             "recorded in .deployed_state.json, and the nonce (if any) "
             "through _resolve_nonce_target_app(). Exits 0=PASS / 1=FAIL; "
             "the run batch aborts on FAIL before any Modal call or spend.",
    )
    _parser.add_argument(
        "--verify-e22-arm-profile",
        action="store_true",
        default=False,
        help="Fail-fast local check of the E22 causal A/B arm profile: "
             "E19 atomic profile + arm-specific CHECKPOINT_PREWARM (0 or 1). "
             "Exits 0 on exact match, 1 on mismatch. Aborts BEFORE any deploy.",
    )
    _parser.add_argument(
        "--verify-e25-profile",
        action="store_true",
        default=False,
        help="Fail-fast local check of the E25 whole-critical-path validation "
             "profile: E19 atomic base + speculative CLIP hydration + GPU fast "
             "return + optimization diagnostics + canonical late VAE. "
             "Exits 0 on exact match, 1 on mismatch. Aborts BEFORE any deploy.",
    )
    _parser.add_argument(
        "--verify-e26-profile",
        action="store_true",
        default=False,
        help="Fail-fast local check of the E26 concrete cold-wins validation "
             "profile: E19 atomic base + E26 speculative CLIP (frozen-manifest "
             "absolute paths) + production GPU fast return + checkpoint "
             "prewarm + late VAE + optimization diagnostics.  Exits 0 on exact "
             "match, 1 on mismatch. Aborts BEFORE any deploy.",
    )
    _parser.add_argument(
        "--verify-e28-profile",
        action="store_true",
        default=False,
        help="Fail-fast local check of the E28 critical-path implementation "
             "validation profile: E19 atomic base + earliest restore-time "
             "speculative CLIP + tuned direct-GPU loader defaults (CLIP "
             "T8/B64MiB, UNET T8/B256MiB) + multi-window Gantt + E27 "
             "forensics; FP32 cast-once OFF.  Exits 0 on exact match, 1 on "
             "mismatch. Aborts BEFORE any deploy.",
    )
    _args = _parser.parse_args()

    # Apply the explicit count to the normal benchmark loop as well as the
    # specialized variance modes.  E22 is intentionally fail-closed here so
    # a wrapper regression cannot spend a second request.
    if _args.run_count is not None:
        if _args.run_count < 1:
            print("E22 run count must be a positive integer", flush=True)
            sys.exit(1)
        RUN_COUNT = int(_args.run_count)
    if _e22_arm_active() and not _args.prime_registry_proof:
        _e22_env_run_count = os.environ.get("V2_BENCHMARK_RUNS", "").strip()
        if _args.run_count != 1 or _e22_env_run_count != "1":
            print(
                "=== ERROR: E22 requires explicit --run-count 1 and "
                "V2_BENCHMARK_RUNS=1; refusing paid execution ===",
                flush=True,
            )
            sys.exit(1)

    # E26 hard single-run guard: the validation selector requires
    # --run-count 1 + V2_BENCHMARK_RUNS=1 + a fresh conditioning nonce.
    # Local-only verify subcommands (no Modal spend) are exempt — they run
    # during the wrapper's pre-deploy/pre-request gates and do not execute
    # the paid request.
    _e26_verify_only = bool(
        _args.verify_d6_profile
        or _args.verify_e10_profile
        or _args.verify_e10_remote_profile
        or _args.verify_run_preflight
        or _args.verify_e22_arm_profile
        or _args.verify_e25_profile
        or _args.verify_e26_profile
        or _args.verify_e28_profile
    )
    if _e26_profile_active() and not _args.prime_registry_proof and not _e26_verify_only:
        _e26_env_run_count = os.environ.get("V2_BENCHMARK_RUNS", "").strip()
        if _args.run_count != 1 or _e26_env_run_count != "1":
            print(
                "=== ERROR: E26 validation requires explicit --run-count 1 "
                f"and V2_BENCHMARK_RUNS=1 (got {_args.run_count!r} / "
                f"{_e26_env_run_count!r}); refusing paid execution ===",
                flush=True,
            )
            sys.exit(1)
        _e26_nonce = os.environ.get("V2_E26_CONDITIONING_NONCE", "").strip()
        if not _e26_nonce:
            print(
                "=== ERROR: E26 validation requires V2_E26_CONDITIONING_NONCE; "
                "refusing paid execution ===",
                flush=True,
            )
            sys.exit(1)

    # E25 hard single-run guard: the validation selector requires
    # --run-count 1 + V2_BENCHMARK_RUNS=1 + a fresh conditioning nonce.
    # Local-only verify subcommands (no Modal spend) are exempt — they run
    # during the wrapper's pre-deploy/pre-request gates and do not execute
    # the paid request.
    _e25_verify_only = bool(
        _args.verify_d6_profile
        or _args.verify_e10_profile
        or _args.verify_e10_remote_profile
        or _args.verify_run_preflight
        or _args.verify_e22_arm_profile
        or _args.verify_e25_profile
        or _args.verify_e26_profile
        or _args.verify_e28_profile
    )
    if _e25_profile_active() and not _args.prime_registry_proof and not _e25_verify_only:
        _e25_env_run_count = os.environ.get("V2_BENCHMARK_RUNS", "").strip()
        if _args.run_count != 1 or _e25_env_run_count != "1":
            print(
                "=== ERROR: E25 validation requires explicit --run-count 1 "
                f"and V2_BENCHMARK_RUNS=1 (got {_args.run_count!r} / "
                f"{_e25_env_run_count!r}); refusing paid execution ===",
                flush=True,
            )
            sys.exit(1)
        _e25_nonce = os.environ.get("V2_E25_CONDITIONING_NONCE", "").strip()
        if not _e25_nonce:
            print(
                "=== ERROR: E25 validation requires V2_E25_CONDITIONING_NONCE; "
                "refusing paid execution ===",
                flush=True,
            )
            sys.exit(1)

    # E28 hard single-run guard: the validation selector requires
    # --run-count 1 + V2_BENCHMARK_RUNS=1 + a fresh conditioning nonce.
    # Local-only verify subcommands (no Modal spend) are exempt — they run
    # during the wrapper's pre-deploy/pre-request gates and do not execute
    # the paid request.
    _e28_verify_only = bool(
        _args.verify_d6_profile
        or _args.verify_e10_profile
        or _args.verify_e10_remote_profile
        or _args.verify_run_preflight
        or _args.verify_e22_arm_profile
        or _args.verify_e25_profile
        or _args.verify_e26_profile
        or _args.verify_e28_profile
    )
    if _e28_profile_active() and not _args.prime_registry_proof and not _e28_verify_only:
        _e28_env_run_count = os.environ.get("V2_BENCHMARK_RUNS", "").strip()
        if _args.run_count != 1 or _e28_env_run_count != "1":
            print(
                "=== ERROR: E28 validation requires explicit --run-count 1 "
                f"and V2_BENCHMARK_RUNS=1 (got {_args.run_count!r} / "
                f"{_e28_env_run_count!r}); refusing paid execution ===",
                flush=True,
            )
            sys.exit(1)
        _e28_nonce = os.environ.get("V2_E28_CONDITIONING_NONCE", "").strip()
        if not _e28_nonce:
            print(
                "=== ERROR: E28 validation requires V2_E28_CONDITIONING_NONCE; "
                "refusing paid execution ===",
                flush=True,
            )
            sys.exit(1)

    # Campaign persistence args must be reachable from _run_one/main (and
    # from the preflight's nonce-target resolution).
    _EXPERIMENT_ARGS = _args

    # D6 atomic deploy gate: --verify-d6-profile runs the fail-fast local
    # check and exits (0=PASS / 1=FAIL) BEFORE any Modal work or deploy.
    if _args.verify_d6_profile:
        sys.exit(_run_d6_verify_cli())

    if _args.verify_e10_profile:
        sys.exit(_run_e10_profile_cli())

    if _args.verify_e10_remote_profile:
        sys.exit(asyncio.run(_run_e10_remote_profile_cli()))

    # Run preflight gate: --verify-run-preflight validates the request
    # environment against the recorded deployment and exits BEFORE any
    # Modal submission (fail-closed; the run batch aborts on FAIL).
    if _args.verify_run_preflight:
        sys.exit(_run_run_preflight_cli(nonce=_args.conditioning_cache_nonce))

    if _args.verify_e22_arm_profile:
        ok, details = verify_e22_arm_profile()
        print("[v2.e22_arm_profile]", flush=True)
        print(f"profile={details.get('profile', 'default')}", flush=True)
        _profile_keys = tuple(E19_FINAL_COLD_LOADER_PROFILE)
        print(f"ATOMIC_PROFILE={E19_FINAL_COLD_LOADER_PROFILE_NAME}", flush=True)
        for _key in _profile_keys:
            _short = _key.removeprefix("COMFYMODAL_V2_").lower()
            print(f"{_short}={details.get(_key, 'unavailable')}", flush=True)
        print(f"e22_arm={details.get('e22_arm', '')}", flush=True)
        print(f"validation={details.get('validation', 'FAIL')}", flush=True)
        if details.get("error"):
            print(f"error={details['error']}", flush=True)
        if ok:
            print("PROFILE ACCEPTED", flush=True)
            print(
                "DEPLOY_COMMAND=modal deploy -m "
                "comfymodal_runtime.modal_app",
                flush=True,
            )
        else:
            print("PROFILE REJECTED", flush=True)
        sys.exit(0 if ok else 1)

    if _args.verify_e25_profile:
        ok, details = verify_e25_validation_profile()
        print("[v2.e25_profile]", flush=True)
        print(f"profile={details.get('profile', 'default')}", flush=True)
        print(f"ATOMIC_PROFILE={details.get('profile', 'default')}", flush=True)
        for _key in tuple(E19_FINAL_COLD_LOADER_PROFILE) + tuple(E25_VALIDATION_PROFILE):
            _short = _key.removeprefix("COMFYMODAL_V2_").lower()
            print(f"{_short}={details.get(_key, 'unavailable')}", flush=True)
        print(f"validation={details.get('validation', 'FAIL')}", flush=True)
        if details.get("error"):
            print(f"error={details['error']}", flush=True)
        if ok:
            print("PROFILE ACCEPTED", flush=True)
            print(
                "DEPLOY_COMMAND=modal deploy -m "
                "comfymodal_runtime.modal_app",
                flush=True,
            )
        else:
            print("PROFILE REJECTED", flush=True)
        sys.exit(0 if ok else 1)

    if _args.verify_e26_profile:
        ok, details = verify_e26_validation_profile()
        print("[v2.e26_profile]", flush=True)
        print(f"profile={details.get('profile', 'default')}", flush=True)
        print(f"ATOMIC_PROFILE={details.get('profile', 'default')}", flush=True)
        for _key in tuple(E19_FINAL_COLD_LOADER_PROFILE) + tuple(E26_VALIDATION_PROFILE):
            _short = _key.removeprefix("COMFYMODAL_V2_").lower()
            print(f"{_short}={details.get(_key, 'unavailable')}", flush=True)
        print(f"validation={details.get('validation', 'FAIL')}", flush=True)
        if details.get("error"):
            print(f"error={details['error']}", flush=True)
        if ok:
            print("PROFILE ACCEPTED", flush=True)
            print(
                "DEPLOY_COMMAND=modal deploy -m "
                "comfymodal_runtime.modal_app",
                flush=True,
            )
        else:
            print("PROFILE REJECTED", flush=True)
        sys.exit(0 if ok else 1)

    if _args.verify_e28_profile:
        ok, details = verify_e28_validation_profile()
        print("[v2.e28_profile]", flush=True)
        print(f"profile={details.get('profile', 'default')}", flush=True)
        print(f"ATOMIC_PROFILE={details.get('profile', 'default')}", flush=True)
        for _key in (tuple(E19_FINAL_COLD_LOADER_PROFILE)
                     + tuple(E28_VALIDATION_PROFILE) + tuple(E28_LOADER_PROFILE)):
            _short = _key.removeprefix("COMFYMODAL_V2_").lower()
            print(f"{_short}={details.get(_key, 'unavailable')}", flush=True)
        print(f"validation={details.get('validation', 'FAIL')}", flush=True)
        if details.get("error"):
            print(f"error={details['error']}", flush=True)
        if ok:
            print("PROFILE ACCEPTED", flush=True)
            print(
                "DEPLOY_COMMAND=modal deploy -m "
                "comfymodal_runtime.modal_app",
                flush=True,
            )
        else:
            print("PROFILE REJECTED", flush=True)
        sys.exit(0 if ok else 1)

    _variance_pretouch = _resolve_pretouch(_args.variance_pretouch)

    # --variance-cold / --variance-matrix imply the matching V2_BENCHMARK_MODE
    # semantics; the env mode alone is also honoured by the .bat wrappers.
    _variance_cold = _args.variance_cold or (
        os.environ.get("V2_BENCHMARK_MODE", "").strip().lower() == "variance_cold"
    )
    _variance_matrix = _args.variance_matrix or (
        os.environ.get("V2_BENCHMARK_MODE", "").strip().lower() == "variance_matrix"
    )
    _host_ab = _args.host_ab or (
        os.environ.get("V2_BENCHMARK_MODE", "").strip().lower() == "host_ab"
    )
    _backing_ab = _args.backing_ab or (
        os.environ.get("V2_BENCHMARK_MODE", "").strip().lower() == "backing_ab"
    )
    _volume_read = _args.volume_read or (
        os.environ.get("V2_BENCHMARK_MODE", "").strip().lower() == "volume_read"
    )
    _snapshot_restore_only = _args.snapshot_restore_only or (
        os.environ.get("V2_BENCHMARK_MODE", "").strip().lower() == "snapshot_restore_only"
    )
    _provider_ab = _args.provider_ab or (
        os.environ.get("V2_BENCHMARK_MODE", "").strip().lower() == "provider_ab"
    )

    # Batch-A acceptance validation mode: opt-in via --batch-a-acceptance or
    # COMFYMODAL_V2_BATCH_A_ACCEPTANCE=1.  Validates the RUN 1 artifact against
    # the strict Batch-A gates and prints the BATCH A ACCEPTANCE block.
    _batch_a_acceptance = bool(_args.batch_a_acceptance) or (
        os.environ.get("COMFYMODAL_V2_BATCH_A_ACCEPTANCE", "").strip().lower()
        in ("1", "true", "yes")
    )

    # Batch-B acceptance validation mode: opt-in via --batch-b-acceptance or
    # COMFYMODAL_V2_BATCH_B_ACCEPTANCE=1.  Validates the RUN 1 artifact against
    # the strict Batch-B gates and prints the BATCH B ACCEPTANCE block.
    _batch_b_acceptance = bool(_args.batch_b_acceptance) or (
        os.environ.get("COMFYMODAL_V2_BATCH_B_ACCEPTANCE", "").strip().lower()
        in ("1", "true", "yes")
    )

    # Batch-C acceptance validation mode: opt-in via --batch-c-acceptance or
    # COMFYMODAL_V2_BATCH_C_ACCEPTANCE=1, or automatically when the strict
    # fast-path expectation COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH=1 is
    # set (a fast-path expectation without the layer would silently not gate).
    _batch_c_acceptance = bool(_args.batch_c_acceptance) or (
        os.environ.get("COMFYMODAL_V2_BATCH_C_ACCEPTANCE", "").strip().lower()
        in ("1", "true", "yes")
    ) or (
        os.environ.get("COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH", "").strip().lower()
        in ("1", "true", "yes")
    )

    async def _run_main_with_drain_teardown() -> None:
        try:
            await main(
                bypass_cpu_snapshot_unet=_args.bypass_cpu_snapshot_unet,
                cpu_snapshot_unet_ab=_args.cpu_snapshot_unet_ab,
                acceptance=_args.acceptance,
                variance_cold=_variance_cold,
                variance_matrix=_variance_matrix,
                transfer_ab=_args.transfer_ab,
                region_ab=_args.region_ab,
                host_ab=_host_ab,
                backing_ab=_backing_ab,
                provider_ab=_provider_ab,
                volume_read=_volume_read,
                snapshot_restore_only=_snapshot_restore_only,
                snapshot_restore_only_backfill=_args.snapshot_restore_only_backfill,
                variance_pretouch=_variance_pretouch,
                report_only=_args.report_only,
                gap_seconds=_args.gap_seconds,
                run_count=_args.run_count,
                teardown=_args.teardown,
                pin_transfer=int(_args.pin_transfer),
                quiesced_transfer=int(_args.quiesced_transfer),
                batch_a_acceptance=_batch_a_acceptance,
                batch_b_acceptance=_batch_b_acceptance,
                batch_c_acceptance=_batch_c_acceptance,
                prime_registry_proof=_args.prime_registry_proof,
                unique_prompt_suffix=_args.unique_prompt_suffix,
                conditioning_cache_nonce=_args.conditioning_cache_nonce,
            )
        finally:
            # Process/loop teardown: join any remaining persistence drains with
            # a bounded budget so no drain task is left pending at loop
            # shutdown (no "Task was destroyed but it is pending" warnings).
            try:
                from comfymodal_runtime.modal_transport import join_all_persistence_drains
                _joined = await join_all_persistence_drains(timeout=_PERSISTENCE_DRAIN_JOIN_TIMEOUT)
                if _joined:
                    print(f"[v2.benchmark] persistence drains joined={len(_joined)}", flush=True)
            except Exception as _teardown_exc:  # noqa: BLE001
                print(
                    f"[v2.benchmark] persistence drain teardown failed: "
                    f"{type(_teardown_exc).__name__}: {_teardown_exc}",
                    flush=True,
                )

    asyncio.run(_run_main_with_drain_teardown())
