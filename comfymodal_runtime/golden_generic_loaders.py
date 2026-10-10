"""Request-scoped generic fast-loader composition over shared Golden cores.

Generic (non-canonical) v2 plan runs execute arbitrary graphs through the
upstream executor with native per-node file reads.  This module lets those
runs reuse THE SAME Golden loader implementations (imported, never copied)
for supported loader nodes:

* classify each loader node (supported / unsupported + reason),
* invoke the unmodified ``golden_*_load`` stage functions with a REAL
  ``GoldenSession`` built for the generic request,
* insert the adopted model objects into the executor output cache so the
  native node functions hit cache and skip their file reads,
* retain QD owners for exactly the request duration, then release them
  WITHOUT touching the shared dispatcher or any canonical lifecycle.

Activation is strictly generic-path: the installer is only ever called from
the v2 plan-execution flow, which canonical Golden runs never enter (they
would trip ``golden_prompt_executor_forbidden``).  Every failure — unsupported
contract, missing file, loader error — falls back to the native path and is
recorded per node.  Nothing here mutates canonical behavior.

Phase 1 covers CLIPLoader only (the slowest loader on measured workloads).
VAELoader and UNETLoader classify explicitly so their status is observable;
UNET scaled-FP8 in particular is contractually rejected by the shared core
and must stay native.

Two shared source-read arms are attempted in order, both imported never
copied:

* ``qd4_demand`` (first): the canonical ``clip_qd_load`` demand reader —
  self-contained per call (workers joined before return, no persistent
  pool), so it is immune to persistent-pool poisoning.  Construction
  mirrors the native CLIPLoader recipe exactly over the same shared
  ``comfy.sd.load_text_encoder_state_dicts`` delegation; only the
  file-read step is fast.
* ``m2_transport`` (fallback): the persistent M2 singleton via the
  unmodified ``golden_clip_load`` stage.  Currently fails closed
  fleet-wide (persistent source pool poisoned by a cancelled dispatcher
  handoff); kept so a healthy pool is used when available.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Mapping, Sequence


# Loader classes this composition knows how to classify.  Only CLIPLoader
# has a composed fast path today; the rest report explicit reasons.
_KNOWN_LOADER_CLASSES = frozenset({
    "CLIPLoader",
    "DualCLIPLoader",
    "VAELoader",
    "UNETLoader",
    "CheckpointLoader",
    "CheckpointLoaderSimple",
})

# Roles mirror the canonical role map so accounting stays comparable.
_ROLE_MAP = {
    "CLIPLoader": "clip",
    "DualCLIPLoader": "clip",
    "VAELoader": "vae",
    "UNETLoader": "unet",
    "CheckpointLoader": "checkpoint",
    "CheckpointLoaderSimple": "checkpoint",
}


def classify_loader_node(
    class_type: str,
    inputs: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Classify one loader node for shared-core composition (pure logic).

    Returns ``{"supported": bool, "role": str, "reason": str, ...}``.
    Supported means: attempt the shared Golden core; anything else means run
    the native node function untouched.  Never raises.
    """
    class_type = str(class_type or "")
    inputs = inputs if isinstance(inputs, dict) else {}
    role = _ROLE_MAP.get(class_type, "?")
    unsupported = {"supported": False, "role": role, "reason": ""}
    if class_type not in _KNOWN_LOADER_CLASSES:
        unsupported["reason"] = "unknown_loader_class"
        return unsupported
    if class_type in ("CheckpointLoader", "CheckpointLoaderSimple"):
        unsupported["reason"] = "checkpoint_not_role_separable"
        return unsupported
    if class_type == "DualCLIPLoader":
        unsupported["reason"] = "dual_clip_deferred"
        return unsupported
    if class_type == "UNETLoader":
        unsupported["reason"] = "unet_deferred"
        return unsupported
    if class_type == "VAELoader":
        unsupported["reason"] = "vae_deferred"
        return unsupported
    # CLIPLoader from here on.
    clip_name = inputs.get("clip_name")
    if not isinstance(clip_name, str) or not clip_name.strip():
        unsupported["reason"] = "clip_name_missing"
        return unsupported
    device = inputs.get("device", "default")
    if isinstance(device, str) and device.strip().lower() == "cpu":
        return dict(supported=False, role=role,
                    reason="explicit_cpu_device_respected")
    clip_type = inputs.get("type", "stable_diffusion")
    if not isinstance(clip_type, str) or not clip_type.strip():
        clip_type = "stable_diffusion"
    return dict(supported=True, role=role, reason="",
                clip_name=str(clip_name), clip_type=str(clip_type),
                device=str(device or "default"))


def resolve_clip_type_shared(name: str) -> Any:
    """Resolve a CLIPType via the shared Golden resolver (no fallback here)."""
    from .golden_serial import resolve_clip_type

    return resolve_clip_type(name)


def _default_path_resolver(folder: str, filename: str) -> str | None:
    """Resolve a model filename to an absolute path via folder_paths."""
    try:
        import folder_paths

        path = folder_paths.get_full_path(folder, filename)
        if path and os.path.isfile(path):
            return path
        return None
    except Exception:
        return None


class GenericLoaderHolder:
    """Retains generic-composition sessions/owners for one request.

    QD owners backing adopted models must outlive executor cache use.
    Release happens exactly once at request end via :meth:`close`, which
    releases single owners WITHOUT shutting down the shared dispatcher.
    Idempotent and never raises.
    """

    def __init__(self) -> None:
        self._sessions: list[Any] = []
        self._owners: list[Any] = []
        self._closed = False

    def retain(self, session: Any, owners: Sequence[Any] | None = None) -> None:
        if session is not None:
            self._sessions.append(session)
        for owner in list(owners or []):
            if owner is not None:
                self._owners.append(owner)

    def close(self) -> dict[str, Any]:
        """Release retained single owners. Never touches the dispatcher."""
        result = {"released": 0, "errors": 0}
        if self._closed:
            result["already_closed"] = True
            return result
        self._closed = True
        for owner in self._owners:
            try:
                release = getattr(owner, "release_storage", None)
                if callable(release):
                    release()
                else:
                    close = getattr(owner, "close", None)
                    if callable(close):
                        close()
                result["released"] += 1
            except Exception:
                result["errors"] += 1
        self._owners.clear()
        self._sessions.clear()
        return result


def build_generic_clip_session(
    *,
    clip_filenames: Sequence[str],
    clip_type: str,
    folder: str,
    request_id: str,
    volume: Any = None,
    request_extra: Mapping[str, Any] | None = None,
) -> Any:
    """Build a REAL GoldenSession adapted for one generic CLIP load.

    Uses the same session/contract/spec classes as canonical runs; only the
    inputs differ (actual node filenames/type instead of frozen canonical
    values).  No golden_serial.py changes required.
    """
    from .golden_serial import (
        ClipLoadSpec,
        GoldenRequest,
        GoldenSession,
        GoldenWorkflowContract,
    )

    names = tuple(str(n) for n in (clip_filenames or []) if str(n or "").strip())
    if not names:
        raise ValueError("generic_clip_filenames_missing")
    spec = ClipLoadSpec(
        checkpoint_names=names,
        clip_type=str(clip_type or "stable_diffusion"),
        folder=str(folder or "text_encoders"),
    )
    contract = GoldenWorkflowContract(clip_spec=spec)
    extra = dict(request_extra or {})
    extra.setdefault("generic_loader_composition", True)
    extra.setdefault("golden_mode", "serial")
    request = GoldenRequest(
        request_id=str(request_id or "generic-clip"),
        prompt={},
        extra_data=extra,
    )
    session = GoldenSession(
        request,
        volume=volume,
        contract=contract,
    )
    return session


async def compose_generic_clip_load(
    *,
    clip_filenames: Sequence[str],
    clip_type: str,
    folder: str,
    request_id: str,
    path_resolver: Callable[[str, str], str | None] | None = None,
    volume: Any = None,
) -> dict[str, Any]:
    """Load CLIP via the SHARED Golden core (same code canonical runs use).

    Returns ``{"ok": True, "clip": ..., "session": ..., "owners": [...],
    " elapsed_ms": ...}`` or ``{"ok": False, "reason": ...}``.  Never raises:
    every failure must fall back to the native node function.
    """
    started_ns = time.monotonic_ns()
    resolve = path_resolver or _default_path_resolver
    try:
        names = [str(n) for n in (clip_filenames or []) if str(n or "").strip()]
        if not names:
            return {"ok": False, "reason": "clip_filenames_missing"}
        resolved: list[str] = []
        for name in names:
            path = resolve(folder, name)
            if not path:
                return {"ok": False, "reason": f"clip_path_unresolvable:{name}"}
            resolved.append(path)
        from .golden_serial import golden_clip_load

        session = build_generic_clip_session(
            clip_filenames=names,
            clip_type=clip_type,
            folder=folder,
            request_id=request_id,
            volume=volume,
        )
        # The stage reads full paths from the session (same as canonical).
        session.clip_paths = list(resolved)
        clip = await golden_clip_load(session)
        owners = list(getattr(session, "clip_owners", None) or [])
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        return {
            "ok": True,
            "clip": clip,
            "session": session,
            "owners": owners,
            "elapsed_ms": elapsed_ms,
            "reason": "",
        }
    except Exception as exc:  # noqa: BLE001 - fallback contract: never raise
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        return {
            "ok": False,
            "reason": f"{type(exc).__name__}:{str(exc)[:200]}",
            "elapsed_ms": elapsed_ms,
        }


async def compose_generic_clip_load_qd4(
    *,
    clip_filenames: Sequence[str],
    clip_type: str,
    folder: str,
    request_id: str,
    path_resolver: Callable[[str, str], str | None] | None = None,
) -> dict[str, Any]:
    """Load CLIP via the SHARED QD4 demand reader (canonical clean-lane arm).

    Uses the same ``clip_qd_load`` the canonical clean-lane demand path uses
    (imported, never copied).  It is self-contained per call — workers are
    joined before return and it owns no persistent pool — so it is immune
    to the persistent-pool poisoning that fails the M2 singleton
    (``PoolPoisonedError:cancelled dispatcher handoff was not completed``).

    Construction mirrors the native CLIPLoader recipe exactly: the same
    shared ``comfy.sd.load_text_encoder_state_dicts`` delegation with the
    same ``cached_patcher_init`` shape; only the file-read step is fast.
    No manifest pipeline is applied (native loads apply none).  QD owners
    are returned for request-scoped retention; the caller releases them via
    the holder without touching any shared lifecycle.

    Returns the same outcome shape as :func:`compose_generic_clip_load`
    plus ``source_arm="qd4_demand"``.  Never raises.
    """
    started_ns = time.monotonic_ns()
    resolve = path_resolver or _default_path_resolver
    try:
        names = [str(n) for n in (clip_filenames or []) if str(n or "").strip()]
        if not names:
            return {"ok": False, "reason": "clip_filenames_missing",
                    "source_arm": "qd4_demand"}
        if len(names) > 1:
            return {"ok": False, "reason": "qd4_multi_checkpoint_deferred",
                    "source_arm": "qd4_demand"}
        path = resolve(folder, names[0])
        if not path:
            return {"ok": False,
                    "reason": f"clip_path_unresolvable:{names[0]}",
                    "source_arm": "qd4_demand"}
        from .clip_qd_reader import clip_qd_load, qd_config

        cfg = qd_config() or {}
        qd_value = int(cfg.get("qd", 0) or 0)
        block_mib = int(cfg.get("block_mib", 0) or 0)
        launch_policy = str(cfg.get("launch_policy", "") or "")
        if not bool(cfg.get("enabled")):
            return {"ok": False, "reason": "qd4_gate_disabled",
                    "source_arm": "qd4_demand"}
        if qd_value != 4:
            return {"ok": False,
                    "reason": f"qd4_gate_qd_not_4:{qd_value}",
                    "source_arm": "qd4_demand"}
        if block_mib < 1 or not launch_policy:
            return {"ok": False, "reason": "qd4_gate_config_incomplete",
                    "source_arm": "qd4_demand"}
        sd, loader, owner = clip_qd_load(
            path,
            qd=qd_value,
            block_mib=block_mib,
            trace=None,
            launch_policy=launch_policy,
            artifact_path=cfg.get("artifact_path") or None,
        )
        import comfy.sd
        from comfy.utils import convert_old_quants

        # Mirror the native recipe: convert_old_quants runs whenever the
        # (default, empty) model_options carry no custom_operations.  The
        # native path passes REAL safetensors header metadata, which carries
        # _quantization_metadata for scaled-FP8 weights; passing {} skips
        # the .comfy_quant attachment and the constructor rejects raw F8
        # tensors (observed live).  Header-only parse: no second payload
        # read (tensors stay lazy; only the JSON header is touched).
        model_options: dict[str, Any] = {}
        file_metadata: dict[str, Any] = {}
        try:
            if str(path).lower().endswith((".safetensors", ".sft")):
                from safetensors import safe_open as _safe_open

                with _safe_open(path, framework="pt", device="cpu") as _hdr:
                    _meta = _hdr.metadata()
                    if isinstance(_meta, dict):
                        file_metadata = dict(_meta)
        except Exception:
            file_metadata = {}
        sd, _qd_metadata = convert_old_quants(
            sd, model_prefix="", metadata=file_metadata
        )
        clip_type_obj = resolve_clip_type_shared(clip_type)
        try:
            import folder_paths

            embedding_directory = folder_paths.get_folder_paths("embeddings")
        except Exception:
            embedding_directory = None
        clip = comfy.sd.load_text_encoder_state_dicts(
            [sd],
            embedding_directory=embedding_directory,
            clip_type=clip_type_obj,
            model_options=model_options,
        )
        try:
            clip.patcher.cached_patcher_init = (
                comfy.sd.load_clip_model_patcher,
                ([path], embedding_directory, clip_type_obj, model_options),
            )
        except Exception:
            pass
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        owners = [o for o in (loader, owner) if o is not None]
        return {
            "ok": True,
            "clip": clip,
            "session": None,
            "owners": owners,
            "elapsed_ms": elapsed_ms,
            "reason": "",
            "source_arm": "qd4_demand",
        }
    except Exception as exc:  # noqa: BLE001 - fallback contract: never raise
        elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        return {
            "ok": False,
            "reason": f"{type(exc).__name__}:{str(exc)[:200]}",
            "elapsed_ms": elapsed_ms,
            "source_arm": "qd4_demand",
        }


def _cache_entry_for(obj: Any) -> Any | None:
    """Build a CacheEntry shaped exactly like the residency seeder's."""
    try:
        from execution import CacheEntry as _CacheEntry
    except Exception:
        return None
    try:
        outputs_list = [[v] for v in obj] if isinstance(obj, (tuple, list)) else [[obj]]
        return _CacheEntry(ui={}, outputs=outputs_list)
    except Exception:
        return None


async def insert_loader_cache_entry(
    outputs_cache: Any,
    cache_key_set: Any,
    node_id: str,
    obj: Any,
) -> dict[str, str]:
    """Insert one loaded object into the executor output cache (verified).

    Mirrors the residency seeder's insert+verify shape.  Returns a decision
    dict; never raises — failure means the native node simply executes.
    """
    node_id = str(node_id or "")
    try:
        data_key = cache_key_set.get_data_key(node_id) if cache_key_set is not None else None
    except Exception:
        data_key = None
    if data_key is None:
        return {"decision": "cache_key_missing", "node_id": node_id}
    entry = _cache_entry_for(obj)
    if entry is None:
        return {"decision": "cache_insert_failed", "node_id": node_id}
    try:
        await outputs_cache.set(node_id, entry)
        retrieved = await outputs_cache.get(node_id)
    except Exception:
        return {"decision": "cache_insert_failed", "node_id": node_id}
    if retrieved is None:
        return {"decision": "cache_insert_failed", "node_id": node_id}
    return {"decision": "seeded", "node_id": node_id}


async def compose_loaders_for_workflow(
    *,
    workflow: Mapping[str, Any],
    outputs_cache: Any,
    cache_key_set: Any,
    holder: GenericLoaderHolder,
    request_id: str,
    trace_emit: Callable[..., Any] | None = None,
    path_resolver: Callable[[str, str], str | None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Attempt shared-core loads for eligible loader nodes, seed the cache.

    Runs AFTER the executor's set_prompt (cache keys exist).  For each
    CLIPLoader node: skip when already cached, classify, compose via the
    shared core, insert on success.  Every outcome is recorded per node;
    native execution always remains the fallback.  Never raises.
    """
    results: dict[str, dict[str, Any]] = {}
    seen_paths: dict[str, Any] = {}

    def _emit(name: str, **fields: Any) -> None:
        try:
            if callable(trace_emit):
                trace_emit(name, phase="execution", metadata=dict(fields))
        except Exception:
            pass

    try:
        nodes = workflow.items() if isinstance(workflow, Mapping) else []
    except Exception:
        return results
    for raw_nid, node in nodes:
        try:
            node_id = str(raw_nid or "")
            if not node_id or not isinstance(node, Mapping):
                continue
            class_type = str(node.get("class_type", "") or "")
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                inputs = {}
            classification = classify_loader_node(class_type, inputs)
            if not classification.get("supported"):
                if class_type in _KNOWN_LOADER_CLASSES:
                    results[node_id] = {
                        "requested": "shared_core",
                        "actual": "native",
                        "reason": str(classification.get("reason") or "unsupported"),
                    }
                continue
            # Skip nodes the residency/snapshot path (or an earlier node)
            # already satisfied - never reload covered work.
            try:
                existing = await outputs_cache.get(node_id)
            except Exception:
                existing = None
            if existing is not None:
                results[node_id] = {
                    "requested": "shared_core",
                    "actual": "cache_hit",
                    "reason": "already_cached",
                }
                continue
            clip_name = str(classification.get("clip_name") or "")
            clip_type = str(classification.get("clip_type") or "stable_diffusion")
            path_key = f"text_encoders/{clip_name}"
            if path_key in seen_paths:
                obj = seen_paths[path_key]
                outcome: dict[str, Any] = {
                    "ok": True, "clip": obj, "session": None,
                    "owners": [], "elapsed_ms": 0.0, "reason": "dedup_within_request",
                }
            else:
                # QD4 demand first (self-contained, pool-poison immune),
                # M2 singleton second (healthy pool used when available).
                outcome = await compose_generic_clip_load_qd4(
                    clip_filenames=[clip_name],
                    clip_type=clip_type,
                    folder="text_encoders",
                    request_id=request_id,
                    path_resolver=path_resolver,
                )
                if not outcome.get("ok"):
                    qd4_reason = str(outcome.get("reason") or "qd4_failed")
                    m2_outcome = await compose_generic_clip_load(
                        clip_filenames=[clip_name],
                        clip_type=clip_type,
                        folder="text_encoders",
                        request_id=request_id,
                        path_resolver=path_resolver,
                    )
                    m2_outcome.setdefault("source_arm", "m2_transport")
                    if not m2_outcome.get("ok"):
                        m2_outcome["reason"] = (
                            f"{qd4_reason}|{m2_outcome.get('reason')}"
                        )
                    outcome = m2_outcome
                if outcome.get("ok") and outcome.get("clip") is not None:
                    seen_paths[path_key] = outcome["clip"]
            if not outcome.get("ok") or outcome.get("clip") is None:
                results[node_id] = {
                    "requested": "shared_core",
                    "actual": "native",
                    "reason": str(outcome.get("reason") or "compose_failed"),
                    "elapsed_ms": outcome.get("elapsed_ms", 0.0),
                    "source_arm": str(outcome.get("source_arm") or "unknown"),
                }
                _emit("generic_loader_composition", node_id=node_id,
                      role="clip", requested="shared_core", actual="native",
                      reason=str(outcome.get("reason") or "compose_failed"),
                      source_arm=str(outcome.get("source_arm") or "unknown"))
                continue
            if outcome.get("session") is not None:
                holder.retain(outcome.get("session"), outcome.get("owners"))
            decision = await insert_loader_cache_entry(
                outputs_cache, cache_key_set, node_id, outcome["clip"],
            )
            if decision.get("decision") == "seeded":
                results[node_id] = {
                    "requested": "shared_core",
                    "actual": "shared_core",
                    "reason": "",
                    "elapsed_ms": outcome.get("elapsed_ms", 0.0),
                    "source_arm": str(outcome.get("source_arm") or "unknown"),
                }
            else:
                results[node_id] = {
                    "requested": "shared_core",
                    "actual": "native",
                    "reason": str(decision.get("decision") or "cache_insert_failed"),
                    "elapsed_ms": outcome.get("elapsed_ms", 0.0),
                    "source_arm": str(outcome.get("source_arm") or "unknown"),
                }
            _emit("generic_loader_composition", node_id=node_id,
                  role="clip", requested="shared_core",
                  actual=results[node_id]["actual"],
                  reason=results[node_id]["reason"],
                  source_arm=str(outcome.get("source_arm") or "unknown"))
        except Exception as exc:  # noqa: BLE001 - per-node isolation
            try:
                results[str(raw_nid or "?")] = {
                    "requested": "shared_core",
                    "actual": "native",
                    "reason": f"{type(exc).__name__}:{str(exc)[:120]}",
                }
            except Exception:
                pass
    return results


def install_generic_loader_hook(
    executor: Any,
    workflow: Mapping[str, Any] | None,
    holder: GenericLoaderHolder,
    trace_emit: Callable[..., Any] | None,
    request_id: str,
) -> Callable[[], None] | None:
    """Wrap the executor output-cache ``set_prompt`` with generic composition.

    The wrapper calls through to whatever ``set_prompt`` is currently
    installed (the snapshot seeder's wrapper or the original), so snapshot
    residency keeps priority, then attempts shared-core loads for loader
    nodes the cache still misses.  Returns a restore callable (never None
    when installed).  Installation failure returns None and leaves the
    executor untouched — native behavior is always the fallback.
    """
    try:
        caches = getattr(executor, "caches", None)
        outputs_cache = getattr(caches, "outputs", None) if caches is not None else None
        original_set_prompt = getattr(outputs_cache, "set_prompt", None)
        if not callable(original_set_prompt):
            return None
        workflow_snapshot = dict(workflow) if isinstance(workflow, Mapping) else {}

        async def generic_set_prompt(*args: Any, **kwargs: Any) -> Any:
            result = await original_set_prompt(*args, **kwargs)
            try:
                await compose_loaders_for_workflow(
                    workflow=workflow_snapshot,
                    outputs_cache=outputs_cache,
                    cache_key_set=getattr(outputs_cache, "cache_key_set", None),
                    holder=holder,
                    request_id=str(request_id or ""),
                    trace_emit=trace_emit,
                )
            except Exception:
                pass
            return result

        outputs_cache.set_prompt = generic_set_prompt  # type: ignore[method-assign]

        def _restore() -> None:
            try:
                if getattr(outputs_cache, "set_prompt", None) is generic_set_prompt:
                    outputs_cache.set_prompt = original_set_prompt
            except Exception:
                pass

        return _restore
    except Exception:
        return None
