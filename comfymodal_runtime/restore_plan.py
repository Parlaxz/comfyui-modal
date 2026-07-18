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
from typing import Any

from comfymodal_runtime.contracts import (
    ModelRestoreKey,
    PrefillKey,
    RestorePlan,
    stable_hash,
)
from comfymodal_runtime.runtime_state import CommitCoordinator


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
    texts = _extract_prompt_texts(workflow)
    bundle_hash = (
        stable_hash({"prompts": sorted(texts)}) if texts else ""
    )
    return PrefillKey(
        model_key=model_key,
        prompt_bundle_hash=bundle_hash,
    )


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
        }
        return stable_hash(identity)

    def publish(self, new_plan: RestorePlan) -> int:
        """Publish *new_plan*.

        Returns the observed generation (as an ``int``).

        * Loads the current authoritative plan from the volume.
        * Compares **identity fields** (model_key, prefill_key, model_spec,
          prefill_spec, source_workflow_hash, schema_version) — volatile
          ``generation`` and ``created_at`` are **excluded** from the
          comparison.  When the identity is unchanged, no write occurs.
        * If the identity differs, assigns a **monotonic** generation:
          when the incoming plan's generation is the default (``0``) or
          behind the current authoritative generation, the generation is
          advanced by one.  Explicit higher generations are preserved.
        * Writes the new plan, commits once, and returns the assigned
          generation.

        Non-numeric generations are safely coerced to ``0``.
        """
        # 1. Reload authoritative state from the volume.
        current_plan = self._load_current_plan()

        # 2. No-op when identity is unchanged (ignore volatile generation/created_at)
        if current_plan is not None:
            if self._identity_hash(current_plan) == self._identity_hash(new_plan):
                return self._safe_generation(current_plan.generation)

        # 3. Compute monotonic generation
        incoming_gen = self._safe_generation(new_plan.generation)
        if current_plan is not None:
            current_gen = self._safe_generation(current_plan.generation)
            if incoming_gen > current_gen:
                generation = incoming_gen
            else:
                generation = current_gen + 1
        else:
            generation = incoming_gen

        # 4. Write + commit once.
        plan_dict = new_plan.to_dict()
        plan_dict["generation"] = generation
        self._coordinator.write_state(
            generation,
            {"restore_plan": plan_dict},
        )
        self._coordinator.commit(generation)

        return generation

    def _load_current_plan(self) -> RestorePlan | None:
        """Load the current ``RestorePlan`` from authoritative state."""
        state = self._coordinator.read_state()
        if state is None:
            return None
        plan_data = state.get("restore_plan")
        if not plan_data:
            return None
        return RestorePlan.from_dict(plan_data)
