"""Golden-only runtime compatibility for KJNodes' JoinStrings node."""


class JoinStrings:
    """Runtime parity copy of KJNodes' JoinStrings node."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "delimiter": ("STRING", {"default": " "}),
            },
            "optional": {
                "string1": ("STRING", {"default": "", "forceInput": True}),
                "string2": ("STRING", {"default": "", "forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "joinstring"
    CATEGORY = "KJNodes/text"

    def joinstring(self, delimiter, string1="", string2=""):
        return (string1 + delimiter + string2,)


def register_join_strings_fallback(nodes_module, *, golden_enabled: bool) -> bool:
    """Register KJNodes JoinStrings only when the caller is on Golden."""
    if not golden_enabled:
        print(
            "[comfyapp.compat] owner=comfyui-modal source=KJNodes.JoinStrings "
            "reason=non_golden_runtime action=skip"
        )
        return False

    mappings = nodes_module.NODE_CLASS_MAPPINGS
    if "JoinStrings" in mappings:
        print(
            "[comfyapp.compat] owner=KJNodes source=KJNodes.JoinStrings "
            "reason=real_registration_present action=skip"
        )
        return False

    mappings["JoinStrings"] = JoinStrings
    display_mappings = getattr(nodes_module, "NODE_DISPLAY_NAME_MAPPINGS", None)
    if display_mappings is None:
        display_mappings = {}
        nodes_module.NODE_DISPLAY_NAME_MAPPINGS = display_mappings
    display_mappings["JoinStrings"] = "Join Strings"
    print(
        "[comfyapp.compat] owner=comfyui-modal source=KJNodes.JoinStrings "
        "reason=missing_kjnodes_registration action=registered"
    )
    return True
