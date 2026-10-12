from __future__ import annotations

import tempfile

import pytest

from studio_domain import WorkflowDomainService, WorkflowDomainValidationError
from studio_domain.models import Mapping
from studio_workflow_run import (
    _build_plan_replay_meta,
    prepare_effective_prompt,
)


pytestmark = pytest.mark.fast_unit


def _prompt(*, secondary: bool = False, prompt_value: object = "literal") -> dict:
    workflow = {
        "text": {
            "class_type": "TextGenerate",
            "inputs": {"prompt": prompt_value},
        },
        "consumer": {
            "class_type": "Consumer",
            "inputs": {"text": ["text", 0]},
        },
        "output": {"class_type": "SaveImage", "inputs": {"images": ["consumer", 0]}},
    }
    if secondary:
        workflow["consumer"]["inputs"]["thinking"] = ["text", 1]
    return workflow


def test_mapping_round_trip_revision_and_old_records_default_unbound():
    assert Mapping.from_dict({"mapping_id": "m", "workflow_version_id": "v"}).to_dict()[
        "text_generate_node_id"
    ] is None
    with tempfile.TemporaryDirectory() as root:
        service = WorkflowDomainService(root)
        workflow = service.create_workflow("Text")
        version = service.create_version_from_capture(
            workflow["workflow_id"],
            {"graph_json": {"nodes": []}, "api_prompt_json": {"workflow": {}, "output": _prompt()}},
        )
        version_id = version["workflow_version_id"]
        service.set_mapping(
            version_id,
            entries={},
            output_node_id="output",
            text_generate_node_id="text",
        )
        stored = service.get_mapping(version_id)
        assert stored["text_generate_node_id"] == "text"
        revised = service.create_mapping_revision(
            version_id, entries={}, output_node_id="output", text_generate_node_id=None
        )
        assert service.get_mapping(version_id)["text_generate_node_id"] == "text"
        assert service.get_mapping(revised["workflow_version_id"])["text_generate_node_id"] is None


def test_mapping_rejects_bad_target_and_consumed_secondary_output():
    with tempfile.TemporaryDirectory() as root:
        service = WorkflowDomainService(root)
        workflow = service.create_workflow("Text")

        def make_version(prompt):
            return service.create_version_from_capture(
                workflow["workflow_id"],
                {"graph_json": {"nodes": []}, "api_prompt_json": {"workflow": {}, "output": prompt}},
            )["workflow_version_id"]

        bad_id = make_version({"text": {"class_type": "Other", "inputs": {"prompt": "x"}},
                               "output": {"class_type": "SaveImage", "inputs": {}}})
        with pytest.raises(WorkflowDomainValidationError, match="TextGenerate"):
            service.set_mapping(bad_id, entries={}, output_node_id="output", text_generate_node_id="text")

        secondary_id = make_version(_prompt(secondary=True))
        with pytest.raises(WorkflowDomainValidationError, match="secondary"):
            service.set_mapping(
                secondary_id, entries={}, output_node_id="output", text_generate_node_id="text"
            )


def _prompt_schema(role="prompt"):
    return {role: {"node_id": "text", "input_name": "prompt"}}


def test_bypass_replaces_literal_and_linked_prompt_without_mutating_source():
    literal = _prompt()
    result = prepare_effective_prompt(
        literal, {}, {}, {"text_generate_node_id": "text"}, {"skip_text_generate": True}
    )
    assert result["workflow"]["consumer"]["inputs"]["text"] == "literal"
    assert "text" not in result["workflow"]
    assert "text" in literal

    linked = _prompt(prompt_value=["upstream", 0])
    result = prepare_effective_prompt(
        linked, {}, {}, {"text_generate_node_id": "text"}, {"skip_text_generate": True}
    )
    assert result["workflow"]["consumer"]["inputs"]["text"] == ["upstream", 0]


def test_skip_requires_valid_stored_binding_and_replay_identity_records_intent():
    missing = prepare_effective_prompt(
        _prompt(), {}, {}, {"text_generate_node_id": None}, {"skip_text_generate": True}
    )
    assert "no bound node" in missing["error"]
    invalid_bool = prepare_effective_prompt(
        _prompt(), {}, {}, {"text_generate_node_id": "text"}, {"skip_text_generate": 1}
    )
    assert "must be a boolean" in invalid_bool["error"]

    class Plan:
        def to_dict(self):
            return {
                "workflow": _prompt(),
                "workflow_hash": "after-bypass",
                "request_metadata": {
                    "workflow_id": "wf",
                    "workflow_version_id": "v2",
                    "skip_text_generate": True,
                    "text_generate_node_id": "text",
                },
            }

    replay = _build_plan_replay_meta(Plan(), {"skip_text_generate": True})
    assert replay["skip_text_generate"] is True
    assert replay["text_generate_node_id"] == "text"
    assert replay["request_json"]["request_metadata"]["text_generate_node_id"] == "text"


def test_bypass_prefers_shelf_prompt_over_node_template():
    workflow = _prompt(prompt_value=["template_node", 0])
    workflow["template_node"] = {
        "class_type": "Template",
        "inputs": {"text": "TEMPLATE prefix: rewrite this idea"},
    }
    schema = _prompt_schema()
    result = prepare_effective_prompt(
        workflow,
        schema,
        {"prompt": "closeup portrait photo of a gorgeous Romanian 20yo woman"},
        {"text_generate_node_id": "text"},
        {"skip_text_generate": True},
    )
    assert result["workflow"]["consumer"]["inputs"]["text"] == (
        "closeup portrait photo of a gorgeous Romanian 20yo woman"
    )
    assert result["studio_meta"]["text_generate_prompt_source"] == "shelf"
    assert "text" not in result["workflow"]


def test_bypass_prefers_shelf_prompt_through_positive_prompt_alias():
    workflow = _prompt(prompt_value="TEMPLATE prefix: rewrite this idea")
    schema = _prompt_schema("positive_prompt")
    result = prepare_effective_prompt(
        workflow,
        schema,
        {"positive_prompt": "shelf text via alias"},
        {"text_generate_node_id": "text"},
        {"skip_text_generate": True},
    )
    assert result["workflow"]["consumer"]["inputs"]["text"] == "shelf text via alias"
    assert result["studio_meta"]["text_generate_prompt_source"] == "shelf"


def test_bypass_falls_back_to_node_input_without_shelf_prompt():
    workflow = _prompt(prompt_value="node template text")
    result = prepare_effective_prompt(
        workflow, {}, {}, {"text_generate_node_id": "text"}, {"skip_text_generate": True}
    )
    assert result["workflow"]["consumer"]["inputs"]["text"] == "node template text"
    assert result["studio_meta"]["text_generate_prompt_source"] == "node_input"

    non_string = prepare_effective_prompt(
        _prompt(prompt_value="node template text"),
        _prompt_schema(),
        {"prompt": None},
        {"text_generate_node_id": "text"},
        {"skip_text_generate": True},
    )
    assert non_string["workflow"]["consumer"]["inputs"]["text"] == "node template text"
    assert non_string["studio_meta"]["text_generate_prompt_source"] == "node_input"
