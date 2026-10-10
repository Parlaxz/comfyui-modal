"""Focused regressions for live UI-workflow compatibility."""

from __future__ import annotations

import sys
import types
from unittest.mock import patch

import pytest

import studio_workflow_run as swr
from studio_domain.models import MappingEntry


pytestmark = pytest.mark.fast_unit


def _entry(role: str, node_id: str, input_name: str, **kwargs) -> MappingEntry:
    return MappingEntry(
        semantic_role=role,
        node_id=node_id,
        input_name=input_name,
        **kwargs,
    )


def test_ui_refresh_preserves_aliases_and_refreshes_stale_metadata():
    stored = [
        {
            "semantic_role": "cfg_scale",
            "node_id": "163",
            "input_name": "cfg",
            "control_kind": "string",
            "minimum": None,
        },
        {
            "semantic_role": "clip",
            "node_id": "195",
            "input_name": "clip_name",
            "control_kind": "string",
        },
    ]
    fresh = {
        "cfg": _entry("cfg", "163", "cfg", control_kind="number", minimum=0.0),
        "model": _entry("model", "194", "unet_name", control_kind="file"),
        "model_clip": _entry("model", "195", "clip_name", control_kind="file"),
        "steps": _entry("steps", "163", "steps", control_kind="integer"),
        "sampler": _entry(
            "sampler", "163", "sampler_name", control_kind="enum",
            enum_options=["euler"],
        ),
    }
    regenerated = {
        "163": {"class_type": "KSampler", "inputs": {
            "cfg": 6.5, "steps": 18, "sampler_name": "euler",
        }},
        "194": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "krea2_turbo_fp8_scaled.safetensors",
        }},
        "195": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "clip.safetensors",
        }},
    }
    bundle = {
        "version": {"graph_json": {"nodes": [{"id": 163}]}},
        "mapping": {"entries": stored, "output_node_id": "old-output"},
        "executable_prompt": {},
        "control_schema": {},
        "defaults": {},
    }
    with patch("studio_domain.graph.ui_graph_to_api_prompt", return_value=regenerated), \
         patch("studio_domain.graph.derive_mapping_candidates", return_value=(fresh, "213")):
        refreshed = swr._refresh_ui_workflow_bundle(bundle)

    entries = {entry["semantic_role"]: entry for entry in refreshed["mapping"]["entries"]}
    assert set(entries) == {"cfg_scale", "clip", "model", "steps", "sampler"}
    assert "cfg" not in entries
    assert entries["cfg_scale"]["control_kind"] == "number"
    assert entries["cfg_scale"]["minimum"] == 0.0
    assert entries["clip"]["control_kind"] == "file"
    assert refreshed["control_schema"] is not None
    assert refreshed["defaults"]["cfg_scale"] == 6.5
    assert refreshed["defaults"]["sampler"] == "euler"
    assert refreshed["mapping"]["output_node_id"] == "213"


def test_ui_refresh_preserves_stored_output_node_when_regenerated_graph_contains_it():
    regenerated = {
        "6": {"class_type": "SaveImage", "inputs": {}},
        "7": {"class_type": "SaveImage", "inputs": {}},
    }
    bundle = {
        "version": {"graph_json": {"nodes": [{"id": 6}, {"id": 7}]}},
        "mapping": {"entries": [], "output_node_id": "7"},
        "executable_prompt": {},
        "control_schema": {},
        "defaults": {},
    }
    with patch("studio_domain.graph.ui_graph_to_api_prompt", return_value=regenerated), \
         patch("studio_domain.graph.derive_mapping_candidates", return_value=({}, "6")):
        refreshed = swr._refresh_ui_workflow_bundle(bundle)

    assert refreshed["mapping"]["output_node_id"] == "7"


def test_ui_refresh_skips_subgraph_nested_graphs():
    """Subgraph workflows keep the stored expanded prompt.

    Regression: regenerating the prompt from the top-level UI graph drops
    every ``"<outer>:<inner>"`` node, wiping stored bindings and surfacing
    as ``missing required control 'clip'`` in the playground.
    """
    stored_prompt = {
        "30:11": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
        "29": {"class_type": "SaveImage", "inputs": {"images": ["30:3", 0]}},
    }
    stored_entries = [
        {"semantic_role": "clip", "node_id": "30:11", "input_name": "clip_name", "control_kind": "file"},
    ]
    bundle = {
        "version": {"graph_json": {
            "nodes": [{"id": 30, "type": "sg-1"}, {"id": 29, "type": "SaveImage"}],
            "definitions": {"subgraphs": [{"id": "sg-1", "nodes": [{"id": 11}]}]},
        }},
        "mapping": {"entries": stored_entries, "output_node_id": "29"},
        "executable_prompt": stored_prompt,
        "control_schema": {"clip": stored_entries[0]},
        "defaults": {"clip": "clip.safetensors"},
    }
    with patch(
        "studio_domain.graph.ui_graph_to_api_prompt",
        side_effect=AssertionError("must not regenerate nested graphs"),
    ):
        refreshed = swr._refresh_ui_workflow_bundle(bundle)

    assert refreshed["executable_prompt"] == stored_prompt
    assert refreshed["defaults"] == {"clip": "clip.safetensors"}
    assert swr.merge_workflow_controls(
        refreshed["defaults"], {}, refreshed["control_schema"]
    )["errors"] == []


def test_ui_refresh_skips_when_regeneration_drops_stored_binding():
    """Safety net: never replace the prompt when a stored target is lost."""
    stored_prompt = {
        "163": {"class_type": "KSampler", "inputs": {"cfg": 6.5}},
    }
    stored_entries = [
        {"semantic_role": "cfg_scale", "node_id": "163", "input_name": "cfg", "control_kind": "number"},
    ]
    bundle = {
        "version": {"graph_json": {"nodes": [{"id": 163}]}},
        "mapping": {"entries": stored_entries, "output_node_id": ""},
        "executable_prompt": stored_prompt,
        "control_schema": {"cfg_scale": stored_entries[0]},
        "defaults": {"cfg_scale": 6.5},
    }
    pruned = {"163": {"class_type": "KSampler", "inputs": {}}}
    with patch("studio_domain.graph.ui_graph_to_api_prompt", return_value=pruned), \
         patch("studio_domain.graph.derive_mapping_candidates", return_value=({}, "")):
        refreshed = swr._refresh_ui_workflow_bundle(bundle)

    assert refreshed["executable_prompt"] == stored_prompt
    assert refreshed["defaults"] == {"cfg_scale": 6.5}


def test_sampler_null_override_keeps_regenerated_graph_default():
    schema = {
        "sampler": {
            "node_id": "163",
            "input_name": "sampler_name",
            "enum_options": ["euler"],
        },
    }
    merged = swr.merge_workflow_controls(
        {"sampler": "euler"}, {"sampler": None}, schema,
    )
    assert merged["errors"] == []
    assert merged["values"]["sampler"] == "euler"


def test_model_loader_normalization_drops_krea_subfolder_prefix():
    workflow = {
        "194": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": r"krea2\krea2_turbo_fp8_scaled.safetensors"},
        },
        "195": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": "clip.safetensors"},
        },
    }
    swr._normalize_model_loader_names(workflow)
    assert workflow["194"]["inputs"]["unet_name"] == "krea2_turbo_fp8_scaled.safetensors"
    merged = swr.merge_workflow_controls(
        {},
        {"model_unet": r"krea2\krea2_turbo_fp8_scaled.safetensors"},
        {"model_unet": {
            "input_name": "unet_name",
            "enum_options": ["krea2_turbo_fp8_scaled.safetensors"],
        }},
    )
    assert merged["errors"] == []
    assert merged["values"]["model_unet"] == "krea2_turbo_fp8_scaled.safetensors"


def test_required_image_is_only_hydrated_from_explicit_schema_default(monkeypatch):
    class InputNode:
        @classmethod
        def INPUT_TYPES(cls):
            return {
                "required": {
                    "image": ("IMAGE",),
                    "filename_prefix": ("STRING", {"default": "ComfyUI"}),
                    "mode": (["first", "second"],),
                },
            }

    fake_nodes = types.ModuleType("nodes")
    setattr(fake_nodes, "NODE_CLASS_MAPPINGS", {"InputNode": InputNode})
    monkeypatch.setitem(sys.modules, "nodes", fake_nodes)

    workflow = {"1": {"class_type": "InputNode", "inputs": {"image": None}}}
    evidence = swr._hydrate_missing_required_widget_defaults(workflow)

    assert workflow["1"]["inputs"]["image"] is None
    assert workflow["1"]["inputs"]["filename_prefix"] == "ComfyUI"
    assert "mode" not in workflow["1"]["inputs"]
    assert swr.merge_workflow_controls(
        {}, {}, {"source_image": {"required": True}},
    )["errors"]
    assert {item["input"] for item in evidence["hydrated"]} == {"filename_prefix"}


def test_stale_string_override_for_number_control_falls_back_to_default():
    schema = {
        "cfg_scale": {
            "node_id": "163",
            "input_name": "cfg",
            "control_kind": "number",
        },
    }
    merged = swr.merge_workflow_controls(
        {"cfg_scale": 8.0}, {"cfg_scale": "fixed"}, schema,
    )
    assert merged["errors"] == []
    assert merged["values"]["cfg_scale"] == 8.0


def test_numeric_string_override_for_number_control_preserved_verbatim():
    schema = {
        "cfg_scale": {
            "node_id": "163",
            "input_name": "cfg",
            "control_kind": "number",
        },
    }
    merged = swr.merge_workflow_controls(
        {"cfg_scale": 8.0}, {"cfg_scale": "7.5"}, schema,
    )
    assert merged["errors"] == []
    assert merged["values"]["cfg_scale"] == "7.5"
