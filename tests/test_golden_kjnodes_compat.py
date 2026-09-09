import types

import pytest

from comfymodal_runtime.kjnodes_compat import register_join_strings_fallback


@pytest.mark.fast_unit
def test_golden_missing_kjnodes_registration_matches_exact_contract():
    nodes = types.SimpleNamespace(
        NODE_CLASS_MAPPINGS={}, NODE_DISPLAY_NAME_MAPPINGS={}
    )
    assert register_join_strings_fallback(nodes, golden_enabled=True)

    node = nodes.NODE_CLASS_MAPPINGS["JoinStrings"]
    assert node.INPUT_TYPES() == {
        "required": {"delimiter": ("STRING", {"default": " "})},
        "optional": {
            "string1": ("STRING", {"default": "", "forceInput": True}),
            "string2": ("STRING", {"default": "", "forceInput": True}),
        },
    }
    assert node.RETURN_TYPES == ("STRING",)
    assert node.CATEGORY == "KJNodes/text"
    assert node.FUNCTION == "joinstring"
    assert nodes.NODE_DISPLAY_NAME_MAPPINGS["JoinStrings"] == "Join Strings"
    assert node().joinstring("|", "left", "right") == ("left|right",)


@pytest.mark.fast_unit
def test_existing_kjnodes_registration_is_untouched():
    existing = object()
    display = {"JoinStrings": "real display"}
    nodes = types.SimpleNamespace(
        NODE_CLASS_MAPPINGS={"JoinStrings": existing},
        NODE_DISPLAY_NAME_MAPPINGS=display,
    )
    assert not register_join_strings_fallback(nodes, golden_enabled=True)
    assert nodes.NODE_CLASS_MAPPINGS["JoinStrings"] is existing
    assert nodes.NODE_DISPLAY_NAME_MAPPINGS is display
    assert nodes.NODE_DISPLAY_NAME_MAPPINGS["JoinStrings"] == "real display"


@pytest.mark.fast_unit
def test_non_golden_production_does_not_register_fallback():
    nodes = types.SimpleNamespace(
        NODE_CLASS_MAPPINGS={}, NODE_DISPLAY_NAME_MAPPINGS={}
    )
    assert not register_join_strings_fallback(nodes, golden_enabled=False)
    assert nodes.NODE_CLASS_MAPPINGS == {}
    assert nodes.NODE_DISPLAY_NAME_MAPPINGS == {}
