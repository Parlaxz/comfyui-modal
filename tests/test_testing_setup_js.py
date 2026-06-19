"""Phase 8 — Setup UI structural tests.

This is a Python-side test that statically inspects ``web/testing-setup.js``
to verify the public API, exported symbols, and section coverage match
the parent plan §23. ComfyUI loads the JS file as a plain ES module at
runtime; we don't have a JS test runner in this project, so a structural
check is the appropriate level of verification.
"""
import importlib.util
import re
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
JS_PATH = REPO_ROOT / "web" / "testing-setup.js"


class _TestModule:
    """Loader that exposes the JS file's contents as a python-ish object
    for the structural assertions below."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.text = path.read_text(encoding="utf-8") if path.exists() else ""

    def has_export(self, name: str) -> bool:
        return bool(re.search(rf"export\s+(?:function|const|class)\s+{re.escape(name)}\b", self.text))

    def has_function(self, name: str) -> bool:
        return bool(re.search(rf"function\s+{re.escape(name)}\s*\(", self.text))

    def has_section(self, label: str) -> bool:
        return label in self.text

    def has_event_listener(self, event: str) -> bool:
        return f'"{event}"' in self.text or f"'{event}'" in self.text


class SetupUITests(unittest.TestCase):
    def setUp(self) -> None:
        if not JS_PATH.exists():
            raise AssertionError("web/testing-setup.js missing")
        self.m = _TestModule(JS_PATH)

    def test_exports_setup_tab_render(self):
        self.assertTrue(self.m.has_export("setup_tab_render"),
                        "expected `export function setup_tab_render`")

    def test_contains_required_sections(self):
        for label in ("Experiment", "Workflows & Models", "Model Profiles",
                      "LoRAs", "Prompts", "Images", "Axes", "Execution",
                      "Review & Run"):
            with self.subTest(label=label):
                self.assertTrue(self.m.has_section(label),
                                f"section {label!r} not found in testing-setup.js")

    def test_uses_pure_dom_no_framework_imports(self):
        # Pure DOM only: no React, no Vue, no Preact
        for forbidden in ("react", "preact", "vue", "@vue", "svelte"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.m.text.lower(),
                                 f"testing-setup.js must not import {forbidden}")

    def test_name_input_wires_input_event(self):
        # The experiment name input fires onChange
        self.assertTrue(self.m.has_event_listener("input"),
                        "expected at least one 'input' event listener")

    def test_pick_main_triple_handles_object_slots(self):
        """pickMainTriple must handle profile.slots as an object (not array)."""
        self.assertIn("Object.keys(rawSlots)", self.m.text,
                       "pickMainTriple should iterate object keys for dict slots")
        self.assertIn("rawSlots[key]", self.m.text,
                       "pickMainTriple should access values via object key")

    def test_loras_wire_model_strength_input(self):
        """LoRA rows must wire model_strength input changes back to spec."""
        self.assertIn("model_strength", self.m.text,
                       "expected model_strength CSV input in LoRA section")
        self.assertIn("onEntryChange", self.m.text,
                       "expected onChange callback propagation in makeLoraRow")

    def test_loras_wire_clip_strength_input(self):
        """LoRA rows must wire clip_strength input changes back to spec."""
        self.assertIn("clip_strength", self.m.text,
                       "expected clip_strength CSV input in LoRA section")

    def test_loras_wire_file_input(self):
        """LoRA rows must wire file input changes back to spec."""
        self.assertIn('"lora.safetensors"', self.m.text,
                       "expected file input placeholder in LoRA section")

    def test_multi_lora_per_entry_rows(self):
        """Each LoRA selection must support multiple per-entry rows."""
        text = self.m.text
        self.assertIn("makeLoraEntryRow", text,
                       "expected makeLoraEntryRow for per-index LoRA editing")
        self.assertIn("entry.loras[idx]", text,
                       "expected per-index lora entry access")

    def test_multi_lora_add_entry_button(self):
        """Each selection must have an Add LoRA entry button."""
        self.assertIn("+ Add LoRA entry", self.m.text,
                       "expected add-entry button inside LoRA selections")

    def test_multi_lora_remove_entry_button(self):
        """Each per-entry row must have a remove button."""
        self.assertIn("testing-setup-lora-entry-remove", self.m.text,
                       "expected remove button per LoRA entry")
        self.assertIn("splice(idx", self.m.text,
                       "expected splice to remove entry at index")

    def test_validate_spec_exists(self):
        """validateSpec function must exist for pre-compile validation."""
        self.assertTrue(self.m.has_function("validateSpec"),
                        "expected function validateSpec for LoRA validation")

    def test_validation_checks_empty_lora_file(self):
        """validateSpec should flag enabled LoRA with empty file."""
        self.assertIn("file path is required", self.m.text,
                       "expected validation message for empty LoRA file")

    def test_validation_checks_no_workflow_selected(self):
        """validateSpec should warn when no workflows selected."""
        self.assertIn("Select at least one workflow profile", self.m.text,
                       "expected validation message for no workflow")

    def test_compile_uses_validation(self):
        """Compile button handler must call validateSpec before onCompile."""
        self.assertIn("validateSpec(spec)", self.m.text,
                       "expected validateSpec to be called before compile")


# ---------------------------------------------------------------------------
# Setup Clarity: popup-scroll-aware navigation and structural markers
# ---------------------------------------------------------------------------

class SetupClarityNavigationTests(unittest.TestCase):
    """Setup section card structure and clarity markers (rail removed)."""

    def setUp(self) -> None:
        if not JS_PATH.exists():
            raise AssertionError("web/testing-setup.js missing")
        self.m = _TestModule(JS_PATH)

    def test_setup_uses_section_cards_not_rail(self):
        """Setup must use section cards stacked vertically, not a phase rail."""
        text = self.m.text
        self.assertNotIn(
            "testing-setup-phase-rail",
            text,
            "Phase rail has been removed; sections are stacked cards",
        )

    def test_setup_contains_finish_zone_marker(self):
        """Setup must have a finish zone marker for Review & Run."""
        self.assertTrue(
            self.m.has_section("testing-setup-finish-zone"),
            "Expected testing-setup-finish-zone class for the Review & Run finish zone",
        )

    def test_setup_contains_field_grid_marker(self):
        """Setup must have a field grid utility for Axes."""
        self.assertTrue(
            self.m.has_section("testing-setup-field-grid"),
            "Expected testing-setup-field-grid class for grouped axis fields",
        )


# ---------------------------------------------------------------------------
# Progressive Clarity: phase rail, collapsible sections, profile menu, advanced toggle
# ---------------------------------------------------------------------------

class SetupProgressiveClarityTests(unittest.TestCase):
    """Setup progressive-collapse and reduced-clutter markers."""

    def setUp(self) -> None:
        if not JS_PATH.exists():
            raise AssertionError("web/testing-setup.js missing")
        self.m = _TestModule(JS_PATH)

    def test_setup_no_phase_rail(self):
        """testing-setup.js must NOT use testing-setup-phase-rail (rail removed)."""
        self.assertNotIn(
            "testing-setup-phase-rail",
            self.m.text,
            "Phase rail has been removed from the setup UI",
        )

    def test_setup_uses_collapsible_section_marker(self):
        """testing-setup.js must use testing-setup-section-collapsible."""
        self.assertTrue(
            self.m.has_section("testing-setup-section-collapsible"),
            "Expected testing-setup-section-collapsible class for collapsible sections",
        )

    def test_setup_uses_data_collapsed_attribute(self):
        """testing-setup.js must use data-collapsed attribute."""
        self.assertIn(
            "data-collapsed",
            self.m.text,
            "Expected data-collapsed attribute for collapse state",
        )

    def test_setup_uses_advanced_axes_marker(self):
        """testing-setup.js must use testing-setup-advanced-toggle."""
        self.assertTrue(
            self.m.has_section("testing-setup-advanced-toggle"),
            "Expected testing-setup-advanced-toggle for advanced axes controls",
        )

    def test_setup_uses_inline_profile_actions(self):
        """testing-setup.js must use inline profile action buttons (Validate, Duplicate, Delete)."""
        text = self.m.text
        self.assertIn("Validate", text,
                       "Expected Validate button in workflow profile rows")
        self.assertIn("Duplicate", text,
                       "Expected Duplicate button in workflow profile rows")
        self.assertIn("Delete", text,
                       "Expected Delete button in workflow profile rows")

    def test_setup_has_sampler_toggle_grid(self):
        """testing-setup.js must have sampler enable/disable toggles."""
        self.assertIn("testing-setup-sampler-grid", self.m.text,
                       "Expected testing-setup-sampler-grid for sampler toggles")
        self.assertIn("DEFAULT_ENABLED_SAMPLERS", self.m.text,
                       "Expected DEFAULT_ENABLED_SAMPLERS constant")

    def test_setup_has_prompt_editor_with_preset_bar(self):
        """testing-setup.js must have prompt editor with save-as-preset."""
        self.assertIn("testing-setup-prompt-editor", self.m.text,
                       "Expected testing-setup-prompt-editor for in-page prompt editing")
        self.assertIn("testing-setup-preset-bar", self.m.text,
                       "Expected testing-setup-preset-bar for preset dropdown + save button")

    def test_setup_has_model_profiles_section(self):
        """testing-setup.js must have a Model Profiles section."""
        self.assertIn("modelProfiles", self.m.text,
                       "Expected modelProfiles section key in testing-setup.js")
        self.assertIn("Model Profiles", self.m.text,
                       "Expected 'Model Profiles' section label in testing-setup.js")


# ---------------------------------------------------------------------------
# Visual redesign: step rail and section card
# ---------------------------------------------------------------------------

class SetupSectionCardTests(unittest.TestCase):
    """Section card structure (rail removed, stacked cards only)."""

    def setUp(self) -> None:
        if not JS_PATH.exists():
            raise AssertionError("web/testing-setup.js missing")
        self.m = _TestModule(JS_PATH)

    def test_no_phase_rail_class(self):
        """testing-setup.js must NOT have a phase rail class."""
        self.assertNotIn(
            "testing-setup-phase-rail",
            self.m.text,
            "Phase rail has been removed; no testing-setup-phase-rail expected",
        )

    def test_nine_section_labels(self):
        """All 9 section labels must be present (including Model Profiles)."""
        steps = [
            "Experiment",
            "Workflows & Models",
            "Model Profiles",
            "LoRAs",
            "Prompts",
            "Images",
            "Axes",
            "Execution",
            "Review & Run",
        ]
        text = self.m.text
        for step in steps:
            with self.subTest(step=step):
                self.assertIn(
                    step,
                    text,
                    f"Step {step!r} must appear in testing-setup.js",
                )

    def test_no_phase_key_attribute(self):
        """testing-setup.js must NOT have data-phase-key (rail removed)."""
        self.assertNotIn(
            "data-phase-key",
            self.m.text,
            "data-phase-key is from the removed phase rail; should not exist",
        )

    def test_section_card_class(self):
        """testing-setup.js must use a section card wrapper class."""
        self.assertTrue(
            self.m.has_section("testing-setup-section-card"),
            "Expected testing-setup-section-card class for section cards",
        )

    def test_data_section_key_attribute(self):
        """Section cards must have data-section-key attributes."""
        self.assertIn(
            "data-section-key",
            self.m.text,
            "Expected data-section-key attribute on section cards",
        )

    def test_no_four_phases(self):
        """The 4-phase rail labels should NOT be present (rail removed)."""
        for phase in ("Define", "Configure", "Modifiers", "Review"):
            # "Review" appears in "Review & Run" section label, so skip it
            if phase == "Review":
                continue
            with self.subTest(phase=phase):
                self.assertNotIn(
                    f'"{phase}"',
                    self.m.text,
                    f"Phase {phase!r} should not appear as a rail phase label",
                )


if __name__ == "__main__":
    unittest.main()
