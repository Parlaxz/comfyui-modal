"""Thin seam adapters for comfyapp.py reconciliation (E40 owns that file).

R41 deliberately keeps ``comfyapp.py`` edits at zero: the Golden pipeline is
fully exercised through this module's seams and the deterministic local test
suite.  Remote validation happens only after R41 reconciles onto E40.

Intended integration hunks (documented for R41_E40_RECONCILIATION_MANIFEST):

1. CLIP clean-lane QD call site (post-E39 anchor:
   ``clip_fast_hydration_wiring.py`` QD invocation seam) routes through
   ``seams["clip_golden_load"]`` when ``golden_pipeline_enabled()``.
2. ``load_models_gpu`` wrapper (post-E39 single observation boundary)
   consults ``GoldenOwnerRegistry.join_or_adopt(UNET, ...)`` BEFORE any
   native migration — adoption of the Golden owner, never a re-read.
3. ``VAEDecode`` consume path calls ``seams["vae_demand_join"]`` before the
   native decode; ADOPTED/FAILED/TIMEOUT decisions classify DEGRADED.

Enablement semantics: ``COMFYMODAL_GOLDEN_PIPELINE`` is a deploy-time
enablement switch only.  It is NOT runtime adaptive selection — the role
policy stays immutable QD4 regardless.  Provider/region/cloud/host identity
is telemetry-only and never influences algorithm selection.
"""

from __future__ import annotations

import os
from typing import Dict

from .contracts import GoldenError
from .pipeline import GoldenPipeline

__all__ = ["golden_pipeline_enabled", "install_golden_seams"]


def golden_pipeline_enabled() -> bool:
    """Deploy-time enablement switch (not a runtime algorithm selector)."""
    return os.environ.get("COMFYMODAL_GOLDEN_PIPELINE", "0") == "1"


def install_golden_seams(pipeline: GoldenPipeline) -> Dict[str, object]:
    """Bind fail-closed seam callables to a pipeline instance.

    Every seam propagates exceptions; none contains a silent fallback.
    """

    def clip_golden_load(loader, binding):
        return pipeline.run_role_load(binding.role, loader, binding, label_prefix="golden")

    def unet_golden_prepare(binding):
        return pipeline.unet_prepare(binding)

    def unet_golden_commit(loader, binding):
        return pipeline.run_unet_commit(loader, binding)

    def vae_golden_qd(loader, binding):
        return pipeline.run_vae_qd(loader, binding)

    def vae_demand_join(join_timeout_s=None):
        return pipeline.vae_decode_demand(join_timeout_s)

    def unet_demand_join(join_timeout_s=None):
        from .contracts import ModelRole

        decision, owner = pipeline.registry.join_or_adopt(
            ModelRole.UNET,
            pipeline.join_timeout_s if join_timeout_s is None else join_timeout_s,
        )
        return {"decision": decision.value, "owner": owner}

    seams: Dict[str, object] = {
        "clip_golden_load": clip_golden_load,
        "unet_golden_prepare": unet_golden_prepare,
        "unet_golden_commit": unet_golden_commit,
        "unet_demand_join": unet_demand_join,
        "vae_golden_qd": vae_golden_qd,
        "vae_demand_join": vae_demand_join,
    }
    for name, fn in seams.items():
        if not callable(fn):
            raise GoldenError(f"seam {name} not callable")
    return seams
