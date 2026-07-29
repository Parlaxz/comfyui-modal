"""Snapshot-safe runtime bootstrap and restore lifecycle.

Lane B extensions:
  - Authoritative pre-scan generation identity freeze/reuse
  - Sage patch snapshot identity retention after real CUDA init
  - Snapshot-memory validation certificate with Volume fallback
  - Reachability-based graph trimming report (delegates to production_workflow)
"""

from __future__ import annotations

import configparser
import contextlib
import logging
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from .contracts import SnapshotExecutionSeed
from .runtime_executor import _restore_isolation_scope
from .trace import RuntimeTrace

_log = logging.getLogger(__name__)

# ── Sage snapshot identity constants ────────────────────────────────────
COMFYMODAL_SAGE_PATCH_VERSION: str = "comfymodal-sage-v1"
"""Repository-owned sentinel for Sage Python monkeypatch identification.

Set during CPU-snapshot-safe Sage pre-discovery. Verified at restore time
after CUDA init to decide whether full Sage discovery can be skipped.
Stable within this commit of comfyui-modal. Never contains user data,
CUDA handles, tensor objects, or model state.
"""

SNAPSHOT_SAGE_POLICY_VERSION: str = "1"
"""Snapshot-time Sage policy version. Bump when Sage integration changes."""


def _discover_and_patch_sage_cpu_snapshot(
    *,
    custom_node_generation: str = "",
    deployment_combined_hash: str = "",
    baked_cuda_available: bool = False,
) -> dict[str, str]:
    """CPU-snapshot-safe Sage pre-discovery.

    Imports the exact Sage integration, discovers the target function once,
    and installs a Python monkeypatch with a stable COMFYMODAL_SAGE_PATCH_VERSION
    sentinel. No CUDA/GPU/tensor/kernel/inference access.

    Returns a dict with snapshot identity fields:
      module_name, module_file_or_source_identity, target_attribute_path,
      patched_callable_qualname, patch_version, sage_mode, policy_version,
      custom_node_generation, deployment_combined_hash
    """
    result: dict[str, str] = {
        "module_name": "",
        "module_file_or_source_identity": "",
        "target_attribute_path": "",
        "patched_callable_qualname": "",
        "patch_version": COMFYMODAL_SAGE_PATCH_VERSION,
        "sage_mode": "",
        "policy_version": SNAPSHOT_SAGE_POLICY_VERSION,
        "custom_node_generation": custom_node_generation,
        "deployment_combined_hash": deployment_combined_hash,
    }
    try:
        # Discover Sage integration via the known production path:
        # ComfyUI KJNodes model_optimization_nodes.py and api._apply_sage_attention_policy.
        # The _apply_sage_attention_policy method iterates sys.modules looking for
        # model_optimization_nodes.py and calls patch_kjnodes_get_sage_func().
        # We do the same CPU-snapshot-safe discovery here without CUDA/tensor access.
        target = None
        target_mod = None
        target_attr_path = ""
        for mod in list(sys.modules.values()):
            file_name = getattr(mod, "__file__", "") or ""
            if file_name.endswith("model_optimization_nodes.py"):
                target_mod = mod
                target = getattr(mod, "get_sage_func", None)
                if callable(target):
                    target_attr_path = "get_sage_func"
                break

        if target_mod is not None:
            result["module_name"] = getattr(target_mod, "__name__", "")
            source_file = getattr(target_mod, "__file__", "")
            if source_file:
                import hashlib
                result["module_file_or_source_identity"] = hashlib.sha256(
                    source_file.encode("utf-8")
                ).hexdigest()[:16]

        if target is not None:
            integration = sys.modules.get("comfyapp")
            patcher = getattr(integration, "patch_kjnodes_get_sage_func", None)
            if callable(patcher):
                patcher(target_mod, baked_cuda_available=baked_cuda_available)
                target = getattr(target_mod, "get_sage_func", target)
            # Record qualified name
            if hasattr(target, "__qualname__"):
                result["patched_callable_qualname"] = target.__qualname__
            elif hasattr(target, "__name__"):
                result["patched_callable_qualname"] = target.__name__

            # Install the sentinel on the callable
            setattr(target, "_comfymodal_sage_patch_version", COMFYMODAL_SAGE_PATCH_VERSION)
            result["target_attribute_path"] = target_attr_path

        if target_mod is not None:
            # Mark the module with the sentinel too
            setattr(target_mod, "_comfymodal_sage_patch_version", COMFYMODAL_SAGE_PATCH_VERSION)

        if target is not None:
            result["sage_mode"] = "patched_at_snapshot"
        elif target_mod is not None:
            result["sage_mode"] = "module_found_no_target"
        else:
            result["sage_mode"] = "module_not_found"

        print(
            f"[v2.sage_snapshot] action=discover_and_patch "
            f"module={result['module_name']} "
            f"target={result['patched_callable_qualname']} "
            f"mode={result['sage_mode']} "
            f"version={COMFYMODAL_SAGE_PATCH_VERSION}",
            flush=True,
        )
    except Exception as exc:
        result["sage_mode"] = f"error:{str(exc)[:60]}"
    return result


def _verify_sage_snapshot_identity(
    *,
    snapshot_identity: dict[str, str],
    current_custom_node_generation: str = "",
    current_deployment_combined_hash: str = "",
) -> bool:
    """Verify that the in-memory Sage patch installed at snapshot time is
    still present and intact.  Returns True when the sentinel, version,
    and identity fields all match — meaning full Sage discovery can be
    skipped.  No CUDA/GPU access.
    """
    # Check the patched callable's sentinel
    mod_name = snapshot_identity.get("module_name", "")
    if not mod_name:
        return False
    mod = sys.modules.get(mod_name)
    if mod is None:
        return False
    # Check module-level sentinel
    if getattr(mod, "_comfymodal_sage_patch_version", "") != COMFYMODAL_SAGE_PATCH_VERSION:
        return False
    # Check target callable sentinel
    target_attr_path = snapshot_identity.get("target_attribute_path", "")
    if target_attr_path:
        parts = target_attr_path.split(".")
        obj = mod
        for part in parts:
            obj = getattr(obj, part, None)
            if obj is None:
                return False
        if getattr(obj, "_comfymodal_sage_patch_version", "") != COMFYMODAL_SAGE_PATCH_VERSION:
            return False
    else:
        # Fallback: check any callable on the module with the sentinel
        found = False
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name, None)
            if callable(attr) and getattr(attr, "_comfymodal_sage_patch_version", "") == COMFYMODAL_SAGE_PATCH_VERSION:
                found = True
                break
        if not found:
            return False
    # Check custom-node generation and deployment hash if provided
    if snapshot_identity.get("custom_node_generation") and current_custom_node_generation:
        if snapshot_identity["custom_node_generation"] != current_custom_node_generation:
            return False
    if snapshot_identity.get("deployment_combined_hash") and current_deployment_combined_hash:
        if snapshot_identity["deployment_combined_hash"] != current_deployment_combined_hash:
            return False
    # Check patch version
    if snapshot_identity.get("patch_version") != COMFYMODAL_SAGE_PATCH_VERSION:
        return False
    return True


# Three known ComfyUI-Manager config.ini locations (relative to comfyui_root).
_MANAGER_CONFIG_PATHS: tuple[str, ...] = (
    "user/__manager/config.ini",
    "user/default/__manager/config.ini",
    "user/default/ComfyUI-Manager/config.ini",
)


@dataclass(frozen=True)
class BootstrapConfig:
    comfyui_root: str = "/root/comfy/ComfyUI"
    models_path: str = "/root/comfy/ComfyUI/models"
    custom_nodes_path: str = "/root/comfy/ComfyUI/custom_nodes"
    min_containers: int = 0
    scaledown_window: int = 4
    manager_offline: bool = True
    install_requirements_on_startup: bool = False
    # Lane B — path for persisting pre-scan generation record
    prescan_record_path: str = ""


@dataclass
class BootstrapState:
    startup_started_at: float = 0.0
    startup_completed_at: float = 0.0
    restore_started_at: float = 0.0
    restore_completed_at: float = 0.0
    backend: str = ""
    cuda: dict[str, Any] = field(default_factory=dict)
    runtime_generation: str = ""
    custom_node_generation: str = ""
    errors: list[str] = field(default_factory=list)
    # Phase 3 — per-stage durations (ms) from trace events
    stage_durations: dict[str, float] = field(default_factory=dict)
    # Phase 0 — identity/environment metadata captured at lifecycle entry
    modal_task_id: str = ""
    modal_image_id: str = ""
    modal_cloud_provider: str = ""
    modal_region: str = ""
    # SageAttention policy observability
    sage_mode: str = ""
    sage_reason: str = ""
    sage_identity_captured: bool = False
    # Lane B — snapshot Sage identity (frozen at CPU-snapshot time, verified at restore)
    snapshot_sage_identity: dict[str, str] = field(default_factory=dict)
    # Lane B — snapshot custom-node identity (frozen at startup, used at restore)
    snapshot_custom_node_generation: str = ""
    snapshot_custom_node_source: str = ""
    snapshot_custom_node_schema: str = "0"
    deployment_combined_hash: str = ""
    # Lane B — snapshot-memory validation certificate
    snapshot_certificate: dict[str, Any] = field(default_factory=dict)
    snapshot_cert_valid: bool = False
    # Lane B — graph trimming evidence
    graph_removable_node_ids: list[str] = field(default_factory=list)
    graph_trimming_possible: bool = False
    # Lane B — SnapshotExecutionSeed (deterministic immutable cache seed)
    snapshot_execution_seed: SnapshotExecutionSeed | None = None
    snapshot_loader_outputs: dict[str, Any] = field(default_factory=dict)
    snapshot_model_identities: dict[str, str] = field(default_factory=dict)
    snapshot_seed_built: bool = False
    # -- Legacy prescan identity aliases (backward-compatible diagnostics) --
    prescan_runtime_generation: str = ""
    prescan_custom_node_generation: str = ""
    prescan_record_path: str = ""
    # -- CacheDiT restore preparation state --
    _cachedit_unet_identity: str = ""
    _cachedit_workflow_hash: str = ""
    _cachedit_inputs_prepared: bool = False
    # -- RES4LYF restore preparation state --
    _res4lyf_static_prepared: tuple = ()
    # -- Dependency preflight identity (captured at startup, checked at request) --
    dependency_manifest_identity: str = ""
    dependency_manifest_schema_version: str = "0"
    dependency_manifest_workflow_hash: str = ""
    dependency_manifest_custom_node_generation: str = ""
    dependency_manifest_deployment_hash: str = ""
    dependency_manifest_repair_mode: str = ""
    # -- Dependency preflight counters (actual expensive calls, not skips) --
    dependency_scan_call_count: int = 0
    dependency_validation_call_count: int = 0
    dependency_manifest_build_call_count: int = 0

    def has_prescan_identity(self) -> bool:
        """Backward-compatible diagnostic — checks frozen prescan identity."""
        return bool(self.prescan_custom_node_generation)

    def freeze_prescan_identity(self, *, record_path: str = "") -> None:
        """Backward-compatible diagnostic — freezes current generations
        into legacy prescan identity fields.
        """
        self.prescan_runtime_generation = self.runtime_generation
        self.prescan_custom_node_generation = self.custom_node_generation
        self.prescan_record_path = str(record_path)

    def build_snapshot_execution_seed(
        self,
        *,
        workflow_hash: str = "",
        output_node_ids: Sequence[str] = (),
        loader_node_ids: Sequence[str] = (),
        loader_cache_signatures: Sequence[dict[str, Any]] = (),
        sampler_node_ids: Sequence[str] = (),
        sampler_static_inputs: Sequence[dict[str, Any]] = (),
        custom_node_generation: str = "",
        deployment_combined_hash: str = "",
    ) -> SnapshotExecutionSeed:
        """Build and store a deterministic SnapshotExecutionSeed.

        Contains only identity fields — no outputs, latents, or random state.
        Used to seed the live executor.caches with snapshot-time model objects.
        """
        seed = SnapshotExecutionSeed(
            workflow_hash=str(workflow_hash),
            output_node_ids=tuple(str(i) for i in output_node_ids),
            loader_node_ids=tuple(str(i) for i in loader_node_ids),
            loader_cache_signatures=tuple(dict(item) for item in loader_cache_signatures),
            sampler_node_ids=tuple(str(i) for i in sampler_node_ids),
            sampler_static_inputs=tuple(dict(item) for item in sampler_static_inputs),
            custom_node_generation=str(custom_node_generation),
            deployment_combined_hash=str(deployment_combined_hash),
        )
        self.snapshot_execution_seed = seed
        self.snapshot_seed_built = True
        return seed

    def freeze_custom_node_identity(
        self, *,
        custom_node_generation: str = "",
        generation_source: str = "",
        schema_version: str = "0",
        deployment_combined_hash: str = "",
    ) -> None:
        """Freeze the custom-node identity from observed values at snapshot time."""
        self.snapshot_custom_node_generation = str(custom_node_generation)
        self.snapshot_custom_node_source = str(generation_source)
        self.snapshot_custom_node_schema = str(schema_version)
        self.deployment_combined_hash = str(deployment_combined_hash)

    def has_snapshot_custom_node_identity(self) -> bool:
        """True when a snapshot custom-node generation identity is present."""
        return bool(self.snapshot_custom_node_generation)

    def sage_identity(self) -> dict[str, str]:
        """Return frozen Sage identity for certificate creation."""
        return {
            "sage_mode": self.sage_mode,
            "sage_reason": self.sage_reason,
        }

    def set_snapshot_certificate(self, cert: dict[str, Any]) -> None:
        self.snapshot_certificate = dict(cert)
        # Validate inline - V2 certs use direct identity comparison
        # (cert_identity vs recomputed from identity_components).
        # V1/legacy certs fall back to the generic optimizer validator.
        try:
            sv = cert.get("schema_version")
            if sv == 2:
                # V2 validation: recompute identity from components
                import hashlib
                stored_identity = str(cert.get("cert_identity", "") or cert.get("identity", ""))
                components = cert.get("identity_components", {})
                if isinstance(components, dict) and stored_identity:
                    h = hashlib.sha256()
                    h.update(f"cert_schema={components.get('schema_version', '2')}\n".encode())
                    h.update(f"workflow_hash={components.get('workflow_hash', '')}\n".encode())
                    h.update(f"deployment_hash={components.get('deployment_hash', '')}\n".encode())
                    h.update(f"repair_mode={components.get('repair_mode', '')}\n".encode())
                    h.update(f"custom_nodes_generation={components.get('custom_nodes_generation', '')}\n".encode())
                    computed = h.hexdigest()
                    self.snapshot_cert_valid = (stored_identity == computed)
                else:
                    self.snapshot_cert_valid = False
            else:
                from optimizations import validate_snapshot_certificate
                result = validate_snapshot_certificate(cert)
                self.snapshot_cert_valid = bool(result.get("valid"))
        except Exception:
            self.snapshot_cert_valid = False

    def set_graph_trimming_evidence(
        self, *, removable_ids: list[str], trimming_possible: bool,
    ) -> None:
        self.graph_removable_node_ids = list(removable_ids)
        self.graph_trimming_possible = bool(trimming_possible)

    async def seed_loader_cache_signatures(
        self,
        executor: Any,
        *,
        loader_node_ids: Sequence[str] = (),
        loader_node_class_types: dict[str, str] | None = None,
        loader_outputs: dict[str, Any] | None = None,
        request_model_key: dict[str, Any] | None = None,
        snapshot_model_key: dict[str, Any] | None = None,
        request_model_spec: dict[str, Any] | None = None,
        snapshot_model_spec: dict[str, Any] | None = None,
        workflow_hash: str = "",
        custom_node_generation: str = "",
        deployment_combined_hash: str = "",
        allow_cache: bool = True,
    ) -> dict[str, dict[str, str]]:
        """Seed immutable loader outputs into executor.caches.outputs.

        Every candidate loader node gets exactly one outcome dict with keys:
          decision    — ``seeded`` | ``missing_snapshot_output`` | ``identity_mismatch`` | ``unsupported``
          role        — ``unet`` | ``clip`` | ``vae`` | ``checkpoint`` | ``?``
          expected_identity  — short hash of request role identity (or ``""``)
          actual_identity    — short hash of snapshot role identity (or ``""``)
          mismatch_fields    — comma-separated differing fields (or ``"none"``)

        Changes from prior gating:
          - No global rejection on workflow_hash, model_key, model_spec,
            custom_node_generation, or deployment_combined_hash.
          - Each loader role is independently compared using canonical
            per-role identity (``compute_loader_role_identity``).
          - VAE always reports ``missing_snapshot_output`` (snapshot lacks VAE).
          - CheckpointLoader/CheckpointLoaderSimple report ``unsupported``
            unless safely role-separated.
          - UNET and CLIP report ``identity_mismatch`` with exact mismatched
            fields when request vs. snapshot role identity differs.
        """
        import hashlib
        from .contracts import (
            compute_loader_role_identity,
            find_role_identity_mismatch_fields,
        )

        results: dict[str, dict[str, str]] = {}
        _unsupported_decision = lambda mf: {"decision": "unsupported", "role": "?", "expected_identity": "", "actual_identity": "", "mismatch_fields": mf}
        if not allow_cache:
            return {str(nid): _unsupported_decision("cache_insert_failed") for nid in loader_node_ids}
        caches = getattr(executor, "caches", None)
        if caches is None:
            return {str(nid): _unsupported_decision("cache_insert_failed") for nid in loader_node_ids}
        outputs_cache = getattr(caches, "outputs", None)
        if outputs_cache is None:
            return {str(nid): _unsupported_decision("cache_insert_failed") for nid in loader_node_ids}
        # set_prompt must have already run — verify via cache_key_set
        cache_key_set = getattr(outputs_cache, "cache_key_set", None)
        if cache_key_set is None or not getattr(outputs_cache, "initialized", False):
            return {str(nid): _unsupported_decision("cache_key_missing") for nid in loader_node_ids}

        seed = self.snapshot_execution_seed
        if not seed:
            return {str(nid): {"decision": "missing_snapshot_output", "role": "?", "expected_identity": "", "actual_identity": "", "mismatch_fields": "none"} for nid in loader_node_ids}

        loader_outputs = loader_outputs or self.snapshot_loader_outputs
        _class_types = dict(loader_node_class_types or {})

        # ── Allowed loader types ────────────────────────────────────────
        _ALLOWED_CLASS_TYPES: set[str] = {
            "UNETLoader",
            "CLIPLoader",
            "DualCLIPLoader",
            "VAELoader",
            "CheckpointLoader",
            "CheckpointLoaderSimple",
        }

        # ── Role mapping ────────────────────────────────────────────────
        _ROLE_MAP: dict[str, str] = {
            "UNETLoader": "unet",
            "CLIPLoader": "clip",
            "DualCLIPLoader": "clip",
            "VAELoader": "vae",
            "CheckpointLoader": "checkpoint",
            "CheckpointLoaderSimple": "checkpoint",
        }

        # ── Build per-role canonical identities ─────────────────────────
        # Compute once per role; all nodes of the same role share the same
        # identity comparison.
        _snap_cn_gen = self.snapshot_custom_node_generation or ""
        _snap_dep_hash = self.deployment_combined_hash or ""
        # Static patch hash: use explicit "none" when no patch metadata exists
        # in the cached snapshot output (general V2 fast path without CacheDiT/RES4LYF).
        _req_static_patch = "none"
        _snap_static_patch = "none"
        # If static patches were populated in the snapshot output, use that identity;
        # otherwise the canonical "none" ensures no false-positive patch-matching.
        _sp = self.snapshot_execution_seed
        if _sp is not None:
            _snap_static_patch = getattr(_sp, "static_model_patches_hash", "") or "none"

        _req_role_identity: dict[str, dict[str, str]] = {}
        _snap_role_identity: dict[str, dict[str, str]] = {}
        for _role in ("unet", "clip", "vae"):
            _req_role_identity[_role] = compute_loader_role_identity(
                _role, request_model_spec or {},
                custom_node_generation=custom_node_generation,
                deployment_combined_hash=deployment_combined_hash,
                static_model_patches_hash=_req_static_patch,
            )
            _snap_role_identity[_role] = compute_loader_role_identity(
                _role, snapshot_model_spec or {},
                custom_node_generation=_snap_cn_gen,
                deployment_combined_hash=_snap_dep_hash,
                static_model_patches_hash=_snap_static_patch,
            )

        try:
            from execution import CacheEntry as _CacheEntry
        except Exception:
            _CacheEntry = None

        for _raw_nid in loader_node_ids:
            node_id = str(_raw_nid)
            _ct = _class_types.get(node_id, "")
            _role = _ROLE_MAP.get(_ct, "?")

            # 1. Check class type is allowed
            if _ct not in _ALLOWED_CLASS_TYPES:
                results[node_id] = {
                    "decision": "unsupported",
                    "role": _role,
                    "expected_identity": "",
                    "actual_identity": "",
                    "mismatch_fields": "none",
                }
                continue

            # 2. Checkpoint loaders: unsupported unless safely role-separated
            if _role == "checkpoint":
                results[node_id] = {
                    "decision": "unsupported",
                    "role": _role,
                    "expected_identity": "",
                    "actual_identity": "",
                    "mismatch_fields": "none",
                }
                continue

            # 3. VAE: always missing_snapshot_output (snapshot has no VAE)
            if _role == "vae":
                results[node_id] = {
                    "decision": "missing_snapshot_output",
                    "role": _role,
                    "expected_identity": "",
                    "actual_identity": "",
                    "mismatch_fields": "none",
                }
                continue

            # 4. Check output availability
            _out = loader_outputs.get(node_id)
            if _out is None:
                # Clear any stale cache entry for this node
                try:
                    await outputs_cache.delete(node_id)
                except Exception:
                    pass
                results[node_id] = {
                    "decision": "missing_snapshot_output",
                    "role": _role,
                    "expected_identity": "",
                    "actual_identity": "",
                    "mismatch_fields": "none",
                }
                continue

            # 5. Per-role identity comparison (UNET / CLIP)
            _req_id = _req_role_identity.get(_role, {})
            _snap_id = _snap_role_identity.get(_role, {})
            _req_hash = _req_id.get("stable_id", "")
            _snap_hash = _snap_id.get("stable_id", "")

            # Short hashes for diagnostics
            _req_short = _req_hash[:16] if _req_hash else ""
            _snap_short = _snap_hash[:16] if _snap_hash else ""

            if _req_hash and _snap_hash and _req_hash != _snap_hash:
                # Clear any stale cache entry for this node before reporting mismatch
                try:
                    await outputs_cache.delete(node_id)
                except Exception:
                    pass
                _mismatch_fields = find_role_identity_mismatch_fields(_req_id, _snap_id)
                results[node_id] = {
                    "decision": "identity_mismatch",
                    "role": _role,
                    "expected_identity": _req_short,
                    "actual_identity": _snap_short,
                    "mismatch_fields": ",".join(_mismatch_fields) if _mismatch_fields else "unknown",
                }
                continue

            # 6. Cache key must already exist (set_prompt already ran)
            _data_key = cache_key_set.get_data_key(node_id)
            if _data_key is None:
                results[node_id] = {
                    "decision": "unsupported",
                    "role": _role,
                    "expected_identity": _req_short,
                    "actual_identity": _snap_short,
                    "mismatch_fields": "cache_key_missing",
                }
                continue

            # 7. Insert into outputs cache
            try:
                _outputs_list = [[v] for v in _out] if isinstance(_out, (tuple, list)) else [[_out]]
                _entry_obj = (
                    _CacheEntry(ui={}, outputs=_outputs_list)
                    if _CacheEntry is not None
                    else None
                )
                if _entry_obj is None:
                    results[node_id] = {
                        "decision": "unsupported",
                        "role": _role,
                        "expected_identity": _req_short,
                        "actual_identity": _snap_short,
                        "mismatch_fields": "cache_insert_failed",
                    }
                    continue
                await outputs_cache.set(node_id, _entry_obj)
                # Verify insertion — immediate get
                _retrieved = await outputs_cache.get(node_id)
                if _retrieved is None:
                    results[node_id] = {
                        "decision": "unsupported",
                        "role": _role,
                        "expected_identity": _req_short,
                        "actual_identity": _snap_short,
                        "mismatch_fields": "cache_insert_failed",
                    }
                    continue
                _digest = hashlib.sha256(str(_data_key).encode("utf-8")).hexdigest()[:16]
                results[node_id] = {
                    "decision": "seeded",
                    "role": _role,
                    "expected_identity": _req_short,
                    "actual_identity": _snap_short,
                    "mismatch_fields": "none",
                }
            except Exception:
                results[node_id] = {
                    "decision": "unsupported",
                    "role": _role,
                    "expected_identity": _req_short,
                    "actual_identity": _snap_short,
                    "mismatch_fields": "cache_insert_failed",
                }

        return results

    def _restore_cachedit_prepare(
        self,
        *,
        unet: Any = None,
        workflow_inputs: dict[str, Any] | None = None,
        workflow_hash: str = "",
    ) -> dict[str, Any]:
        """Resolve CacheDiT_Model_Optimizer dynamically, invoke its declared
        FUNCTION exactly once (no TypeError retry), passing only
        scalar/static inputs (rejecting connection-shaped list/tuple values),
        plus ``model=restored_snapshot_unet``, and return patched model +
        diagnostics.

        Uses FUNCTION attribute on the node class.  Single invocation via
        instantiated node instance for bound-method compatibility.  Filters
        ``workflow_inputs`` to keys matching the node's declared INPUT_TYPES
        whose values are not connection tuples (``(node_id, output_index)``).
        Returns ``patched_model`` for caller to replace active UNET.
        """
        def _is_connection_link(val: Any) -> bool:
            """Detect ComfyUI-style connection tuples ``(node_id, output_index)``."""
            return (
                isinstance(val, (tuple, list))
                and len(val) == 2
                and isinstance(val[0], (str, int))
                and isinstance(val[1], int)
            )

        results: dict[str, Any] = {"ok": False, "patched_model": None}
        try:
            import nodes as _cd_nodes
            _mappings = getattr(_cd_nodes, "NODE_CLASS_MAPPINGS", {})
            _cachedit_cls = _mappings.get("CacheDiT_Model_Optimizer")
            if _cachedit_cls is None:
                results["error"] = "CacheDiT_Model_Optimizer node class not found"
                return results
            # Resolve FUNCTION name dynamically from the node class
            _func_name = getattr(_cachedit_cls, "FUNCTION", "optimize")
            _fn = getattr(_cachedit_cls, _func_name, None)
            if _fn is None:
                results["error"] = (
                    f"CacheDiT_Model_Optimizer has no FUNCTION {_func_name!r}"
                )
                return results
            # Gather declared scalar/static input names from INPUT_TYPES
            _declared: set[str] = set()
            try:
                _it = _cachedit_cls.INPUT_TYPES()
                for _cat in ("required", "optional"):
                    for _k in (_it.get(_cat, {}) if isinstance(_it, dict) else ()):
                        _declared.add(str(_k))
            except Exception:
                pass  # fall back to no filter — all non-connection values pass
            # Build scalar/static-only inputs (no graph model key, no connections)
            _inputs: dict[str, Any] = {}
            for _k, _v in (workflow_inputs or {}).items():
                if _k == "model":
                    continue  # will be passed explicitly
                if _is_connection_link(_v):
                    continue  # reject connection-shaped values
                # If declared set is non-empty, only accept matching keys
                if _declared and _k not in _declared:
                    continue
                _inputs[_k] = _v
            # Instantiate node and invoke FUNCTION once as ComfyUI does
            _instance = _cachedit_cls()
            _raw_output = _fn(_instance, model=unet, **_inputs)
            # RETURN_TYPES = ("MODEL",) — first output is the patched model
            if isinstance(_raw_output, (list, tuple)) and len(_raw_output) > 0:
                _patched_model = _raw_output[0]
            else:
                _patched_model = _raw_output
            # Mark identity/workflow hash/inputs prepared
            _transformer = getattr(getattr(unet, "model", None), "diffusion_model", None)
            self._cachedit_unet_identity = str(
                getattr(_transformer, "_cache_dit_identity", str(id(unet)))
            )
            self._cachedit_workflow_hash = workflow_hash
            self._cachedit_inputs_prepared = True
            results["cache_dit_applied"] = True
            results["patched_model"] = _patched_model
            results["unet_identity"] = self._cachedit_unet_identity
            results["workflow_hash"] = workflow_hash[:16] if workflow_hash else ""
            results["ok"] = True
        except Exception as exc:
            results["error"] = str(exc)[:120]
        return results

    def _restore_res4lyf_prepare(
        self,
        *,
        sampler_node_inputs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Extract static RES4LYF (ClownsharKSampler_Beta) inputs excluding
        connection-shaped dynamic values, invoke the exact ExtraOptions parser
        used by ClownsharKSampler_Beta.main (resolved through its module
        globals, never via a hardcoded import path), and cache an immutable
        prepared record per sampler.

        Zero sampler nodes → ``ok=0`` with ``reason=no_sampler_node``.
        Parser failure never swallowed — propagates as error.

        Returned ``prepared_records`` is a list of dicts each containing:
          node_id, raw_extra_options (str), parser (ExtraOptions instance
          when safe for read-only reuse, else None), static_inputs (frozen
          dict).  Caller keys by workflow hash for identity comparison.

        Returns diagnostics dict with ``ok``, ``reason``,
        ``res4lyf_static_prepared``, ``prepared_records``, ``sampler_nodes``,
        and optional ``parser_import_warning`` if exact parser could not be
        resolved from node module.
        """
        def _is_connection_link(val: Any) -> bool:
            """Detect ComfyUI-style connection tuples ``(node_id, output_index)``."""
            return (
                isinstance(val, (tuple, list))
                and len(val) == 2
                and isinstance(val[0], (str, int))
                and isinstance(val[1], int)
            )

        results: dict[str, Any] = {"ok": False, "res4lyf_static_prepared": False}
        try:
            if not sampler_node_inputs:
                results["reason"] = "no_sampler_node"
                results["ok"] = False
                return results

            # Determine exact ExtraOptions constructor from the actual
            # ClownsharKSampler_Beta.main module globals — NOT by assuming
            # an import package name like "RES4LYF.helper".
            _ExtraOptions = None
            _parser_source = ""
            try:
                import nodes as _r4_nodes
                _r4_cls = getattr(_r4_nodes, "NODE_CLASS_MAPPINGS", {}).get(
                    "ClownsharKSampler_Beta"
                )
                if _r4_cls is not None:
                    _mod_name = getattr(_r4_cls, "__module__", "")
                    if _mod_name:
                        import importlib
                        _r4_mod = importlib.import_module(_mod_name)
                        _ExtraOptions = getattr(_r4_mod, "ExtraOptions", None)
                        if _ExtraOptions is not None:
                            _parser_source = f"module={_mod_name}.ExtraOptions"
            except Exception:
                pass

            if _ExtraOptions is None:
                results["parser_import_warning"] = (
                    "ExtraOptions could not be resolved from "
                    "ClownsharKSampler_Beta module — parser reuse unavailable"
                )

            _prepared_records: list[dict[str, Any]] = []
            for _entry in sampler_node_inputs:
                _node_id = _entry.get("node_id", "")
                _inputs = dict(_entry.get("inputs", {}))

                # Exclude runtime-varying and connection-shaped inputs
                _exclude_prefixes = (
                    "seed", "noise_", "latent_", "positive", "negative"
                )
                _keys_to_drop = [
                    k for k in _inputs
                    if any(k.startswith(p) or k == p for p in _exclude_prefixes)
                    or _is_connection_link(_inputs[k])
                ]
                for _k in _keys_to_drop:
                    _inputs.pop(_k, None)

                # Extract raw extra_options string
                _eo_str = str(_inputs.pop("extra_options", ""))

                # Cache the parser result object only if it's safe to treat
                # as immutable/read-only for request reuse.  ExtraOptions is
                # immutable after construction (stores the string, __call__
                # does regex lookups only).  NEVER claim parsing was avoided
                # if we only validate the raw string — we instantiate the
                # full parser here.
                _parser: Any = None
                if _ExtraOptions is not None:
                    _parser = _ExtraOptions(_eo_str)
                    # Verify parseability — never swallow failure
                    _parser("test_parse", default=None)

                # Preserve disable_dummy_sampler_init if absent
                if "disable_dummy_sampler_init" not in _inputs:
                    _inputs["disable_dummy_sampler_init"] = True

                # Freeze static inputs (non-underscore keys)
                _frozen = {k: v for k, v in _inputs.items() if not k.startswith("_")}

                _prepared_records.append({
                    "node_id": _node_id,
                    "raw_extra_options": _eo_str,
                    "parser": _parser,
                    "static_inputs": _frozen,
                })

            self._res4lyf_static_prepared = tuple(
                (p["node_id"], p["static_inputs"]) for p in _prepared_records
            )
            results["res4lyf_static_prepared"] = True
            results["prepared_records"] = _prepared_records
            results["sampler_nodes"] = len(_prepared_records)
            results["parser_source"] = _parser_source
            results["ok"] = True
        except Exception as exc:
            results["error"] = str(exc)[:120]
        return results


def ensure_models_symlink(models_path: str, comfyui_root: str) -> str:
    """Ensure ComfyUI resolves its model directory without copying models."""
    source = Path(models_path)
    destination = Path(comfyui_root) / "models"
    if destination.is_symlink():
        if destination.resolve() != source.resolve():
            destination.unlink()
    elif destination.exists():
        if destination.resolve() == source.resolve():
            return str(destination)
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(source, target_is_directory=True)
    return str(destination)


def _write_manager_config_ini(path: Path) -> None:
    """Write ``[default] network_mode = offline`` preserving all existing sections.

    Uses ``ConfigParser(strict=False)`` to tolerate duplicate sections, and an
    atomic temp-file + ``os.replace`` to avoid partial writes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    parser = configparser.ConfigParser(strict=False)
    # Read the existing file (if any) into the parser.
    parser.read([str(path)], encoding="utf-8")
    if not parser.has_section("default"):
        parser.add_section("default")
    parser.set("default", "network_mode", "offline")

    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".config_tmp_", suffix=".ini", text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            parser.write(fh)
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def configure_manager_offline(
    comfyui_root: str,
    environ: dict[str, str] | None = None,
) -> dict[str, str]:
    """Set environment hints *and* write ``config.ini`` files so ComfyUI-Manager
    stays offline even when it reads config before checking environment variables.

    Parameters
    ----------
    comfyui_root:
        Absolute path to the ComfyUI root directory (e.g. ``/root/comfy/ComfyUI``).
    environ:
        Optional environment mapping (defaults to ``os.environ``).  Keys are set
        via ``setdefault`` so caller pre-sets are honoured.

    Returns
    -------
    Dict of the environment changes applied (always ``{"COMFYUI_MANAGER_MODE": "offline",
    "COMFYUI_MANAGER_NETWORK_MODE": "offline"}``).
    """
    target = environ if environ is not None else os.environ
    changes = {
        "COMFYUI_MANAGER_MODE": "offline",
        "COMFYUI_MANAGER_NETWORK_MODE": "offline",
    }
    for key, value in changes.items():
        target.setdefault(key, value)

    written: list[str] = []
    root = Path(comfyui_root)
    for rel_path in _MANAGER_CONFIG_PATHS:
        cfg = root / rel_path
        _write_manager_config_ini(cfg)
        written.append(str(cfg))

    _log.info("Manager offline config applied to %s", "; ".join(written))
    print("[v2.manager] network_mode=offline configs=%d" % len(written), flush=True)
    return changes


@contextlib.contextmanager
def cpu_snapshot_environment() -> Iterator[None]:
    """Hide CUDA only while snapshot-time imports execute."""
    previous = os.environ.get("CUDA_VISIBLE_DEVICES")
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        else:
            os.environ["CUDA_VISIBLE_DEVICES"] = previous


class RuntimeBootstrap:
    """Coordinates exactly one CPU-snapshot and one post-restore lifecycle."""

    def __init__(
        self,
        config: BootstrapConfig | None = None,
        *,
        reload_models: Callable[[], Any] | None = None,
        reload_runtime_state: Callable[[], Any] | None = None,
        sync_custom_nodes: Callable[[], Any] | None = None,
        install_requirements: Callable[[], Any] | None = None,
        start_backend: Callable[[], Any] | None = None,
        restore_gpu_state: Callable[[], Any] | None = None,
        initialize_cuda: Callable[[], Any] | None = None,
        apply_sage_policy: Callable[[], Any] | None = None,
        observe_generations: Callable[[], dict[str, str]] | None = None,
        read_current_custom_node_identity: Callable[[], dict[str, str]] | None = None,
        deployment_combined_hash: str = "",
    ) -> None:
        self.config = config or BootstrapConfig()
        self.reload_models = reload_models
        self.reload_runtime_state = reload_runtime_state
        self.sync_custom_nodes = sync_custom_nodes
        self.install_requirements = install_requirements
        self.start_backend = start_backend
        self.restore_gpu_state = restore_gpu_state
        self.initialize_cuda = initialize_cuda
        self.apply_sage_policy = apply_sage_policy
        self.observe_generations = observe_generations
        self.read_current_custom_node_identity = read_current_custom_node_identity
        self.state = BootstrapState()
        self._deployment_combined_hash = str(deployment_combined_hash or "")
        self._sage_baked_cuda_available = False
        self._backend_started = False

    def startup(self, *, snapshot: bool = True, trace: RuntimeTrace | None = None) -> BootstrapState:
        started = time.time()
        self.state.startup_started_at = started
        # Phase 0/3 — capture identity/environment metadata at lifecycle entry
        if trace:
            self.state.modal_task_id = os.environ.get("MODAL_TASK_ID", "")
            self.state.modal_image_id = os.environ.get("MODAL_IMAGE_ID", "")
            self.state.modal_cloud_provider = os.environ.get("MODAL_CLOUD_PROVIDER", "")
            self.state.modal_region = os.environ.get("MODAL_REGION", "")
            trace.emit(
                "snapshot_restore_start",
                phase="startup",
                metadata={
                    "modal_task_id": self.state.modal_task_id,
                    "modal_image_id": self.state.modal_image_id,
                    "modal_cloud_provider": self.state.modal_cloud_provider,
                    "modal_region": self.state.modal_region,
                    "snapshot_enabled": str(snapshot),
                },
            )
        try:
            if trace:
                trace.emit("models_symlink_start", phase="startup")
            ensure_models_symlink(self.config.models_path, self.config.comfyui_root)
            if trace:
                trace.emit("models_symlink_end", phase="startup")

            if trace:
                trace.emit("manager_offline_start", phase="startup")
            if self.config.manager_offline:
                configure_manager_offline(self.config.comfyui_root)
            if trace:
                trace.emit("manager_offline_end", phase="startup")

            if trace:
                trace.emit("reload_models_start", phase="startup")
            if self.reload_models:
                self.reload_models()
            if trace:
                trace.emit("reload_models_end", phase="startup")

            if trace:
                trace.emit("reload_runtime_state_start", phase="startup")
            if self.reload_runtime_state:
                self.reload_runtime_state()
            if trace:
                trace.emit("reload_runtime_state_end", phase="startup")

            if trace:
                trace.emit("sync_custom_nodes_start", phase="startup")
            if self.sync_custom_nodes:
                self.sync_custom_nodes()
            if trace:
                trace.emit("sync_custom_nodes_end", phase="startup")

            if trace:
                trace.emit("install_requirements_start", phase="startup")
            if self.config.install_requirements_on_startup and self.install_requirements:
                self.install_requirements()
            if trace:
                trace.emit("install_requirements_end", phase="startup")

            if trace:
                trace.emit("comfyui_path_setup_start", phase="startup")
            self._import_comfyui_path()
            if trace:
                trace.emit("comfyui_path_setup_end", phase="startup")

            if trace:
                trace.emit("backend_startup_start", phase="startup")
            if self.start_backend and not self._backend_started:
                backend = self.start_backend()
                self.state.backend = str(backend or "in_process")
                self._backend_started = True
            if trace:
                trace.emit("backend_startup_end", phase="startup")

            if trace:
                trace.emit("observe_generations_start", phase="startup")
            if self.observe_generations:
                observed = self.observe_generations() or {}
                self.state.runtime_generation = str(observed.get("runtime_state", ""))
                self.state.custom_node_generation = str(observed.get("custom_nodes", ""))
                self.state.snapshot_custom_node_source = str(
                    observed.get("custom_nodes_source", "") or ""
                )
            if trace:
                trace.emit("observe_generations_end", phase="startup")

            # ── Lane B: CPU-snapshot Sage pre-discovery ──
            # After all custom-node imports complete, discover and patch the
            # Sage target function with a stable sentinel. No CUDA/GPU access.
            _sage_snap_identity = _discover_and_patch_sage_cpu_snapshot(
                custom_node_generation=self.state.custom_node_generation,
                deployment_combined_hash=getattr(self, '_deployment_combined_hash', ''),
                baked_cuda_available=bool(
                    getattr(self, "_sage_baked_cuda_available", False)
                ),
            )
            self.state.snapshot_sage_identity = _sage_snap_identity
            if trace and _sage_snap_identity.get("sage_mode"):
                trace.emit(
                    "sage_snapshot_identity",
                    phase="startup",
                    metadata={
                        "sage_mode": _sage_snap_identity.get("sage_mode", ""),
                        "patch_version": _sage_snap_identity.get("patch_version", ""),
                        "target": _sage_snap_identity.get("patched_callable_qualname", ""),
                    },
                )

            # Lane B — freeze custom-node identity and persist the atomic versioned record
            _cn_identity_gen = self.state.custom_node_generation
            _cn_identity_src = (
                self.state.snapshot_custom_node_source or "observe_generations"
            )
            self.state.freeze_custom_node_identity(
                custom_node_generation=_cn_identity_gen,
                generation_source=_cn_identity_src,
                schema_version="1",
                deployment_combined_hash=getattr(self, '_deployment_combined_hash', ''),
            )
            # Persist atomic versioned record
            try:
                self._persist_custom_node_identity_record()
                if trace:
                    trace.emit(
                        "custom_node_identity_frozen",
                        phase="startup",
                        metadata={
                            "cn_gen": self.state.snapshot_custom_node_generation,
                            "source": _cn_identity_src,
                            "schema": self.state.snapshot_custom_node_schema,
                            "deployment_hash": self.state.deployment_combined_hash[:16] if self.state.deployment_combined_hash else "",
                        },
                    )
            except Exception as _pexc:
                print(f"[bootstrap] custom_node_identity_persist error: {_pexc}", flush=True)

            self.state.startup_completed_at = time.time()
            if trace:
                trace.emit(
                    "snapshot_restore_end",
                    phase="startup",
                    metadata={"status": "ok"},
                )
                durations = trace.durations_ms()
                self.state.stage_durations.update(durations)
            return self.state
        except Exception as exc:
            self.state.errors.append(str(exc))
            if trace:
                trace.emit(
                    "snapshot_restore_end",
                    phase="startup",
                    metadata={"status": "error", "error": str(exc)[:200]},
                )
            raise

    def _persist_custom_node_identity_record(self) -> None:
        """Persist an atomic versioned custom-node identity record to disk."""
        record_path = getattr(self.config, 'prescan_record_path', '')
        if not record_path:
            return
        import json
        payload = {
            "schema_version": self.state.snapshot_custom_node_schema,
            "custom_node_generation": self.state.snapshot_custom_node_generation,
            "generation_source": self.state.snapshot_custom_node_source,
            "deployment_combined_hash": self.state.deployment_combined_hash,
            "updated_at": time.time(),
        }
        tmp = f"{record_path}.tmp"
        os.makedirs(os.path.dirname(record_path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, sort_keys=True, separators=(",", ":"))
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, record_path)

    def _read_current_custom_node_identity(self) -> dict[str, str]:
        """Authoritative-only read of the current custom-node identity.

        Reads only an O(1) existing runtime API token, a small deployment-
        produced generation record, or the immutable in-memory deployment
        identity.  No directory enumeration, hashing, requirements scan,
        fingerprint, repair, or Volume sync.

        Returns a dict with keys: ``custom_node_generation``, ``generation_source``,
        ``schema_version``, ``deployment_combined_hash``, ``token``.
        When the identity is unavailable, returns ``{"custom_node_generation": ""}``.
        """
        result: dict[str, str] = {
            "custom_node_generation": "",
            "generation_source": "unavailable",
            "schema_version": "0",
            "deployment_combined_hash": "",
            "token": "",
        }
        try:
            # 1) Try the runtime API token (fastest, O(1))
            api_token = getattr(self, '_current_api_token', None)
            if api_token:
                result["token"] = str(api_token)
        except Exception:
            pass
        try:
            # 2) Try the persisted record from deployment
            record_path = getattr(self.config, 'prescan_record_path', '')
            if record_path and os.path.exists(record_path):
                import json
                with open(record_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    gen = data.get("custom_node_generation", "")
                    if gen:
                        result["custom_node_generation"] = str(gen)
                        result["generation_source"] = str(data.get("generation_source", "persisted_record"))
                        result["schema_version"] = str(data.get("schema_version", "0"))
                        result["deployment_combined_hash"] = str(data.get("deployment_combined_hash", ""))
                        return result
        except Exception:
            pass
        # 3) Fallback: in-memory deployment identity from snapshot state
        try:
            if self.state.snapshot_custom_node_generation:
                result["custom_node_generation"] = self.state.snapshot_custom_node_generation
                result["generation_source"] = "snapshot_memory"
                result["schema_version"] = self.state.snapshot_custom_node_schema
                result["deployment_combined_hash"] = self.state.deployment_combined_hash
        except Exception:
            pass
        return result

    def _restore_prescan_identity(self) -> None:
        """Read the persisted prescan record and populate legacy identity fields.

        If a prescan record exists and has a non-empty custom_node_generation,
        sets prescan_custom_node_generation, prescan_runtime_generation, etc.
        on the state for backward-compatible diagnostic use.
        """
        record_path = getattr(self.config, 'prescan_record_path', '')
        if not record_path or not os.path.exists(record_path):
            return
        try:
            import json
            with open(record_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                gen = data.get("custom_node_generation", "") or data.get("generation", "")
                if gen:
                    self.state.prescan_custom_node_generation = str(gen)
                    self.state.prescan_runtime_generation = str(
                        data.get("runtime_generation", "") or data.get("content_hash", "")
                    )
                    self.state.prescan_record_path = record_path
                    print(
                        f"[bootstrap] prescan_identity_restored "
                        f"cn_gen={gen[:24]} source=persisted_record",
                        flush=True,
                    )
        except Exception as exc:
            print(f"[bootstrap] prescan_identity_restore_error: {exc}", flush=True)

    # REMOVED: _build_and_store_snapshot_certificate — placeholder superseded
    # by the V2 workflow certificate built in ModalRuntimeEntrypoint.startup().

    def restore(self, *, trace: RuntimeTrace | None = None, _restore_isolation_enabled: bool = False) -> BootstrapState:
        started = time.perf_counter()
        self.state.restore_started_at = time.time()
        # Phase 0/3 — capture identity/environment metadata at lifecycle entry
        if trace:
            self.state.modal_task_id = os.environ.get("MODAL_TASK_ID", "")
            self.state.modal_image_id = os.environ.get("MODAL_IMAGE_ID", "")
            self.state.modal_cloud_provider = os.environ.get("MODAL_CLOUD_PROVIDER", "")
            self.state.modal_region = os.environ.get("MODAL_REGION", "")
            trace.emit(
                "snapshot_restore_start",
                phase="restore",
                metadata={
                    "modal_task_id": self.state.modal_task_id,
                    "modal_image_id": self.state.modal_image_id,
                    "modal_cloud_provider": self.state.modal_cloud_provider,
                    "modal_region": self.state.modal_region,
                },
            )
        try:
            # ── 1. restore_gpu_state ──
            def _do_restore_gpu_state():
                if trace:
                    trace.emit("restore_gpu_state_start", phase="restore")
                if self.restore_gpu_state:
                    self.restore_gpu_state()
                if trace:
                    trace.emit("restore_gpu_state_end", phase="restore")
            _restore_isolation_scope("restore_gpu_state", _do_restore_gpu_state, enabled=_restore_isolation_enabled)

            # ── 2. initialize_cuda_context ──
            def _do_initialize_cuda():
                if trace:
                    trace.emit("cuda_init_start", phase="restore")
                if self.initialize_cuda:
                    cuda_result = self.initialize_cuda()
                    if isinstance(cuda_result, dict):
                        self.state.cuda = dict(cuda_result)
                if trace:
                    trace.emit(
                        "cuda_init_end",
                        phase="restore",
                        metadata={
                            "device": str(self.state.cuda.get("device", "")),
                            "cuda_available": str(self.state.cuda.get("cuda_available", "")),
                        },
                    )
            _restore_isolation_scope("initialize_cuda_context", _do_initialize_cuda, enabled=_restore_isolation_enabled)

            # ── Lane B: Sage exact-match fast path ──
            # After initialize_cuda, read sys.modules and verify the snapshot
            # Sage identity sentinel.  Exact match skips full Sage discovery.
            # Timer immediately around _verify_sage_snapshot_identity only.
            _skipped_sage = False
            _sage_verify_ok = False
            _sage_verify_ms = 0.0
            if self.state.snapshot_sage_identity:
                _sage_current_identity = (
                    self.read_current_custom_node_identity()
                    if self.read_current_custom_node_identity is not None
                    else {}
                )
                _sage_t0 = time.perf_counter()
                _sage_verify_ok = bool(
                    not self.read_current_custom_node_identity
                    or _sage_current_identity.get("custom_node_generation")
                ) and _verify_sage_snapshot_identity(
                    snapshot_identity=self.state.snapshot_sage_identity,
                    current_custom_node_generation=str(
                        _sage_current_identity.get(
                            "custom_node_generation",
                            self.state.snapshot_custom_node_generation,
                        )
                    ),
                    current_deployment_combined_hash=str(
                        _sage_current_identity.get(
                            "deployment_combined_hash",
                            self.state.deployment_combined_hash,
                        )
                    ),
                )
                _sage_verify_ms = round((time.perf_counter() - _sage_t0) * 1000, 3)
            if _sage_verify_ok:
                _skipped_sage = True
                print(
                    f"[v2.sage_restore] decision=snapshot_exact_skip "
                    f"discovery_called=0 verify_ms={_sage_verify_ms}",
                    flush=True,
                )
            else:
                # Log why we fell through
                if not self.state.snapshot_sage_identity:
                    _reason = "no_snapshot_sage_identity"
                else:
                    _reason = "verify_failed"
                print(
                    f"[v2.sage_restore] decision=fallback_full_discovery "
                    f"reason={_reason}",
                    flush=True,
                )

            if not _skipped_sage:
                if trace:
                    trace.emit("sage_policy_start", phase="restore")
                if self.apply_sage_policy:
                    sage_result = self.apply_sage_policy()
                    if isinstance(sage_result, bool):
                        self.state.sage_mode = "baked_cuda" if sage_result else "triton_fallback"
                        self.state.sage_reason = "patched" if sage_result else "not-patched-or-not-found"
                    elif isinstance(sage_result, dict):
                        self.state.sage_mode = str(sage_result.get("mode", ""))
                        self.state.sage_reason = str(sage_result.get("reason", ""))
                    # Lane B: capture sage identity after successful application
                    if self.state.sage_mode:
                        self.state.sage_identity_captured = True
                if trace:
                    trace.emit(
                        "sage_policy_end",
                        phase="restore",
                        metadata={
                            "sage_mode": self.state.sage_mode,
                            "sage_reason": self.state.sage_reason,
                        },
                    )

            # ── 3. reload_runtime_state ──
            def _do_reload_runtime_state():
                if trace:
                    trace.emit("reload_runtime_state_start", phase="restore")
                if self.reload_runtime_state:
                    self.reload_runtime_state()
                if trace:
                    trace.emit("reload_runtime_state_end", phase="restore")
            _restore_isolation_scope("reload_runtime_state", _do_reload_runtime_state, enabled=_restore_isolation_enabled)

            # ── 4. reload_models ──
            def _do_reload_models():
                if trace:
                    trace.emit("reload_models_start", phase="restore")
                if self.reload_models:
                    self.reload_models()
                if trace:
                    trace.emit("reload_models_end", phase="restore")
            _restore_isolation_scope("reload_models", _do_reload_models, enabled=_restore_isolation_enabled)

            # Lane B: restore prescan identity from persisted record
            if self.read_current_custom_node_identity is None:
                self._restore_prescan_identity()

            # ── Lane B: custom-node restore fast path (authoritative-only) ──
            # Reads current authoritative-only identity and compares schema,
            # generation, and deployment hash against the snapshot identity.
            # Exact match skips sync_custom_nodes, observe_generations, and
            # fingerprint/hash scans.
            _check_start = time.perf_counter()
            _skipped_cn_sync = False
            _cn_decision = "snapshot_exact_skip"
            _cn_fallback_reason = ""

            _current_source = "unavailable"
            if self.read_current_custom_node_identity and self.sync_custom_nodes:
                current = self.read_current_custom_node_identity()
                _current_gen = current.get("custom_node_generation", "")
                _current_schema = current.get("schema_version", "0")
                _current_dep_hash = current.get("deployment_combined_hash", "")
                _current_source = current.get("generation_source", "unavailable")

                if not _current_gen:
                    _cn_fallback_reason = "missing_current_token"
                    _cn_decision = "fallback_full_sync"
                elif self.state.snapshot_custom_node_schema and _current_schema != self.state.snapshot_custom_node_schema:
                    _cn_fallback_reason = "schema_mismatch"
                    _cn_decision = "fallback_full_sync"
                elif self.state.snapshot_custom_node_generation and _current_gen != self.state.snapshot_custom_node_generation:
                    _cn_fallback_reason = "generation_mismatch"
                    _cn_decision = "fallback_full_sync"
                elif self.state.deployment_combined_hash and _current_dep_hash != self.state.deployment_combined_hash:
                    _cn_fallback_reason = "deployment_hash_mismatch"
                    _cn_decision = "fallback_full_sync"
                elif not self.state.has_snapshot_custom_node_identity():
                    _cn_fallback_reason = "untrusted_source"
                    _cn_decision = "fallback_full_sync"
                else:
                    _skipped_cn_sync = True
            elif self.state.has_prescan_identity() and self.sync_custom_nodes:
                # Fallback: use legacy prescan identity when read_current_custom_node_identity
                # is not provided (backward-compatible path for tests and simpler callers).
                _current_source = "prescan_identity"
                _skipped_cn_sync = True

            _check_ms = round((time.perf_counter() - _check_start) * 1000, 3)

            if _skipped_cn_sync:
                print(
                    f"[v2.custom_node_restore] "
                    f"decision={_cn_decision} "
                    f"callback_called=0 "
                    f"source={_current_source} "
                    f"check_ms={_check_ms}",
                    flush=True,
                )
            else:
                if _cn_fallback_reason:
                    print(
                        f"[v2.custom_node_restore] "
                        f"decision={_cn_decision} "
                        f"callback_called=1 "
                        f"source={_current_source if _current_source else 'unavailable'} "
                        f"check_ms={_check_ms} "
                        f"reason={_cn_fallback_reason}",
                        flush=True,
                    )
                if trace:
                    trace.emit("sync_custom_nodes_start", phase="restore")
                if self.sync_custom_nodes:
                    self.sync_custom_nodes()
                if trace:
                    trace.emit("sync_custom_nodes_end", phase="restore")
            if not _skipped_cn_sync:
                if trace:
                    trace.emit("observe_generations_start", phase="restore")
                if self.observe_generations:
                    observed = self.observe_generations() or {}
                    self.state.runtime_generation = str(observed.get("runtime_state", ""))
                    self.state.custom_node_generation = str(observed.get("custom_nodes", ""))
                if trace:
                    trace.emit("observe_generations_end", phase="restore")
                if self.state.custom_node_generation:
                    self.state.snapshot_custom_node_generation = self.state.custom_node_generation
                    self.state.snapshot_custom_node_source = "observe_generations"
                    try:
                        self._persist_custom_node_identity_record()
                    except Exception as _pexc:
                        print(f"[bootstrap] identity_publish_after_sync error: {_pexc}", flush=True)
            else:
                self.state.custom_node_generation = self.state.snapshot_custom_node_generation

            # Lane B — build SnapshotExecutionSeed from model identities
            _unet_id = self.state.cuda.get("unet_identity", "")
            _clip_id = self.state.cuda.get("clip_identity", "")
            _loader_sigs: list[dict[str, Any]] = []
            if _unet_id:
                _loader_sigs.append({"node_id": "unet", "signature": _unet_id})
            if _clip_id:
                _loader_sigs.append({"node_id": "clip", "signature": _clip_id})
            self.state.build_snapshot_execution_seed(
                workflow_hash=self.state.snapshot_certificate.get("identity_components", {}).get("workflow_hash", ""),
                custom_node_generation=self.state.snapshot_custom_node_generation,
                deployment_combined_hash=self.state.deployment_combined_hash,
                loader_cache_signatures=_loader_sigs,
            )
            if trace and self.state.snapshot_seed_built:
                trace.emit(
                    "snapshot_execution_seed_built",
                    phase="restore",
                    metadata={
                        "workflow_hash": (
                            self.state.snapshot_execution_seed.workflow_hash[:16]
                            if self.state.snapshot_execution_seed is not None else ""
                        ),
                        "loader_count": len(_loader_sigs),
                        "deployment_hash": self.state.deployment_combined_hash[:16] if self.state.deployment_combined_hash else "",
                    },
                )

            self.state.restore_completed_at = time.time()
            if trace:
                trace.emit(
                    "snapshot_restore_end",
                    phase="restore",
                    metadata={"status": "ok"},
                )
                durations = trace.durations_ms()
                self.state.stage_durations.update(durations)
            return self.state
        except Exception as exc:
            self.state.errors.append(str(exc))
            if trace:
                trace.emit(
                    "snapshot_restore_end",
                    phase="restore",
                    metadata={"status": "error", "error": str(exc)[:200]},
                )
            raise

    def _import_comfyui_path(self) -> None:
        root = self.config.comfyui_root
        if root and root not in sys.path and Path(root).exists():
            sys.path.insert(0, root)
