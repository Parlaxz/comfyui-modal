"""Declarative E40 cache taxonomy.

This module intentionally contains no cache implementation or runtime wiring;
it is a small documentation-grade contract for snapshot and golden-lane
reviews.
"""

from __future__ import annotations


TAXONOMY = {
    "exact_clip_conditioning_cache": {
        "name": "exact_clip_conditioning_cache",
        "kind": "CONDITIONING_CACHE",
        "golden_requirement": "FORCED_MISS",
        "reference_file": "comfymodal_runtime/clip_conditioning_cache.py",
    },
    "conditioning_prefetch_memory_cache": {
        "name": "conditioning_prefetch_memory_cache",
        "kind": "CONDITIONING_CACHE",
        "golden_requirement": "OPTIONAL",
        "reference_file": "comfymodal_runtime/clip_conditioning_cache.py",
    },
    "prompt_signature_cache": {
        "name": "prompt_signature_cache",
        "kind": "RUNTIME_MEMO",
        "golden_requirement": "OPTIONAL",
        "reference_file": "comfymodal_runtime/prompt_signature_cache.py",
    },
    "pre_graph_cache": {
        "name": "pre_graph_cache",
        "kind": "RUNTIME_MEMO",
        "golden_requirement": "OPTIONAL",
        "reference_file": "comfymodal_runtime/pre_graph_cache.py",
    },
    "registry_proof_store": {
        "name": "registry_proof_store",
        "kind": "SNAPSHOT_RESIDENT_STATIC_METADATA",
        "golden_requirement": "REQUIRED_HIT",
        "reference_file": "comfymodal_runtime/registry_proof_store.py",
    },
    "experiment_result_store": {
        "name": "experiment_result_store",
        "kind": "REPORTING_STORE",
        "golden_requirement": "OPTIONAL",
        "reference_file": "comfymodal_runtime/experiment_result_store.py",
    },
    "comfyapp_memoized_validation_cache": {
        "name": "comfyapp_memoized_validation_cache",
        "kind": "RUNTIME_MEMO",
        "golden_requirement": "OPTIONAL",
        "reference_file": "comfyapp.py",
    },
    "fast_hydration_state": {
        "name": "fast_hydration_state",
        "kind": "SNAPSHOT_RESIDENT_STATIC_METADATA",
        "golden_requirement": "OPTIONAL",
        "reference_file": "comfymodal_runtime/clip_fast_hydration_wiring.py",
    },
}


def assert_no_hidden_golden_semantic_cache(name: str) -> None:
    """Raise when a taxonomy entry is explicitly forbidden in the golden lane."""
    entry = TAXONOMY.get(name)
    if entry is None:
        raise KeyError(f"unknown cache taxonomy entry: {name}")
    if entry.get("golden_requirement") == "FORBIDDEN":
        raise RuntimeError(f"forbidden golden semantic cache: {name}")


__all__ = ["TAXONOMY", "assert_no_hidden_golden_semantic_cache"]
