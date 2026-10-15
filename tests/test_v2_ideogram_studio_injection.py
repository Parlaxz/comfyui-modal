"""FAST_UNIT: host-side Studio-workflow injection for the isolated Ideogram profile.

Proves the ``__init__._execute_job`` plan-build seam contract without ComfyUI,
Modal, or GPU: (a) inactive without flags (production plan untouched),
(b) active path yields the Studio API graph (DualModelGuider + both INT8
UNET names + steps 16 + euler + Ideogram4Scheduler) with steps provenance,
(c) any selection/invariant mismatch fails closed with GateError.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.fast_unit

from tools.v2_control.errors import GateError

import ideogram_studio_injection as inj


PROFILE = inj.PROFILE
WID = inj.WORKFLOW_ID
WVER = inj.WORKFLOW_VERSION_ID

ENV_KEYS = (
    inj.PROFILE_ENV,
    inj.WORKFLOW_ID_ENV,
    inj.WORKFLOW_VERSION_ENV,
    inj.WORKFLOW_STEPS_ENV,
)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _arm(monkeypatch, *, profile=True, steps="16",
         wid=WID, wver=WVER):
    if profile:
        monkeypatch.setenv(inj.PROFILE_ENV, PROFILE)
    if wid is not None:
        monkeypatch.setenv(inj.WORKFLOW_ID_ENV, wid)
    if wver is not None:
        monkeypatch.setenv(inj.WORKFLOW_VERSION_ENV, wver)
    if steps is not None:
        monkeypatch.setenv(inj.WORKFLOW_STEPS_ENV, steps)


def _production_stub() -> dict:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "production.safetensors"},
        },
    }


def _unet_names(prompt: dict) -> list:
    return sorted(
        str(node.get("inputs", {}).get("unet_name") or "")
        for node in prompt.values()
        if isinstance(node, dict) and node.get("class_type") == "UNETLoader"
    )


def test_inactive_without_flags_returns_plan_untouched():
    stub = _production_stub()
    out, selection = inj.maybe_inject_ideogram_studio_workflow(stub)
    assert out is stub
    assert selection == {"active": False}
    assert stub == _production_stub()


def test_inactive_for_other_profiles():
    stub = _production_stub()
    out, selection = inj.maybe_inject_ideogram_studio_workflow(
        stub, modal_options={"workflow_selection": {
            "profile": "production",
            "workflow_id": "",
            "workflow_version_id": "",
            "workflow_steps": "",
        }},
    )
    assert out is stub
    assert selection == {"active": False}


def test_active_path_yields_studio_graph_with_steps16(monkeypatch):
    _arm(monkeypatch)
    stub = _production_stub()
    out, selection = inj.maybe_inject_ideogram_studio_workflow(stub)
    assert out is not stub
    # Caller plan untouched; injection works on the stored Studio copy.
    assert stub == _production_stub()
    assert selection["active"] is True
    assert selection["steps"] == {
        "graph_default": 20, "requested": 16, "effective": 16, "source": "explicit",
    }
    guiders = [
        node for node in out.values()
        if isinstance(node, dict) and node.get("class_type") == "DualModelGuider"
    ]
    assert len(guiders) == 1
    assert _unet_names(out) == [
        "ideogram4_int8_convrot.safetensors",
        "ideogram4_unconditional_int8_convrot.safetensors",
    ]
    schedulers = [
        (node_id, node) for node_id, node in out.items()
        if isinstance(node, dict) and node.get("class_type") == "Ideogram4Scheduler"
    ]
    assert len(schedulers) == 1
    assert schedulers[0][1]["inputs"]["steps"] == 16
    sampler_names = [
        str(node.get("inputs", {}).get("sampler_name") or "")
        for node in out.values()
        if isinstance(node, dict) and node.get("class_type") == "KSamplerSelect"
    ]
    assert sampler_names == ["euler"]


def test_active_via_flags_without_profile(monkeypatch):
    # Flag channel alone activates (profile env absent).
    _arm(monkeypatch, profile=False)
    assert os.environ.get(inj.PROFILE_ENV, "") == ""
    out, selection = inj.maybe_inject_ideogram_studio_workflow(_production_stub())
    assert selection["active"] is True
    assert selection["scheduler_node"] in out


def test_profile_active_but_flags_absent_fails_closed(monkeypatch):
    monkeypatch.setenv(inj.PROFILE_ENV, PROFILE)
    monkeypatch.setenv(inj.WORKFLOW_STEPS_ENV, "16")
    with pytest.raises(GateError):
        inj.maybe_inject_ideogram_studio_workflow(_production_stub())


def test_version_mismatch_fails_closed(monkeypatch):
    _arm(monkeypatch, wver="wv_deadbeefdeadbeef")
    with pytest.raises(GateError):
        inj.maybe_inject_ideogram_studio_workflow(_production_stub())


def test_steps_not_explicit_16_fails_closed(monkeypatch):
    for steps in (None, "0", "20"):
        _arm(monkeypatch, steps=steps)
        with pytest.raises(GateError):
            inj.maybe_inject_ideogram_studio_workflow(_production_stub())


def test_missing_stored_version_fails_closed(monkeypatch, tmp_path):
    _arm(monkeypatch)
    (tmp_path / ".studio_workflow_versions.json").write_text("[]", encoding="utf-8")
    (tmp_path / ".studio_workflows.json").write_text("[]", encoding="utf-8")
    with pytest.raises(GateError):
        inj.maybe_inject_ideogram_studio_workflow(
            _production_stub(), repo_root=tmp_path
        )
