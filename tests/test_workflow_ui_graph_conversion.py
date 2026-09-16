"""UI-format workflow graph → API prompt conversion (ZIT file-import path).

File imports arrive as ComfyUI UI-format graphs (``{"nodes": [...], "links":
[...]}``) with no API prompt. ``ui_graph_to_api_prompt`` recovers the
executable prompt server-side so mapping candidates, dependency metadata,
and runnable state work for file-imported workflows exactly as for
canvas-captured ones.

Covers: linked slots become connection specs without consuming widgets;
unconnected widget-backed slots consume widgets_values positionally;
pure-widget nodes (empty UI inputs, e.g. seed selectors) resolve through
the node-def order; unknown classes fall back to the inputs-array pattern;
service-level import stores the derived prompt and drops the
"no executable prompt" reason.
"""

from __future__ import annotations

import pytest

from studio_domain import (
    derive_mapping_candidates,
    extract_dependency_metadata,
    is_ui_workflow_format,
    ui_graph_to_api_prompt,
)

pytestmark = pytest.mark.fast_unit


def fake_defs(class_type: str):
    if class_type == "KSampler":
        return (
            {
                "model": ("MODEL",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "latent_image": ("LATENT",),
                "seed": ("INT", {"min": 0, "max": 2**48, "step": 1}),
                "steps": ("INT", {"min": 1, "max": 150, "step": 1}),
                "cfg": ("FLOAT", {"min": 0.0, "max": 30.0}),
                "sampler_name": (["euler", "dpmpp_2m"],),
                "scheduler": (["normal", "karras"],),
                "denoise": ("FLOAT", {"min": 0.0, "max": 1.0}),
            },
            {},
        )
    if class_type == "CLIPTextEncode":
        return ({"text": ("STRING", {"multiline": True}), "clip": ("CLIP",)}, {})
    if class_type == "CheckpointLoaderSimple":
        return ({"ckpt_name": (["a.safetensors", "b.safetensors"],)}, {})
    if class_type == "SaveImage":
        return ({"images": ("IMAGE",)}, {})
    if class_type == "RandomNoise":
        # Pure-widget node: no linkable slots at all.
        return ({"seed": ("INT", {"min": 0}), "control_after_generate": (["fixed", "random"],)}, {})
    return None


def ui_graph() -> dict:
    return {
        "nodes": [
            {
                "id": 4,
                "type": "CheckpointLoaderSimple",
                "inputs": [],
                "widgets_values": ["a.safetensors"],
            },
            {
                "id": 1,
                "type": "CLIPTextEncode",
                "inputs": [{"name": "clip", "type": "CLIP", "link": 10}],
                "widgets_values": ["hello world"],
            },
            {
                "id": 3,
                "type": "KSampler",
                "inputs": [
                    {"name": "model", "type": "MODEL", "link": 11},
                    {"name": "positive", "type": "CONDITIONING", "link": 12},
                    {"name": "negative", "type": "CONDITIONING", "link": None},
                    {"name": "latent_image", "type": "LATENT", "link": 13},
                ],
                "widgets_values": [7, 20, 8.0, "euler", "normal", 1.0],
            },
            {
                "id": 9,
                "type": "RandomNoise",
                "inputs": [],
                "widgets_values": [123, "fixed"],
            },
            {
                "id": 6,
                "type": "SaveImage",
                "inputs": [{"name": "images", "type": "IMAGE", "link": 14}],
            },
        ],
        "links": [
            [10, 4, 1, 1, 0, "CLIP"],
            [11, 4, 0, 3, 0, "MODEL"],
            [12, 1, 0, 3, 1, "CONDITIONING"],
            [13, 5, 0, 3, 3, "LATENT"],
            [14, 3, 0, 6, 0, "IMAGE"],
        ],
    }


class TestUiFormatDetection:
    def test_detects_ui_format(self):
        assert is_ui_workflow_format({"nodes": [], "links": []}) is True
        assert is_ui_workflow_format({"1": {"class_type": "KSampler"}}) is False
        assert is_ui_workflow_format({}) is False
        assert is_ui_workflow_format(None) is False
        assert is_ui_workflow_format([]) is False


class TestUiGraphConversion:
    def test_linked_slots_become_connections(self):
        prompt = ui_graph_to_api_prompt(ui_graph(), node_def_provider=fake_defs)
        ks = prompt["3"]
        assert ks["class_type"] == "KSampler"
        assert ks["inputs"]["model"] == ["4", 0]
        assert ks["inputs"]["positive"] == ["1", 0]
        assert ks["inputs"]["latent_image"] == ["5", 0]

    def test_unconnected_widgets_consume_positionally(self):
        prompt = ui_graph_to_api_prompt(ui_graph(), node_def_provider=fake_defs)
        ks_inputs = prompt["3"]["inputs"]
        # negative is an unconnected pure slot → None (consumes no widget).
        assert ks_inputs["negative"] is None
        assert ks_inputs["seed"] == 7
        assert ks_inputs["steps"] == 20
        assert ks_inputs["cfg"] == 8.0
        assert ks_inputs["sampler_name"] == "euler"
        assert ks_inputs["scheduler"] == "normal"
        assert ks_inputs["denoise"] == 1.0

    def test_pure_widget_node_resolves_through_defs(self):
        prompt = ui_graph_to_api_prompt(ui_graph(), node_def_provider=fake_defs)
        assert prompt["9"]["inputs"] == {"seed": 123, "control_after_generate": "fixed"}
        # Loader with no UI inputs array entries still recovers its widget.
        assert prompt["4"]["inputs"] == {"ckpt_name": "a.safetensors"}
        assert prompt["1"]["inputs"]["text"] == "hello world"

    def test_unknown_class_falls_back_to_inputs_array(self):
        graph = {
            "nodes": [
                {
                    "id": 7,
                    "type": "MysteryNode",
                    "inputs": [
                        {"name": "model", "type": "MODEL", "link": 1},
                        {"name": "strength", "type": "FLOAT", "widget": {"name": "strength"}, "link": None},
                    ],
                    "widgets_values": [0.5],
                }
            ],
            "links": [[1, 4, 0, 7, 0, "MODEL"]],
        }
        prompt = ui_graph_to_api_prompt(graph, node_def_provider=lambda _c: None)
        assert prompt["7"]["inputs"]["model"] == ["4", 0]
        assert prompt["7"]["inputs"]["strength"] == 0.5

    def test_malformed_nodes_are_skipped_never_raise(self):
        graph = {"nodes": [None, "x", {"no": "id"}, {"id": 1, "type": "", "inputs": []}], "links": ["bad", [1]]}
        assert ui_graph_to_api_prompt(graph, node_def_provider=fake_defs) == {}
        assert ui_graph_to_api_prompt({"nodes": "nope"}, node_def_provider=fake_defs) == {}

    def test_candidates_derive_from_converted_prompt(self):
        prompt = ui_graph_to_api_prompt(ui_graph(), node_def_provider=fake_defs)
        entries, output_node_id = derive_mapping_candidates(
            {"api_prompt_json": prompt}, node_def_provider=fake_defs
        )
        assert output_node_id == "6"
        assert entries["seed"].node_id == "3"
        assert entries["seed"].input_name == "seed"
        assert entries["steps"].node_id == "3"
        assert entries["sampler"].input_name == "sampler_name"
        assert entries["positive_prompt"].node_id == "1"
        assert entries["model"].node_id == "4"


class TestDependencyMetadataCnr:
    def test_cnr_id_propagates_from_ui_graph_and_ignores_comfy_core(self):
        graph = {
            "nodes": [
                {"id": 4, "type": "DonutLoader", "properties": {"cnr_id": "donutnodes"}},
                {"id": 6, "type": "SaveImage", "properties": {"cnr_id": "comfy-core"}},
            ],
        }
        prompt = {
            "4": {"class_type": "DonutLoader", "inputs": {"model_name": "donut.safetensors"}},
            "6": {"class_type": "SaveImage", "inputs": {}},
        }
        meta = extract_dependency_metadata(
            {"graph_json": graph, "api_prompt_json": {"workflow": {}, "output": prompt}}
        )
        assert meta["custom_node_requirements"] == {"DonutLoader": {"cnr_id": "donutnodes"}}
        assert "SaveImage" not in meta["custom_node_requirements"]
        assert meta["node_classes"] == ["DonutLoader", "SaveImage"]

    def test_cnr_id_matches_by_class_when_api_ids_differ(self):
        graph = {
            "nodes": [
                {"id": 99, "type": "DonutLoader", "properties": {"cnr_id": "donutnodes"}}
            ]
        }
        prompt = {"1": {"class_type": "DonutLoader", "inputs": {}}}
        meta = extract_dependency_metadata(
            {"graph_json": graph, "api_prompt_json": {"workflow": {}, "output": prompt}}
        )
        assert meta["custom_node_requirements"]["DonutLoader"]["cnr_id"] == "donutnodes"

    def test_no_cnr_metadata_yields_empty_requirements(self):
        prompt = {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
        meta = extract_dependency_metadata(
            {"graph_json": {"nodes": []}, "api_prompt_json": {"workflow": {}, "output": prompt}}
        )
        assert meta["custom_node_requirements"] == {}

    def test_aux_id_and_version_propagate_from_ui_graph(self):
        graph = {
            "nodes": [
                {
                    "id": 4,
                    "type": "KJNodesLoader",
                    "properties": {"aux_id": "kijai/ComfyUI-KJNodes", "ver": "1.2.3"},
                },
            ],
        }
        prompt = {"4": {"class_type": "KJNodesLoader", "inputs": {}}}
        meta = extract_dependency_metadata(
            {"graph_json": graph, "api_prompt_json": {"workflow": {}, "output": prompt}}
        )
        assert meta["custom_node_requirements"]["KJNodesLoader"] == {
            "aux_id": "kijai/ComfyUI-KJNodes",
            "version": "1.2.3",
        }

    def test_core_node_with_only_version_yields_no_requirement(self):
        """A core node's version is not a custom-node identity."""
        graph = {
            "nodes": [
                {"id": 6, "type": "SaveImage", "properties": {"cnr_id": "comfy-core", "ver": "0.3.0"}},
            ],
        }
        prompt = {"6": {"class_type": "SaveImage", "inputs": {}}}
        meta = extract_dependency_metadata(
            {"graph_json": graph, "api_prompt_json": {"workflow": {}, "output": prompt}}
        )
        assert meta["custom_node_requirements"] == {}

    def test_ui_graph_only_classes_union_into_node_classes(self):
        """UI-only nodes (absent from the executable prompt, e.g. a pack whose
        code failed to load) still surface as dependencies and keep the pack
        identity recorded on the graph node."""
        graph = {
            "nodes": [
                {"id": 4, "type": "DonutLoader", "properties": {"cnr_id": "donutnodes"}},
                {
                    "id": 5,
                    "type": "Krea2IdentityEdit",
                    "properties": {"cnr_id": "krea2_identity_edit"},
                    "inputs": [{"name": "image", "link": None}],
                    "outputs": [{"name": "IMAGE"}],
                },
                {
                    "id": 6,
                    "type": "SeedVarianceEnhancer",
                    "properties": {"aux_id": "owner/SeedVarianceEnhancer", "ver": "2.1.0"},
                    "inputs": [{"name": "model", "link": None}],
                    "outputs": [{"name": "MODEL"}],
                },
            ],
        }
        prompt = {"4": {"class_type": "DonutLoader", "inputs": {}}}
        meta = extract_dependency_metadata(
            {"graph_json": graph, "api_prompt_json": {"workflow": {}, "output": prompt}}
        )
        assert set(meta["node_classes"]) == {
            "DonutLoader",
            "Krea2IdentityEdit",
            "SeedVarianceEnhancer",
        }
        assert meta["custom_node_requirements"]["Krea2IdentityEdit"] == {
            "cnr_id": "krea2_identity_edit"
        }
        assert meta["custom_node_requirements"]["SeedVarianceEnhancer"] == {
            "aux_id": "owner/SeedVarianceEnhancer",
            "version": "2.1.0",
        }

    def test_static_graph_only_classes_union_into_node_classes(self):
        """The ``static_graph`` alias is scanned too (old captures / import)."""
        graph = {
            "nodes": [
                {
                    "id": 9,
                    "type": "BlehNode",
                    "properties": {"aux_id": "bleh/ComfyUI-bleh"},
                    "inputs": [{"name": "x", "link": None}],
                    "outputs": [{"name": "Y"}],
                },
            ],
        }
        meta = extract_dependency_metadata(
            {"static_graph": graph, "api_prompt_json": {"workflow": {}, "output": {}}}
        )
        assert meta["node_classes"] == ["BlehNode"]
        assert meta["custom_node_requirements"]["BlehNode"] == {
            "aux_id": "bleh/ComfyUI-bleh"
        }

    def test_graph_named_widgets_merge_into_model_stack(self):
        graph = {
            "nodes": [
                {
                    "id": 4,
                    "type": "CheckpointLoaderSimple",
                    "inputs": [],
                    "outputs": [{"name": "MODEL"}],
                    "widgets_values_named": {"ckpt_name": "graph_only.safetensors"},
                },
                {
                    "id": 5,
                    "type": "DonutWorkflowPanel",
                    "inputs": [],
                    "outputs": [],
                    "widgets_values_named": {"model_name": "ghost.safetensors"},
                },
            ],
        }
        meta = extract_dependency_metadata(
            {"graph_json": graph, "api_prompt_json": {"workflow": {}, "output": {}}}
        )
        assert meta["model_stack"] == {"checkpoint": ["graph_only.safetensors"]}

    def test_nested_graph_classes_and_identities_surface(self):
        """Manager-missing nodes nested under subgraph/group containers still
        union into node_classes and keep their captured pack identity."""
        graph = {
            "nodes": [
                {"id": 1, "type": "TopNode", "properties": {"cnr_id": "top-pack"},
                 "inputs": [], "outputs": [{"name": "OUT"}]},
            ],
            "definitions": {
                "subgraphs": [
                    {
                        "id": "sg",
                        "nodes": [
                            {
                                "id": 2,
                                "type": "NestedAlphaNode",
                                "properties": {"cnr_id": "nested-pack", "ver": "1.2.3"},
                                "inputs": [{"name": "model", "link": None}],
                                "outputs": [{"name": "MODEL"}],
                            },
                            {
                                "id": 3,
                                "type": "NestedBetaNode",
                                "properties": {"aux_id": "owner/nested-beta"},
                                "inputs": [{"name": "x", "link": None}],
                                "outputs": [{"name": "Y"}],
                            },
                        ],
                    }
                ]
            },
            "extra": {
                "groupNodes": {
                    "g": {
                        "nodes": [
                            {
                                "id": 4,
                                "type": "NestedGammaNode",
                                "properties": {"cnr_id": "nested-pack"},
                                "inputs": [{"name": "x", "link": None}],
                                "outputs": [{"name": "Y"}],
                            }
                        ]
                    }
                }
            },
        }
        meta = extract_dependency_metadata(
            {"graph_json": graph, "api_prompt_json": {"workflow": {}, "output": {}}}
        )
        assert {"TopNode", "NestedAlphaNode", "NestedBetaNode", "NestedGammaNode"}.issubset(
            set(meta["node_classes"])
        )
        assert meta["custom_node_requirements"]["NestedAlphaNode"] == {
            "cnr_id": "nested-pack",
            "version": "1.2.3",
        }
        assert meta["custom_node_requirements"]["NestedBetaNode"] == {
            "aux_id": "owner/nested-beta"
        }
        assert meta["custom_node_requirements"]["NestedGammaNode"] == {
            "cnr_id": "nested-pack"
        }

    def test_nested_virtual_panel_not_a_requirement(self):
        """A nested empty-panel node with no pack identity is not a pack."""
        graph = {
            "nodes": [],
            "definitions": {
                "subgraphs": [
                    {
                        "id": "sg",
                        "nodes": [
                            {
                                "id": 1,
                                "type": "NestedPanel",
                                "properties": {},
                                "inputs": [],
                                "outputs": [],
                            }
                        ],
                    }
                ]
            },
        }
        meta = extract_dependency_metadata(
            {"graph_json": graph, "api_prompt_json": {"workflow": {}, "output": {}}}
        )
        assert "NestedPanel" not in meta["custom_node_requirements"]

    def test_graph_and_prompt_model_refs_both_preserved(self):
        graph = {
            "nodes": [
                {
                    "id": 4,
                    "type": "DonutLoader",
                    "inputs": [{"name": "clip", "link": None}],
                    "outputs": [{"name": "MODEL"}],
                    "widgets_values_named": {"vae_file": "graph_vae.safetensors"},
                },
            ],
        }
        prompt = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "prompt_unet.safetensors"}},
        }
        meta = extract_dependency_metadata(
            {"graph_json": graph, "api_prompt_json": {"workflow": {}, "output": prompt}}
        )
        assert "prompt_unet.safetensors" in meta["model_stack"]["unet"]
        assert "graph_vae.safetensors" in meta["model_stack"]["vae"]


class TestServiceImportDerivesPrompt:
    def _service(self, tmp_path):
        from studio_domain import WorkflowDomainService

        return WorkflowDomainService(str(tmp_path), node_def_provider=fake_defs)

    def test_import_ui_graph_stores_executable_prompt(self, tmp_path):
        service = self._service(tmp_path)
        wf = service.create_workflow("UI Import")
        version = service.create_version_from_capture(
            wf["workflow_id"],
            {"graph_json": ui_graph(), "api_prompt_json": {}},
        )
        assert version["executable_prompt"]["3"]["class_type"] == "KSampler"
        assert version["api_prompt_json"]["3"]["inputs"]["seed"] == 7
        state = service.derive_version_state(version["workflow_version_id"])
        # Executable prompt present → only the mapping reason remains.
        assert state.reasons == ["missing mapping"]
        assert state.runnable is False

    def test_import_api_capture_unchanged(self, tmp_path):
        service = self._service(tmp_path)
        wf = service.create_workflow("API Import")
        prompt = {"3": {"class_type": "KSampler", "inputs": {"seed": 5}}}
        version = service.create_version_from_capture(
            wf["workflow_id"],
            {"graph_json": {}, "api_prompt_json": prompt},
        )
        assert version["executable_prompt"] == prompt

    def test_import_empty_graph_stays_incomplete(self, tmp_path):
        service = self._service(tmp_path)
        wf = service.create_workflow("Empty Import")
        version = service.create_version_from_capture(
            wf["workflow_id"],
            {"graph_json": {"id": "g1", "nodes": []}, "api_prompt_json": {}},
        )
        state = service.derive_version_state(version["workflow_version_id"])
        assert "no executable prompt" in state.reasons
