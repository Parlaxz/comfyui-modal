"""Golden-side INPUT_TYPES schema capture (GeneralSwitch inspect.stack bypass).

The production-008 exhaustive profile showed Impact Pack's ``GeneralSwitch``
spending 574.9 ms over 5 request-time ``INPUT_TYPES()`` calls, essentially all
of it inside ``inspect.stack()`` -> ``getframeinfo`` -> ``findsource`` /
``getmodule``.  That caller detection exists only to support upstream ComfyUI's
``get_input_info()`` validation path, which Golden does not use.

These tests pin the contract that makes bypassing it safe:

* the captured schema is byte-for-byte the class's own normal schema;
* a captured class is served without invoking ``inspect.stack()`` again;
* any absence/incompatibility falls back to the original implementation;
* lazy selection, required/optional/hidden fields are unchanged;
* nothing outside Golden is monkeypatched -- the non-Golden ``get_input_info()``
  detection still runs inside the third-party class;
* no other custom node's ``INPUT_TYPES`` is ever memoized.

``GeneralSwitch`` is reproduced structurally here rather than imported: the
third-party package is never modified or depended on by the test suite.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast_unit

MODULE_PATH = Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "golden_serial.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("golden_serial_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("golden_serial_under_test", module)
    spec.loader.exec_module(module)
    return module


gs = _load_module()


class _AnyType(str):
    """Stand-in for Impact Pack's ``AnyType`` wildcard type sentinel."""

    def __ne__(self, other):  # noqa: D105 - mirrors the third-party behavior
        return False


any_typ = _AnyType("*")


# Caller-detection counters live at module scope so the test doubles can bump
# them without reaching for a class attribute through the metaclass.
_CALLS = {"general_switch_stack": 0, "rgthree_any_switch": 0}


class GeneralSwitch:
    """Structurally faithful stand-in for Impact Pack's ``GeneralSwitch``.

    Reproduces the exact shape that matters: ``inspect.stack()`` is called only
    so the class can detect the ``get_input_info`` validation path and
    substitute an accept-anything container.
    """

    __module__ = "modules.impact.util_nodes"
    __qualname__ = "GeneralSwitch"

    execution_supported = True

    @classmethod
    def INPUT_TYPES(cls):
        dyn_inputs = {
            "input1": (any_typ, {"lazy": True, "tooltip": "Any input. When connected, one more input slot is added."}),
        }
        if cls.execution_supported:
            _CALLS["general_switch_stack"] += 1
            stack = inspect.stack()
            if stack[2].function == "get_input_info":
                # bypass validation
                class AllContainer:
                    def __contains__(self, item):
                        return True

                    def __getitem__(self, key):
                        return any_typ, {"lazy": True}

                dyn_inputs = AllContainer()

        return {
            "required": {
                "select": ("INT", {"default": 1, "min": 1, "max": 999999, "step": 1, "tooltip": "input number"}),
                "sel_mode": ("BOOLEAN", {"default": False, "label_on": "select_on_prompt", "label_off": "select_on_execution", "forceInput": False}),
            },
            "optional": dyn_inputs,
            "hidden": {"unique_id": "UNIQUE_ID", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    def check_lazy_status(self, *args, **kwargs):
        selected_index = int(kwargs["select"])
        input_name = f"input{selected_index}"
        if input_name in kwargs:
            return [input_name]
        return []

    @staticmethod
    def doit(*args, **kwargs):
        selected_index = int(kwargs["select"])
        return kwargs["input%d" % selected_index]


class RgthreeAnySwitch:
    """A second, unrelated class with a genuinely per-call schema.

    Proves the capture never generalizes into arbitrary INPUT_TYPES memoizing.
    """

    __module__ = "custom_nodes.rgthree_comfy.py.any_switch"
    __qualname__ = "RgthreeAnySwitch"

    calls = 0

    @classmethod
    def INPUT_TYPES(cls):
        _CALLS["rgthree_any_switch"] += 1
        return {"required": {"any": ("*", {"lazy": True})}, "optional": {}, "hidden": {}}


class RaisingSwitch:
    """A capture target whose INPUT_TYPES fails; must not break capture."""

    __module__ = "modules.impact.util_nodes"
    __qualname__ = "GeneralSwitch"

    @classmethod
    def INPUT_TYPES(cls):
        raise RuntimeError("boom")


def _capture(mappings):
    """Run the real capture against a synthetic node registry."""

    fake_nodes = types.ModuleType("nodes")
    fake_nodes.NODE_CLASS_MAPPINGS = mappings
    sys.modules["nodes"] = fake_nodes
    try:
        return gs.capture_golden_input_types_schemas()
    finally:
        sys.modules.pop("nodes", None)


@pytest.fixture(autouse=True)
def _clean_cache():
    gs._SNAPSHOT_INPUT_TYPES_SCHEMAS.clear()
    GeneralSwitch.execution_supported = True
    _CALLS["general_switch_stack"] = 0
    _CALLS["rgthree_any_switch"] = 0
    yield
    gs._SNAPSHOT_INPUT_TYPES_SCHEMAS.clear()


# â”€â”€ schema equivalence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_captured_schema_is_exactly_the_normal_schema():
    """The cached schema equals what the class itself produces normally."""
    _capture({"GeneralSwitch": GeneralSwitch})
    cached = gs.golden_input_types(GeneralSwitch)

    _CALLS["general_switch_stack"] = 0
    direct = GeneralSwitch.INPUT_TYPES()

    assert cached == direct
    # Equality of structure, not just the wildcard sentinel.
    assert cached["required"] == direct["required"]
    assert cached["hidden"] == direct["hidden"]
    assert list(cached["required"]) == ["select", "sel_mode"]
    assert list(cached["optional"]) == ["input1"]


def test_cached_lookup_does_not_invoke_inspect_stack():
    """Once captured, repeated Golden lookups cost no caller detection."""
    _capture({"GeneralSwitch": GeneralSwitch})
    assert gs._SNAPSHOT_INPUT_TYPES_SCHEMAS  # capture happened

    _CALLS["general_switch_stack"] = 0
    for _ in range(25):
        gs.golden_input_types(GeneralSwitch)

    assert _CALLS["general_switch_stack"] == 0


def test_capture_only_pays_caller_detection_once():
    """Capture itself resolves the schema exactly once."""
    _capture({"GeneralSwitch": GeneralSwitch})
    assert _CALLS["general_switch_stack"] == 1


def test_capture_is_idempotent():
    """A second capture is a no-op: no re-resolve, no extra caller detection."""
    first = _capture({"GeneralSwitch": GeneralSwitch})
    calls_after_first = _CALLS["general_switch_stack"]
    cached = dict(gs._SNAPSHOT_INPUT_TYPES_SCHEMAS)

    second = _capture({"GeneralSwitch": GeneralSwitch})

    assert len(first) == 1
    assert second == {}
    assert gs._SNAPSHOT_INPUT_TYPES_SCHEMAS == cached
    assert _CALLS["general_switch_stack"] == calls_after_first


# â”€â”€ required behavior preservation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_required_optional_and_hidden_fields_are_present():
    _capture({"GeneralSwitch": GeneralSwitch})
    schema = gs.golden_input_types(GeneralSwitch)

    assert schema["required"]["select"][0] == "INT"
    assert schema["required"]["sel_mode"][0] == "BOOLEAN"
    assert schema["optional"]["input1"][0] is any_typ
    assert schema["optional"]["input1"][1]["lazy"] is True
    assert schema["hidden"] == {"unique_id": "UNIQUE_ID", "extra_pnginfo": "EXTRA_PNGINFO"}


def test_lazy_flag_is_visible_to_the_runner_input_info_helper():
    """GoldenSerialRunner._input_info still reads ``lazy`` from the cached schema."""
    _capture({"GeneralSwitch": GeneralSwitch})
    schema = gs.golden_input_types(GeneralSwitch)

    category, info = gs.GoldenSerialRunner._input_info(GeneralSwitch, "input1", schema)
    assert category == "optional"
    assert info["lazy"] is True

    category, info = gs.GoldenSerialRunner._input_info(GeneralSwitch, "select", schema)
    assert category == "required"
    assert info["default"] == 1
    assert "lazy" not in info


def test_lazy_selection_still_chooses_the_correct_input():
    """check_lazy_status/doit behavior is unaffected by the schema cache."""
    _capture({"GeneralSwitch": GeneralSwitch})
    schema = gs.golden_input_types(GeneralSwitch)
    assert schema["optional"]["input1"][1]["lazy"] is True

    node = GeneralSwitch()
    # A connected lazy input is requested on demand...
    assert node.check_lazy_status(select=2, input2="chosen") == ["input2"]
    # ...and an absent one yields nothing to pull, exactly as Impact Pack does.
    assert node.check_lazy_status(select=1, input2="chosen") == []
    assert node.doit(select=2, input1="a", input2="b") == "b"


# â”€â”€ fallback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_falls_back_to_original_when_no_capture_exists():
    """No snapshot capture -> the class's own INPUT_TYPES is used verbatim."""
    gs._SNAPSHOT_INPUT_TYPES_SCHEMAS.clear()
    _CALLS["general_switch_stack"] = 0

    schema = gs.golden_input_types(GeneralSwitch)

    assert _CALLS["general_switch_stack"] == 1
    assert schema == GeneralSwitch.INPUT_TYPES()
    assert schema["optional"]["input1"][1]["lazy"] is True


def test_falls_back_when_cached_value_is_incompatible():
    """A corrupt/foreign cached value must not be served."""
    key = gs._input_types_snapshot_key(GeneralSwitch)
    gs._SNAPSHOT_INPUT_TYPES_SCHEMAS[key] = "not-a-schema"
    _CALLS["general_switch_stack"] = 0

    schema = gs.golden_input_types(GeneralSwitch)

    assert _CALLS["general_switch_stack"] == 1
    assert isinstance(schema, dict)
    assert schema["optional"]["input1"][1]["lazy"] is True


def test_capture_survives_a_raising_class():
    """One bad class must not prevent the good capture."""
    captured = _capture({"A": RaisingSwitch, "GeneralSwitch": GeneralSwitch})
    assert len(captured) == 1
    assert gs.golden_input_types(GeneralSwitch)["optional"]["input1"][1]["lazy"] is True


def test_capture_without_a_node_registry_is_non_fatal():
    captured = _capture({})
    assert captured == {}
    assert gs.golden_input_types(GeneralSwitch)["optional"]["input1"][1]["lazy"] is True


# â”€â”€ no global monkeypatch â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_non_golden_get_input_info_detection_is_not_monkeypatched():
    """ComfyUI's own validation path still gets Impact Pack's bypass.

    The third-party class is untouched, so a caller two frames below
    ``get_input_info`` still receives the accept-anything container.
    """

    def _invoke(node_cls):
        return node_cls.INPUT_TYPES()

    def get_input_info(node_cls):
        return _invoke(node_cls)

    _capture({"GeneralSwitch": GeneralSwitch})
    schema = get_input_info(GeneralSwitch)

    assert not isinstance(schema["optional"], dict)
    assert "anything" in schema["optional"]
    assert schema["optional"]["anything"] == (any_typ, {"lazy": True})


def test_third_party_class_object_is_not_replaced():
    _capture({"GeneralSwitch": GeneralSwitch})
    gs.golden_input_types(GeneralSwitch)

    # INPUT_TYPES is still the original classmethod, not a wrapper.
    assert GeneralSwitch.INPUT_TYPES.__func__ is GeneralSwitch.__dict__["INPUT_TYPES"].__func__
    assert type(GeneralSwitch.__dict__["INPUT_TYPES"]) is classmethod
    # And the class still performs its own caller detection when invoked directly.
    before = _CALLS["general_switch_stack"]
    GeneralSwitch.INPUT_TYPES()
    assert _CALLS["general_switch_stack"] == before + 1


def test_no_other_custom_node_input_types_is_memoized():
    """Arbitrary custom-node INPUT_TYPES must keep calling the real thing."""
    _capture({"GeneralSwitch": GeneralSwitch, "RgthreeAnySwitch": RgthreeAnySwitch})

    assert gs._input_types_snapshot_key(RgthreeAnySwitch) is None
    for _ in range(3):
        gs.golden_input_types(RgthreeAnySwitch)
    assert _CALLS["rgthree_any_switch"] == 3


def test_unrelated_class_named_general_switch_is_not_captured():
    """Discovery is structural: the module path must also match."""

    class Other:  # __qualname__ will be "Other" at definition time
        pass

    Other.__qualname__ = "GeneralSwitch"
    assert gs._input_types_snapshot_key(Other) is None


# â”€â”€ the runner really goes through the helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_runner_input_paths_use_the_helper():
    """Structural guard: Golden's own resolution paths never call the class.

    A text assertion is the honest way to pin "no remaining direct call" for
    this optimization, because the runner methods need a full prompt context
    to execute.
    """
    source = MODULE_PATH.read_text(encoding="utf-8")
    body = source.split("def golden_input_types", 1)[1]
    runner = body.split("def _require_attention_backend_invocation", 1)[0]
    rest = body.split("def _require_attention_backend_invocation", 1)[1]

    # The helper owns the only remaining raw call in this region.
    assert runner.count("class_def.INPUT_TYPES()") == 1

    # Nothing after the helper may bypass it.
    for line in rest.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"'):
            continue
        assert "class_def.INPUT_TYPES()" not in stripped, stripped