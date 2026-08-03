"""RestorePlan derivation and remote-authoritative publication.

Model key excludes seed, output, run, and prompt fields — only model-loader
identities participate.  Prompt-only changes alter the prefill identity but
not the model identity.

The publisher reloads authoritative state from the volume, performs no write
or commit when the complete plan is unchanged, atomically replaces a changed
plan, commits exactly once, and returns the observed generation.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Mapping

from comfymodal_runtime.contracts import (
    ModelRestoreKey,
    PrefillKey,
    RestorePlan,
    stable_hash,
)
from comfymodal_runtime.runtime_state import CommitCoordinator
from comfymodal_runtime.trace import RuntimeTrace


# ── Default publisher singleton ────────────────────────────────────────
# Lazily initialised once; concurrent callers share the same coordinator.

_default_publisher: Any | None = None
_default_publisher_lock = threading.Lock()


def get_default_restore_publisher():
    """Return a module-level singleton ``RestorePlanPublisher`` backed by
    one ``MountedStateVolume`` rooted at the custom-node root's
    ``.runtime_state/`` and one shared ``CommitCoordinator``.

    Not initialized at import time — first call on the v2 execution path.
    Concurrent callers share the same coordinator safely.
    """
    global _default_publisher
    if _default_publisher is not None:
        return _default_publisher
    with _default_publisher_lock:
        if _default_publisher is not None:
            return _default_publisher
        from comfymodal_runtime.runtime_state import CommitCoordinator, MountedStateVolume

        # Compute the plugin root — same convention as __init__._NODE_DIR
        _plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _runtime_state_dir = os.path.join(_plugin_root, ".runtime_state")
        _volume = MountedStateVolume(_runtime_state_dir)
        _coordinator = CommitCoordinator(_volume)
        _default_publisher = RestorePlanPublisher(_coordinator)
    return _default_publisher


# ── Internal helpers ─────────────────────────────────────────────────────


def _build_dual_clip_identity(clip_name1: str, clip_name2: str) -> str:
    """Concatenate both clip names with a stable separator.

    When both names are identical, returns the single name to avoid
    unnecessary identity bloat.
    """
    if clip_name1 == clip_name2:
        return clip_name1
    return f"{clip_name1}||{clip_name2}"


def _extract_model_references(workflow: dict) -> dict[str, str]:
    """Extract model-loader references from a workflow dict.

    Returns ``{role: filename}`` where *role* is one of ``"unet"``,
    ``"clip"``, ``"vae"``, or ``"clip_type"``.

    ``DualCLIPLoader`` contributes both ``clip_name1`` and ``clip_name2``
    to the single ``clip`` identity by concatenating them with a ``||``
    separator (see ``_build_dual_clip_identity``).  This ensures that
    swapping either clip name changes the model identity.
    """
    refs: dict[str, str] = {}
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue

        if ct in ("CheckpointLoaderSimple", "CheckpointLoader"):
            v = inputs.get("ckpt_name", "")
            if isinstance(v, str) and v:
                refs["unet"] = v
                refs["clip"] = v
                refs["vae"] = v
        elif ct == "UNETLoader":
            v = inputs.get("unet_name", "")
            if isinstance(v, str) and v:
                refs["unet"] = v
        elif ct == "CLIPLoader":
            v = inputs.get("clip_name", "")
            if isinstance(v, str) and v:
                refs["clip"] = v
            t = inputs.get("type", "")
            if isinstance(t, str) and t:
                refs["clip_type"] = t
        elif ct == "DualCLIPLoader":
            v1 = inputs.get("clip_name1", "")
            v2 = inputs.get("clip_name2", "")
            c1 = v1 if isinstance(v1, str) else ""
            c2 = v2 if isinstance(v2, str) else ""
            refs["clip"] = _build_dual_clip_identity(c1, c2)
            t = inputs.get("type", "")
            if isinstance(t, str) and t:
                refs["clip_type"] = t
        elif ct == "VAELoader":
            v = inputs.get("vae_name", "")
            if isinstance(v, str) and v:
                refs["vae"] = v
    return refs


def _extract_prompt_texts(workflow: dict) -> list[str]:
    """Extract all CLIP text-prompt strings from a workflow.

    Only ``CLIPTextEncode`` and ``CLIPTextEncodeSDXL`` nodes are scanned.
    Seed, output routing, and run-level options are excluded.
    """
    texts: list[str] = []
    ENCODE_CLASSES = frozenset({"CLIPTextEncode", "CLIPTextEncodeSDXL"})
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type", "") in ENCODE_CLASSES:
            inputs = node.get("inputs", {})
            if isinstance(inputs, dict):
                text = inputs.get("text", "")
                if isinstance(text, str) and text:
                    texts.append(text)
    return texts


def _infer_prompt_role(node: dict[str, Any]) -> str:
    labels = [
        node.get("title", ""),
        node.get("name", ""),
        (node.get("_meta") or {}).get("title", "") if isinstance(node.get("_meta"), dict) else "",
    ]
    label = " ".join(str(value or "") for value in labels).lower()
    if "negative" in label:
        return "negative"
    if "positive" in label:
        return "positive"
    # Unlabeled CLIPTextEncode nodes default to "positive" so they are
    # eligible when lane mode is "critical" (the default).  Explicit
    # positive/negative inference above is preserved.
    return "positive"


def _extract_safe_prefill_bundle(workflow: dict) -> dict[str, Any]:
    """Use the proven static resolver and build an exact identity bundle."""
    try:
        from optimizations import extract_safe_prompt_bundle
    except Exception as exc:
        return {"eligible": False, "reason": f"resolver_unavailable:{type(exc).__name__}", "encodes": []}

    try:
        resolved = extract_safe_prompt_bundle(workflow)
    except Exception as exc:
        return {"eligible": False, "reason": f"resolver_error:{type(exc).__name__}", "encodes": []}
    if not isinstance(resolved, dict) or not resolved.get("eligible"):
        return {
            "eligible": False,
            "reason": str((resolved or {}).get("reason", "not_eligible")),
            "encodes": [],
        }

    canonical_encodes: list[dict[str, Any]] = []
    for entry in resolved.get("encodes", []):
        if not isinstance(entry, dict):
            continue
        node_id = str(entry.get("node_id", ""))
        node = workflow.get(node_id, {}) if isinstance(workflow, dict) else {}
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        canonical_encodes.append({
            "node_id": node_id,
            "node_class": str(node.get("class_type", "")),
            "prompt_input": "text",
            "role": _infer_prompt_role(node),
            "text": str(entry.get("text", "")),
            "clip_connection": inputs.get("clip"),
            "text_connection": inputs.get("text") if isinstance(inputs.get("text"), list) else None,
            "loader_class": str(entry.get("loader_class", "")),
            "filenames": list(entry.get("filenames", [])),
            "clip_type": str(entry.get("clip_type", "")),
            "text_source": list(entry.get("text_source", [])),
            "adapter_chain": list(entry.get("adapter_chain", [])),
        })
    if not canonical_encodes:
        return {"eligible": False, "reason": "no_safe_encodes", "encodes": []}

    bundle = {
        "schema_version": 1,
        "eligible": True,
        "encodes": canonical_encodes,
    }
    bundle["bundle_hash"] = stable_hash(bundle)
    return bundle


# ── Public derivation functions ──────────────────────────────────────────


def derive_model_key(workflow: dict) -> ModelRestoreKey:
    """Derive model identity from a workflow dict.

    The model key includes only model-loader fields (UNET, CLIP, VAE
    identities).  Seed, output, run, and prompt fields are **excluded** —
    changing only the prompt text does NOT change the model identity.
    """
    refs = _extract_model_references(workflow)
    return ModelRestoreKey(
        unet_identity=refs.get("unet", ""),
        clip_identity=refs.get("clip", ""),
        vae_identity=refs.get("vae", ""),
        clip_type=refs.get("clip_type", ""),
    )


def derive_prefill_key(
    model_key: ModelRestoreKey, workflow: dict
) -> PrefillKey:
    """Derive prefill identity from model key and workflow.

    Prompt-only changes (e.g. changing CLIP text) change the prefill
    identity but do **not** change the model identity.  The prompt bundle
    hash is derived deterministically from prompt text only.
    """
    bundle = _extract_safe_prefill_bundle(workflow)
    bundle_hash = str(bundle.get("bundle_hash", "")) if bundle.get("eligible") else ""
    return PrefillKey(
        model_key=model_key,
        prompt_bundle_hash=bundle_hash,
        encode_options={
            "eligible": bool(bundle.get("eligible")),
            "schema_version": bundle.get("schema_version", 1),
            "reason": bundle.get("reason", "ok"),
            "encodes": bundle.get("encodes", []),
        },
    )


def build_restore_model_spec(workflow: dict, model_stack: dict | None = None) -> dict[str, Any]:
    """Serialize the concrete loader requests needed by the remote preload.

    ``ModelRestoreKey`` intentionally contains identities only.  The remote
    runtime also needs the exact node arguments (weight dtype, CLIP type, and
    dual-CLIP filenames) to invoke ComfyUI's real loader methods during
    ``snap=False``.  Keep that small, deterministic request list alongside the
    key rather than making the remote runtime re-parse a workflow it does not
    receive.
    """
    loaders: dict[str, list[dict[str, Any]]] = {
        "unet": [],
        "clip": [],
        "vae": [],
    }
    for node_id, node in (workflow or {}).items():
        if not isinstance(node, dict):
            continue
        class_type = str(node.get("class_type", ""))
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        if class_type == "UNETLoader" and isinstance(inputs.get("unet_name"), str):
            loaders["unet"].append({
                "node_id": str(node_id),
                "loader_class": class_type,
                "unet_name": inputs["unet_name"],
                "weight_dtype": str(inputs.get("weight_dtype", "default")),
            })
        elif class_type == "CLIPLoader" and isinstance(inputs.get("clip_name"), str):
            loaders["clip"].append({
                "node_id": str(node_id),
                "loader_class": class_type,
                "clip_name": inputs["clip_name"],
                "type": str(inputs.get("type", "stable_diffusion")),
                "device": str(inputs.get("device", "default")),
            })
        elif class_type == "DualCLIPLoader":
            if isinstance(inputs.get("clip_name1"), str) and isinstance(inputs.get("clip_name2"), str):
                loaders["clip"].append({
                    "node_id": str(node_id),
                    "loader_class": class_type,
                    "clip_name1": inputs["clip_name1"],
                    "clip_name2": inputs["clip_name2"],
                    "type": str(inputs.get("type", "sdxl")),
                    "device": str(inputs.get("device", "default")),
                })
        elif class_type == "VAELoader" and isinstance(inputs.get("vae_name"), str):
            loaders["vae"].append({
                "node_id": str(node_id),
                "loader_class": class_type,
                "vae_name": inputs["vae_name"],
            })
    return {
        "model_stack": dict(model_stack or {}),
        "loaders": loaders,
    }


# ── Publisher ────────────────────────────────────────────────────────────


class RestorePlanPublisher:
    """Synchronous publisher for ``RestorePlan``.

    Reloads authoritative state from the volume before deciding.  When
    the complete plan is unchanged from the current authoritative state,
    no write or commit is performed.  When the plan differs, it is
    atomically written and committed once.

    Returns the observed generation after publication.
    """

    def __init__(self, coordinator: CommitCoordinator) -> None:
        self._coordinator = coordinator
        self.last_publish: dict[str, Any] = {}

    @staticmethod
    def _safe_generation(value: int | str) -> int:
        """Safely coerce *value* to ``int``.

        Returns ``0`` when the value is a non-numeric string or otherwise
        cannot be safely interpreted as an integer.
        """
        if isinstance(value, int):
            return value
        try:
            return int(str(value))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _identity_hash(plan: RestorePlan) -> str:
        """Deterministic hash of the plan's identity fields, excluding
        volatile ``generation`` and ``created_at``.

        Two equivalent model/prefill identities created at different times
        produce the same hash, so the no-op check does not falsely trigger
        a write when only timestamps differ.
        """
        identity = {
            "schema_version": plan.schema_version,
            "model_key": plan.model_key.to_dict(),
            "prefill_key": plan.prefill_key.to_dict(),
            "model_spec": dict(plan.model_spec),
            "prefill_spec": dict(plan.prefill_spec),
            "source_workflow_hash": plan.source_workflow_hash,
            "workflow_hash": plan.workflow_hash,
        }
        return stable_hash(identity)

    @staticmethod
    def _build_publication_trace(metrics: dict[str, Any]) -> RuntimeTrace:
        """Build a structured ``RuntimeTrace`` from publication measurement
        keys recorded in *metrics*.

        The trace conveys the same measurements as the flat dict but in a
        structured event form that ``merge_runtime_traces`` can consume.
        Event wall timestamps reflect when the trace is assembled — the
        actual measured durations are carried in event metadata.
        """
        trace = RuntimeTrace(process="publisher")
        trace.emit(
            "publish_state_read",
            phase="publish",
            metadata={"reload_ms": metrics.get("reload_ms", 0.0)},
        )
        trace.emit(
            "publish_compare",
            phase="publish",
            metadata={"compare_ms": metrics.get("compare_ms", 0.0)},
        )
        if metrics.get("changed"):
            trace.emit(
                "publish_write",
                phase="publish",
                metadata={
                    "write_ms": metrics.get("write_ms", 0.0),
                    "bytes_written": metrics.get("bytes_written", 0),
                },
            )
            trace.emit(
                "publish_commit",
                phase="publish",
                metadata={
                    "commit_ms": metrics.get("commit_ms", 0.0),
                },
            )
        else:
            trace.emit(
                "publish_noop",
                phase="publish",
                metadata={"reason": "unchanged_identity"},
            )
        trace.set_metadata(
            generation=str(metrics.get("generation", "")),
            changed=bool(metrics.get("changed")),
            state_path=str(metrics.get("state_path", "")),
            model_identity_changed=bool(metrics.get("model_identity_changed", False)),
            prefill_identity_changed=bool(metrics.get("prefill_identity_changed", False)),
            duration_source="event_metadata",
            wall_timestamps_are="assembly_time",
        )
        return trace

    def publish(self, new_plan: RestorePlan, *, snapshot_seed: Mapping[str, Any] | None = None) -> int:
        """Publish *new_plan* (and optional *snapshot_seed*) and return its
        authoritative generation."""
        return int(self.publish_with_metrics(new_plan, snapshot_seed=snapshot_seed)["generation"])

    def publish_with_metrics(
        self,
        new_plan: RestorePlan,
        *,
        snapshot_seed: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Publish *new_plan* and return generation plus lifecycle timings.

        When *snapshot_seed* is provided (a validated schema-v2 seed payload)
        it is written atomically alongside the plan in the same state write,
        making the seed deployment-scoped and read-back-able via
        ``read_snapshot_seed``.  When omitted and a valid seed is already
        persisted, the republished plan preserves that seed unchanged.
        """
        started = time.perf_counter()
        current_plan = self._load_current_plan()
        reload_completed = time.perf_counter()
        incoming_seed = dict(snapshot_seed) if snapshot_seed is not None else None

        compare_started = time.perf_counter()
        if current_plan is not None:
            if self._identity_hash(current_plan) == self._identity_hash(new_plan):
                # The no-op check covers the COMPLETE state payload: the plan
                # identity AND the atomically-persisted snapshot seed.  A
                # changed seed (e.g. a new deployment custom-node generation)
                # with an unchanged plan still forces a republish so the
                # deployment-scoped seed is never stale.  An omitted incoming
                # seed leaves the persisted seed untouched, so an unchanged
                # plan is always a no-op in that case.
                current_seed = self.read_snapshot_seed()
                if incoming_seed is None or current_seed == incoming_seed:
                    reload_ms = round((reload_completed - started) * 1000.0, 3)
                    compare_ms = round((time.perf_counter() - compare_started) * 1000.0, 3)
                    result = {
                        "changed": False,
                        "generation": self._safe_generation(current_plan.generation),
                        "reload_ms": reload_ms,
                        "compare_ms": compare_ms,
                        "write_ms": 0.0,
                        "commit_ms": 0.0,
                        "bytes_written": 0,
                        "state_path": getattr(self._coordinator, "state_path", ""),
                        "model_identity_changed": False,
                        "prefill_identity_changed": False,
                    }
                    result["trace"] = self._build_publication_trace(result).to_dict()
                    self.last_publish = result
                    return result

        compare_completed = time.perf_counter()
        # Identity-change flags: first publication both true; otherwise compare
        if current_plan is None:
            model_identity_changed = True
            prefill_identity_changed = True
        else:
            model_identity_changed = (
                current_plan.model_key.stable_hash != new_plan.model_key.stable_hash
                or bool(current_plan.model_spec) != bool(new_plan.model_spec)
                or (current_plan.model_spec and new_plan.model_spec
                    and stable_hash(current_plan.model_spec) != stable_hash(new_plan.model_spec))
            )
            prefill_identity_changed = (
                current_plan.prefill_key.stable_hash != new_plan.prefill_key.stable_hash
                or bool(current_plan.prefill_spec) != bool(new_plan.prefill_spec)
                or (current_plan.prefill_spec and new_plan.prefill_spec
                    and stable_hash(current_plan.prefill_spec) != stable_hash(new_plan.prefill_spec))
            )

        incoming_gen = self._safe_generation(new_plan.generation)
        if current_plan is not None:
            current_gen = self._safe_generation(current_plan.generation)
            if incoming_gen > current_gen:
                generation = incoming_gen
            else:
                generation = current_gen + 1
        else:
            generation = incoming_gen

        plan_dict = new_plan.to_dict()
        plan_dict["generation"] = generation
        before_bytes = self._coordinator.metrics.total_write_bytes
        write_started = time.perf_counter()
        _state_payload: dict[str, Any] = {"restore_plan": plan_dict}
        if snapshot_seed is not None:
            _state_payload["snapshot_seed"] = dict(snapshot_seed)
        else:
            _preserved_seed = self.read_snapshot_seed()
            if _preserved_seed is not None:
                _state_payload["snapshot_seed"] = _preserved_seed
        self._coordinator.write_state(
            generation,
            _state_payload,
        )
        write_completed = time.perf_counter()
        after_bytes = self._coordinator.metrics.total_write_bytes
        commit_started = time.perf_counter()
        self._coordinator.commit(generation)
        commit_completed = time.perf_counter()
        result = {
            "changed": True,
            "generation": generation,
            "reload_ms": round((reload_completed - started) * 1000.0, 3),
            "compare_ms": round((compare_completed - compare_started) * 1000.0, 3),
            "write_ms": round((write_completed - write_started) * 1000.0, 3),
            "commit_ms": round((commit_completed - commit_started) * 1000.0, 3),
            "bytes_written": after_bytes - before_bytes,
            "state_path": getattr(self._coordinator, "state_path", ""),
            "model_identity_changed": model_identity_changed,
            "prefill_identity_changed": prefill_identity_changed,
        }
        result["trace"] = self._build_publication_trace(result).to_dict()
        self.last_publish = result
        return result

    async def publish_with_metrics_async(
        self,
        new_plan: RestorePlan,
        *,
        snapshot_seed: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Async variant of ``publish_with_metrics`` that performs exactly one
        awaited async commit and no blocking Modal commit.

        Same semantics as ``publish_with_metrics()`` but uses
        ``coordinator.commit_async()`` to avoid blocking the event loop when
        the underlying Modal Volume commit is async.  Also uses async reload
        (``coordinator.reload_async()``) so Modal's Volume reload is not
        called synchronously from async code.  An omitted *snapshot_seed*
        preserves the currently persisted valid seed on a republish.
        """
        started = time.perf_counter()
        current_plan = await self._load_current_plan_async()
        reload_completed = time.perf_counter()
        incoming_seed = dict(snapshot_seed) if snapshot_seed is not None else None

        compare_started = time.perf_counter()
        if current_plan is not None:
            if self._identity_hash(current_plan) == self._identity_hash(new_plan):
                # No-op detection covers the COMPLETE state payload — plan
                # identity AND the atomically-persisted snapshot seed (see the
                # sync variant for the rationale).  An omitted incoming seed
                # leaves the persisted seed untouched, so an unchanged plan is
                # always a no-op in that case.
                current_seed = self.read_snapshot_seed()
                if incoming_seed is None or current_seed == incoming_seed:
                    reload_ms = round((reload_completed - started) * 1000.0, 3)
                    compare_ms = round((time.perf_counter() - compare_started) * 1000.0, 3)
                    result = {
                        "changed": False,
                        "generation": self._safe_generation(current_plan.generation),
                        "reload_ms": reload_ms,
                        "compare_ms": compare_ms,
                        "write_ms": 0.0,
                        "commit_ms": 0.0,
                        "bytes_written": 0,
                        "state_path": getattr(self._coordinator, "state_path", ""),
                        "model_identity_changed": False,
                        "prefill_identity_changed": False,
                    }
                    result["trace"] = self._build_publication_trace(result).to_dict()
                    self.last_publish = result
                    return result

        compare_completed = time.perf_counter()
        # Identity-change flags: first publication both true; otherwise compare
        if current_plan is None:
            model_identity_changed = True
            prefill_identity_changed = True
        else:
            model_identity_changed = (
                current_plan.model_key.stable_hash != new_plan.model_key.stable_hash
                or bool(current_plan.model_spec) != bool(new_plan.model_spec)
                or (current_plan.model_spec and new_plan.model_spec
                    and stable_hash(current_plan.model_spec) != stable_hash(new_plan.model_spec))
            )
            prefill_identity_changed = (
                current_plan.prefill_key.stable_hash != new_plan.prefill_key.stable_hash
                or bool(current_plan.prefill_spec) != bool(new_plan.prefill_spec)
                or (current_plan.prefill_spec and new_plan.prefill_spec
                    and stable_hash(current_plan.prefill_spec) != stable_hash(new_plan.prefill_spec))
            )

        incoming_gen = self._safe_generation(new_plan.generation)
        if current_plan is not None:
            current_gen = self._safe_generation(current_plan.generation)
            if incoming_gen > current_gen:
                generation = incoming_gen
            else:
                generation = current_gen + 1
        else:
            generation = incoming_gen

        plan_dict = new_plan.to_dict()
        plan_dict["generation"] = generation
        before_bytes = self._coordinator.metrics.total_write_bytes
        write_started = time.perf_counter()
        _state_payload_async: dict[str, Any] = {"restore_plan": plan_dict}
        if snapshot_seed is not None:
            _state_payload_async["snapshot_seed"] = dict(snapshot_seed)
        else:
            _preserved_seed = self.read_snapshot_seed()
            if _preserved_seed is not None:
                _state_payload_async["snapshot_seed"] = _preserved_seed
        self._coordinator.write_state(
            generation,
            _state_payload_async,
        )
        write_completed = time.perf_counter()
        after_bytes = self._coordinator.metrics.total_write_bytes
        commit_started = time.perf_counter()
        await self._coordinator.commit_async(generation)
        commit_completed = time.perf_counter()
        result = {
            "changed": True,
            "generation": generation,
            "reload_ms": round((reload_completed - started) * 1000.0, 3),
            "compare_ms": round((compare_completed - compare_started) * 1000.0, 3),
            "write_ms": round((write_completed - write_started) * 1000.0, 3),
            "commit_ms": round((commit_completed - commit_started) * 1000.0, 3),
            "bytes_written": after_bytes - before_bytes,
            "state_path": getattr(self._coordinator, "state_path", ""),
            "model_identity_changed": model_identity_changed,
            "prefill_identity_changed": prefill_identity_changed,
        }
        result["trace"] = self._build_publication_trace(result).to_dict()
        self.last_publish = result
        return result

    def read_current_plan(self) -> RestorePlan | None:
        """Reload and return the authoritative plan currently on the volume."""
        return self._load_current_plan()

    async def read_current_plan_async(self) -> RestorePlan | None:
        """Async variant of ``read_current_plan`` using async reload."""
        return await self._load_current_plan_async()

    def _load_current_plan(self) -> RestorePlan | None:
        """Load the current ``RestorePlan`` from authoritative state."""
        reload_fn = getattr(self._coordinator, "reload", None)
        if callable(reload_fn):
            reload_fn()
        return self._read_state_plan()

    async def _load_current_plan_async(self) -> RestorePlan | None:
        """Async variant of ``_load_current_plan`` using async reload."""
        await self._coordinator.reload_async()
        return self._read_state_plan()

    def _read_state_plan(self) -> RestorePlan | None:
        """Read RestorePlan from coordinator state (no reload)."""
        state = self._coordinator.read_state()
        if state is None:
            return None
        plan_data = state.get("restore_plan")
        if not plan_data:
            return None
        return RestorePlan.from_dict(plan_data)

    def read_snapshot_seed(self) -> dict[str, Any] | None:
        """Read the deployment-scoped snapshot-seed payload written alongside
        the restore plan (``None`` when absent/invalid)."""
        state = self._coordinator.read_state()
        if state is None:
            return None
        seed_data = state.get("snapshot_seed")
        if not isinstance(seed_data, Mapping) or not seed_data:
            return None
        return dict(seed_data)


class RemoteRestorePlanPublisher:
    """Async adapter that publishes through the v2 Modal transport."""

    def __init__(self, transport: Any, workspace: dict[str, Any] | None = None) -> None:
        self.transport = transport
        self.workspace = workspace

    async def publish(
        self,
        plan: RestorePlan,
        *,
        snapshot_seed: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Publish *plan* (and optional schema-v2 *snapshot_seed*) through the
        v2 Modal transport so both are written atomically to the
        deployment-scoped runtime-state volume."""
        return await self.transport.publish_restore_plan(
            plan.to_dict(),
            workspace=self.workspace,
            snapshot_seed=snapshot_seed,
        )
