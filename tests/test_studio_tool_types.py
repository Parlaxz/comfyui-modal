"""Tool-type profiles for the Studio image workspace (Slice B-G).

Proves the code-owned catalog generalizes from T2I-only to five
workflow-backed image tools without duplicating Prompt/Seed/Model inputs.
"""

from __future__ import annotations

import pytest

from studio_domain.services import (
    BINDABLE_INPUT_CATALOG,
    I2I_OPTIONAL_INPUTS,
    I2I_REQUIRED_INPUTS,
    INPAINT_OPTIONAL_INPUTS,
    INPAINT_REQUIRED_INPUTS,
    OUTPAINT_OPTIONAL_INPUTS,
    OUTPAINT_REQUIRED_INPUTS,
    OUTPUT_BINDING,
    SKETCH_OPTIONAL_INPUTS,
    SKETCH_REQUIRED_INPUTS,
    T2I_OPTIONAL_INPUTS,
    T2I_REQUIRED_INPUTS,
    WORKFLOW_TYPE_PROFILES,
    normalize_workflow_type,
)


pytestmark = pytest.mark.fast_unit


def test_t2i_profile_unchanged():
    # The original T2I contract is a subset that must keep working; other
    # lanes may extend the optional set (e.g. width/height) additively.
    assert tuple(T2I_REQUIRED_INPUTS) == ("prompt", "seed", "model_unet", "vae", "clip")
    for role in ("step_count", "cfg_scale", "sampler"):
        assert role in tuple(T2I_OPTIONAL_INPUTS)
    assert WORKFLOW_TYPE_PROFILES["t2i"]["required"] == T2I_REQUIRED_INPUTS


def test_all_five_workflow_types_have_profiles():
    assert set(WORKFLOW_TYPE_PROFILES) == {"t2i", "i2i", "inpaint", "sketch", "outpaint"}
    assert WORKFLOW_TYPE_PROFILES["i2i"]["required"] == I2I_REQUIRED_INPUTS
    assert WORKFLOW_TYPE_PROFILES["inpaint"]["required"] == INPAINT_REQUIRED_INPUTS
    assert WORKFLOW_TYPE_PROFILES["sketch"]["required"] == SKETCH_REQUIRED_INPUTS
    assert WORKFLOW_TYPE_PROFILES["outpaint"]["required"] == OUTPAINT_REQUIRED_INPUTS


def test_shared_inputs_reused_not_duplicated():
    for role in ("prompt", "seed", "model_unet", "vae", "clip"):
        required_for = BINDABLE_INPUT_CATALOG[role]["required_for"]
        for tool in ("t2i", "i2i", "inpaint", "sketch", "outpaint"):
            assert tool in required_for, f"{role} must be shared by {tool}"
    assert "i2i_prompt" not in BINDABLE_INPUT_CATALOG
    assert "inpaint_prompt" not in BINDABLE_INPUT_CATALOG


def test_source_image_and_mask_first_class():
    assert BINDABLE_INPUT_CATALOG["source_image"]["input_kind"] == "image"
    assert set(BINDABLE_INPUT_CATALOG["source_image"]["required_for"]) == {
        "i2i", "inpaint", "sketch", "outpaint",
    }
    assert BINDABLE_INPUT_CATALOG["mask"]["required_for"] == ("inpaint",)
    assert set(BINDABLE_INPUT_CATALOG["mask"]["optional_for"]) == {"sketch", "outpaint"}
    assert "source_image" in I2I_REQUIRED_INPUTS
    assert "mask" in INPAINT_REQUIRED_INPUTS


def test_output_required_for_all_types():
    for tool in ("t2i", "i2i", "inpaint", "sketch", "outpaint"):
        assert tool in OUTPUT_BINDING["required_for"]


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [("txt2img", "t2i"), ("t2i", "t2i"), ("img2img", "i2i"), ("image_edit", "i2i"),
     ("inpaint", "inpaint"), ("sketch", "sketch"), ("outpaint", "outpaint")],
)
def test_workflow_type_aliases(raw, canonical):
    assert normalize_workflow_type(raw) == canonical


def test_normalize_applies_at_durable_config_boundary(tmp_path):
    from studio_domain.services import WorkflowDomainService

    svc = WorkflowDomainService(str(tmp_path))
    normalized = svc._normalize_workflow_config(
        {"workflow_type": "image_edit", "static_graph": {}, "bindings": {}, "output_binding": {}},
    )
    assert normalized["workflow_type"] == "i2i"
    # An aliased type resolves to a real profile, so completeness gating
    # cannot be bypassed by a non-canonical spelling.
    with pytest.raises(Exception):
        svc._normalize_workflow_config(
            {"workflow_type": "image_edit", "static_graph": {}, "bindings": {}, "output_binding": {}},
            require_complete=True,
        )


def test_input_image_bytes_collected_from_node_dir(tmp_path):
    """Uploaded source/mask files must reach the remote loader.

    The run adapter forwards its node directory; the collector must still
    resolve `<ComfyUI>/input` (two parents up) and must cover any node
    consuming `image`/`mask` inputs — not only LoadImage*.
    """
    import base64

    from canonical_execution import _collect_input_images

    payload = b"studio-source-bytes"
    comfy_root = tmp_path / "ComfyUI"
    (comfy_root / "input").mkdir(parents=True)
    (comfy_root / "input" / "studio-current-abc123.png").write_bytes(payload)
    node_dir = comfy_root / "custom_nodes" / "comfyui-modal"
    node_dir.mkdir(parents=True)

    workflow = {
        "10": {
            "class_type": "PixaromaLoadImageMini",
            "inputs": {"image": "studio-current-abc123.png"},
        },
        "11": {"class_type": "KSampler", "inputs": {"seed": 1}},
    }
    images = _collect_input_images(workflow, str(node_dir))
    assert list(images) == ["studio-current-abc123.png"]
    assert base64.b64decode(images["studio-current-abc123.png"]) == payload


def test_input_image_bytes_collected_for_mask_key(tmp_path):
    import base64

    from canonical_execution import _collect_input_images

    payload = b"studio-mask-bytes"
    comfy_root = tmp_path / "ComfyUI"
    (comfy_root / "input").mkdir(parents=True)
    (comfy_root / "input" / "studio-mask-abc123.png").write_bytes(payload)

    workflow = {
        "11": {
            "class_type": "SomeCustomMaskLoader",
            "inputs": {"mask": "studio-mask-abc123.png"},
        },
    }
    images = _collect_input_images(workflow, str(comfy_root))
    assert list(images) == ["studio-mask-abc123.png"]
    assert base64.b64decode(images["studio-mask-abc123.png"]) == payload


def test_input_image_collection_rejects_escape(tmp_path):
    from canonical_execution import _collect_input_images

    # An annotated `..` reference resolving to an EXISTING file outside the
    # searched roots must not be read (realpath containment, not just `..`
    # component rejection, which annotated paths bypass).
    deep = tmp_path / "deep" / "n1" / "n2"
    deep.mkdir(parents=True)
    (tmp_path / "evil.png").write_bytes(b"must-not-read")

    workflow = {
        "10": {
            "class_type": "LoadImage",
            "inputs": {"image": "../../../../evil.png [input]"},
        },
    }
    assert _collect_input_images(workflow, str(deep)) == {}


def _image_entry(role, required=True):
    return {
        "semantic_role": role,
        "node_id": "10",
        "input_name": "image" if role == "source_image" else "mask",
        "control_kind": "image",
        # Stale directory snapshot: the uploaded file is NOT listed.
        "enum_options": ["old_a.png", "old_b.png"],
        "required": required,
    }


def test_image_roles_ignore_stale_enum_options():
    """Ahmed's live failure: a fresh upload must not be rejected against a
    stale input-directory listing captured at mapping time."""
    from studio_workflow_run import validate_workflow_controls

    schema = {
        "source_image": _image_entry("source_image"),
        "mask": _image_entry("mask"),
        "sampler": {
            "semantic_role": "sampler",
            "node_id": "3",
            "input_name": "sampler_name",
            "control_kind": "enum",
            "enum_options": ["euler", "dpmpp_2m"],
            "required": False,
        },
    }
    errors = validate_workflow_controls(
        {"source_image": "studio-current-fresh123.png", "mask": "studio-mask-fresh123.png",
         "sampler": "euler"},
        schema,
    )
    assert errors == []
    # True closed vocabularies stay strict.
    errors = validate_workflow_controls({"sampler": "not_a_sampler"}, schema)
    assert [e["field"] for e in errors] == ["sampler"]
    # Required-ness still applies to image roles.
    errors = validate_workflow_controls({"source_image": "   "}, schema)
    assert [e["field"] for e in errors] == ["source_image"]


def test_domain_image_roles_ignore_stale_enum():
    from studio_domain.services import WorkflowDomainService
    from studio_domain.models import MappingEntry

    entry = MappingEntry(
        semantic_role="source_image", node_id="10", input_name="image",
        control_kind="enum", enum_options=["old_a.png"],
    )
    assert WorkflowDomainService._validate_value("source_image", "fresh.png", entry) is None
    entry2 = MappingEntry(
        semantic_role="sampler", node_id="3", input_name="sampler_name",
        control_kind="enum", enum_options=["euler"],
    )
    assert WorkflowDomainService._validate_value("sampler", "nope", entry2) is not None


def test_missing_required_binding_blocks_runnable(tmp_path):
    """Ahmed's live trap: an i2i version saved without Source Image must
    report unrunnable with an explicit reason, not 'ready'."""
    import tempfile

    from studio_domain import (
        WorkflowDomainService,
        derive_mapping_candidates,
        graph_hash_from_capture,
        resolve_binding_target,
    )
    from studio_domain.services import WorkflowDomainService as _Service

    root = tempfile.mkdtemp()
    svc = WorkflowDomainService(root)
    wf = svc.create_workflow("I2I", workflow_type="i2i")
    prompt = {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello world", "clip": ["4", 0]}},
        "3": {"class_type": "KSampler", "inputs": {
            "model": ["4", 0], "seed": 0, "steps": 20, "cfg": 7.0,
            "sampler_name": "euler", "scheduler": "normal",
            "positive": ["1", 0], "negative": ["1", 0], "latent_image": ["5", 0],
            "denoise": 1.0}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "krea_model.safetensors"}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["3", 0]}},
    }
    capture = {
        "graph_json": {"id": "g1", "nodes": []},
        "api_prompt_json": {"workflow": {}, "output": prompt},
    }
    version = svc.create_version_from_capture(wf["workflow_id"], capture)

    def node_def(class_type: str):
        if class_type == "KSampler":
            return (
                {
                    "seed": ("INT", {"min": 0, "step": 1, "default": 0}),
                    "steps": ("INT", {"min": 1, "step": 1, "default": 20}),
                    "cfg": ("FLOAT", {"min": 0.0, "step": 0.5, "default": 7.0}),
                    "sampler_name": (["euler", "dpmpp_2m"],),
                },
                {},
            )
        if class_type == "CLIPTextEncode":
            return ({"text": ("STRING", {"multiline": True})}, {})
        if class_type == "CheckpointLoaderSimple":
            return ({"ckpt_name": (["krea_model.safetensors"],)}, {})
        return None

    entries, output_node_id = derive_mapping_candidates(capture, node_def_provider=node_def)
    stored = {
        role: e.to_dict()
        for role, e in entries.items()
        if role in ("positive_prompt", "seed", "model", "steps", "cfg", "sampler")
    }
    svc.set_mapping(
        version["workflow_version_id"], entries=stored, output_node_id=output_node_id,
    )
    state = svc.derive_version_state(version["workflow_version_id"])
    assert not state.runnable
    assert any("source_image" in r for r in state.reasons)


def _dropdown_workflow(state_value):
    return {
        "6": {
            "class_type": "PixaromaDropdown",
            "inputs": {"DropdownState": state_value},
        },
        "15": {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": ["5", 0],
                "upscale_method": "nearest-exact",
                "megapixels": ["6", 0],
                "resolution_steps": 32,
            },
        },
    }


def test_empty_dropdown_link_repaired_not_failed():
    """An unconfigured dropdown feeding a numeric input is completed from the
    target's own default (topology preserved) instead of crashing remotely."""
    import copy
    import json

    from studio_workflow_run import _repair_empty_dropdown_links

    wf = _dropdown_workflow("")
    repairs = _repair_empty_dropdown_links(wf)
    assert len(repairs) == 1
    assert repairs[0]["target_node_id"] == "15"
    assert repairs[0]["source_node_id"] == "6"
    # The link is intact; only the provably-empty state blob is completed,
    # in the browser's own LEAN wire format.
    assert wf["15"]["inputs"]["megapixels"] == ["6", 0]
    state = json.loads(wf["6"]["inputs"]["DropdownState"])
    assert state["type"] == "float" and state["value"] == 1.0


def test_configured_dropdown_link_passes_through():
    from studio_workflow_run import _repair_empty_dropdown_links

    assert _repair_empty_dropdown_links(_dropdown_workflow('{"type": "float", "value": 1.0}')) == []
    # Literal megapixels need no dropdown at all.
    wf = _dropdown_workflow("")
    wf["15"]["inputs"]["megapixels"] = 1.0
    assert _repair_empty_dropdown_links(wf) == []
    # Unrelated graphs are untouched.
    assert _repair_empty_dropdown_links({"1": {"class_type": "KSampler", "inputs": {"seed": 0}}}) == []
    assert _repair_empty_dropdown_links({}) == []
