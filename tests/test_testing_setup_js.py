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

    def test_contains_five_visible_sections(self):
        """Setup shows five visible sections: Generation Type, What Changes?,
        Workflows, Test Values, Review & Run."""
        for label in ("Generation Type", "What Changes?", "Workflows",
                      "Test Values", "Review & Run"):
            with self.subTest(label=label):
                self.assertTrue(self.m.has_section(label),
                                f"section {label!r} not found in testing-setup.js")

    def test_old_nine_labels_removed(self):
        """Old nine-section labels are gone from SECTION_LABELS object."""
        # Extract the SECTION_LABELS object text to avoid false positives
        # from backend routes, CSS classes, or sub-group labels.
        m = re.search(r'const SECTION_LABELS = \{(.+?)\};', self.m.text, re.DOTALL)
        self.assertIsNotNone(m, "SECTION_LABELS definition not found")
        labels_text = m.group(1)
        old_labels = (
            "Experiment", "Model Profiles", "LoRAs",
            "Prompts", "Images", "Axes", "Execution",
            "Workflows & Models",
        )
        for label in old_labels:
            with self.subTest(label=label):
                self.assertNotIn(label, labels_text,
                                 f"old section label {label!r} should not be in SECTION_LABELS")

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
        self.assertTrue(self.m.has_function("pickMainTriple"),
                        "expected pickMainTriple helper")
        self.assertIn("rawSlots", self.m.text,
                       "pickMainTriple should handle dict-style slot objects")

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

    def test_lora_scope_row_is_appended_after_stack_card_construction(self):
        """LoRA scope controls must be appended after stackCard is created.

        Keeping a `const` declaration inside the `el(..., [...])` children array
        makes the browser reject the module at parse time.
        """
        self.assertIn(
            'const scopeRow = el("div", { class: "testing-setup-lora-scope-row" }, [',
            self.m.text,
            "expected standalone scopeRow element construction",
        )
        self.assertIn(
            'stackCard.appendChild(scopeRow);',
            self.m.text,
            "expected LoRA scope row appended after stackCard construction",
        )

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
        self.assertIn("validateSpec(", self.m.text,
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

    def test_setup_has_workflow_local_config_section(self):
        """testing-setup.js must have workflow-local config wording (Model Stack + LoRA)."""
        text = self.m.text
        has_local_stack = (
            "Local Model Stack" in text
            or "workflow-model-stack" in text
        )
        has_local_lora = (
            "Local LoRA" in text
            or "workflow-local-lora" in text
        )
        self.assertTrue(
            has_local_stack,
            "Expected workflow-local model stack wording in testing-setup.js",
        )
        self.assertTrue(
            has_local_lora,
            "Expected workflow-local LoRA wording in testing-setup.js",
        )


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

    def test_five_section_labels_replace_old_nine(self):
        """Five section labels replace old nine — old labels are gone from SECTION_LABELS."""
        text = self.m.text
        # Positive: new 5-section labels appear in SECTION_LABELS
        m = re.search(r'const SECTION_LABELS = \{(.+?)\};', text, re.DOTALL)
        self.assertIsNotNone(m, "SECTION_LABELS definition not found")
        labels_block = m.group(1)
        new_steps = [
            "Generation Type",
            "What Changes?",
            "Workflows",
            "Test Values",
            "Review & Run",
        ]
        for step in new_steps:
            with self.subTest(step=step):
                self.assertIn(
                    step,
                    labels_block,
                    f"New section {step!r} must appear in SECTION_LABELS",
                )
        # Negative: old 9-section labels must be removed from SECTION_LABELS
        gone = (
            "Experiment", "Model Profiles", "LoRAs",
            "Prompts", "Images", "Axes", "Execution",
            "Workflows & Models",
        )
        for label in gone:
            with self.subTest(old_label=label):
                self.assertNotIn(
                    label,
                    labels_block,
                    f"Old section label {label!r} must be removed from SECTION_LABELS",
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


# ---------------------------------------------------------------------------
# Frontend Adapter Boundary: dedicated adapter module replaces
# legacy compiler-shape construction across components.
# ---------------------------------------------------------------------------

class SetupAdapterBoundaryTests(unittest.TestCase):
    """Setup references a dedicated frontend adapter module rather than
    embedding legacy compiler-shape construction across components."""

    def setUp(self) -> None:
        if not JS_PATH.exists():
            raise AssertionError("web/testing-setup.js missing")
        self.m = _TestModule(JS_PATH)

    def test_adapter_module_import(self):
        """testing-setup.js must import from a dedicated adapter module."""
        self.assertIn(
            "./testing-setup-adapter.js",
            self.m.text,
            "Expected import from ./testing-setup-adapter.js for compiler-shape adapter",
        )

    def test_adapter_export_reference(self):
        """testing-setup.js must reference the adapter's exports."""
        # The adapter module exposes spec-to-compiler-shape conversion
        text = self.m.text
        self.assertIn(
            "adapter",
            text,
            "Expected reference to adapter conversion in testing-setup.js",
        )


# ---------------------------------------------------------------------------
# Tri-state labels and sticky summary markers
# ---------------------------------------------------------------------------

class SetupTriStateSummaryTests(unittest.TestCase):
    """Structural markers for tri-state labels and sticky summary."""

    def setUp(self) -> None:
        if not JS_PATH.exists():
            raise AssertionError("web/testing-setup.js missing")
        self.m = _TestModule(JS_PATH)

    def test_tri_state_label_marker(self):
        """Setup must include generation type markers (t2i/i2i toggles)."""
        text = self.m.text
        has_gen_type = (
            "generation_type" in text
            or "generation-tile" in text
            or "data-gen-type" in text
        )
        self.assertTrue(
            has_gen_type,
            "Expected generation_type marker (generation_type / generation-tile / data-gen-type) in testing-setup.js",
        )

    def test_generation_type_values_referenced(self):
        """Generation type labels must reference t2i/img2img values."""
        text = self.m.text
        for val in ('"t2i"', '"img2img"'):
            with self.subTest(value=val):
                self.assertIn(
                    val,
                    text,
                    f"Expected generation type value {val} referenced in testing-setup.js",
                )

    def test_sticky_summary_marker(self):
        """Setup must have a sticky summary section marker."""
        self.assertIn(
            "testing-setup-sticky-summary",
            self.m.text,
            "Expected testing-setup-sticky-summary class for sticky run summary",
        )


# ---------------------------------------------------------------------------
# Workflow-local model stack and LoRA configuration wording
# ---------------------------------------------------------------------------

class SetupWorkflowLocalConfigTests(unittest.TestCase):
    """Workflow-local model stack and LoRA configuration wording."""

    def setUp(self) -> None:
        if not JS_PATH.exists():
            raise AssertionError("web/testing-setup.js missing")
        self.m = _TestModule(JS_PATH)

    def test_workflow_local_model_stack_wording(self):
        """Setup must use workflow-local model stack wording."""
        text = self.m.text
        has_local_wording = (
            "Local Model Stack" in text
            or "workflow-model-stack" in text
            or "workflow_local" in text and "model_stack" in text
        )
        self.assertTrue(
            has_local_wording,
            "Expected workflow-local model stack wording (Local Model Stack / workflow-model-stack) in testing-setup.js",
        )

    def test_workflow_local_lora_wording(self):
        """Setup must use workflow-local LoRA configuration wording."""
        text = self.m.text
        has_lora_wording = (
            "Local LoRA" in text
            or "workflow-local-lora" in text
            or "workflow_local" in text and "lora" in text.lower()
        )
        self.assertTrue(
            has_lora_wording,
            "Expected workflow-local LoRA wording (Local LoRA / workflow-local-lora) in testing-setup.js",
        )


# ---------------------------------------------------------------------------
# Deeper workflow/model-stack/LoRA semantics
# ---------------------------------------------------------------------------

class SetupDeeperSemanticsTests(unittest.TestCase):
    """Structural markers for the deeper workflow semantics in the Setup UI."""

    def setUp(self) -> None:
        if not JS_PATH.exists():
            raise AssertionError("web/testing-setup.js missing")
        self.m = _TestModule(JS_PATH)

    def test_generation_type_t2i_i2i_labels(self):
        """Generation Type section must show T2I and I2I as primary options."""
        text = self.m.text
        for label in ("Text-to-Image", "Image-to-Image"):
            with self.subTest(label=label):
                self.assertIn(
                    label,
                    text,
                    f"Expected generation type label {label!r} in testing-setup.js",
                )

    def test_variable_modes_in_adapter_import(self):
        """testing-setup.js must import variable mode helpers from adapter."""
        text = self.m.text
        self.assertIn(
            "getActiveTestingVariables",
            text,
            "Expected getActiveTestingVariables import from adapter",
        )
        self.assertIn(
            "cycleVariableMode",
            text,
            "Expected cycleVariableMode import from adapter",
        )
        self.assertIn(
            "getVariableLabel",
            text,
            "Expected getVariableLabel import from adapter",
        )

    def test_variable_grid_in_what_changes(self):
        """What Changes section must contain a variable grid."""
        text = self.m.text
        self.assertIn(
            "testing-setup-variable-grid",
            text,
            "Expected testing-setup-variable-grid in What Changes section",
        )
        self.assertIn(
            "testing-setup-var-tile",
            text,
            "Expected testing-setup-var-tile class for variable tiles",
        )

    def test_variable_tri_state_buttons(self):
        """Variable tiles must have Default/Testing/Controlled buttons."""
        text = self.m.text
        for btn in ("Default", "Testing", "Controlled"):
            with self.subTest(btn=btn):
                self.assertIn(
                    btn,
                    text,
                    f"Expected {btn!r} button in variable tile grid",
                )

    def test_multi_stack_imports(self):
        """testing-setup.js must import stack helper functions."""
        text = self.m.text
        self.assertIn(
            "addStackToWorkflow",
            text,
            "Expected addStackToWorkflow helper import",
        )
        self.assertIn(
            "removeStackFromWorkflow",
            text,
            "Expected removeStackFromWorkflow helper import",
        )
        self.assertIn(
            "duplicateStackInWorkflow",
            text,
            "Expected duplicateStackInWorkflow helper import",
        )

    def test_stack_card_markers(self):
        """Workflows section must have stack card UI markers."""
        text = self.m.text
        self.assertIn(
            "testing-setup-stack-card",
            text,
            "Expected testing-setup-stack-card for stack card UI",
        )
        self.assertIn(
            "testing-setup-stack-editor",
            text,
            "Expected testing-setup-stack-editor for stack editing area",
        )

    def test_lora_scope_cycle(self):
        """The LoRA scope cycle must be imported from the adapter."""
        text = self.m.text
        self.assertIn(
            "cycleLoraScope",
            text,
            "Expected cycleLoraScope helper import",
        )
        self.assertIn(
            "getLoraScopeLabel",
            text,
            "Expected getLoraScopeLabel helper import",
        )
        # Scope function must be called at least once
        self.assertIn(
            "getLoraScopeLabel(",
            text,
            "Expected getLoraScopeLabel call in testing-setup.js",
        )

    def test_per_stack_lora_controls(self):
        """Per-stack LoRA sections must exist in the editor."""
        text = self.m.text
        self.assertIn(
            "testing-setup-stack-loras",
            text,
            "Expected per-stack LoRA section marker",
        )

    def test_add_stack_button(self):
        """There must be a way to add stacks to a workflow."""
        text = self.m.text
        self.assertIn(
            "Add Stack",
            text,
            "Expected '+ Add Stack' button in workflow config",
        )

    def test_variable_filtering_in_test_values(self):
        """Test Values section must filter by active testing variables."""
        text = self.m.text
        self.assertIn(
            "activeTestingVars",
            text,
            "Expected activeTestingVars filtering in test values section",
        )
        self.assertIn(
            "isTesting(",
            text,
            "Expected isTesting helper for variable visibility filtering",
        )

    def test_sticky_summary_new_format(self):
        """Sticky summary must reference the new model fields."""
        text = self.m.text
        self.assertIn(
            "testing /",
            text,
            "Expected 'testing / controlled' count in sticky summary",
        )
        self.assertIn(
            '"T2I"',
            text,
            "Expected 'T2I' type display in sticky summary",
        )

    def test_validation_generation_type(self):
        """validateSpec must check for generation_type."""
        text = self.m.text
        self.assertIn(
            "generation_type",
            text,
            "Expected generation_type check in validateSpec",
        )


# ---------------------------------------------------------------------------
# Auto-preview: debounced backend preview on draft changes
# ---------------------------------------------------------------------------

class SetupAutoPreviewTests(unittest.TestCase):
    """Structural markers for authoritative auto-preview behavior."""

    def setUp(self) -> None:
        if not JS_PATH.exists():
            raise AssertionError("web/testing-setup.js missing")
        self.m = _TestModule(JS_PATH)

    def test_auto_preview_container_class(self):
        """Preview section must have an auto-preview status container."""
        self.assertIn(
            "testing-setup-auto-preview",
            self.m.text,
            "Expected testing-setup-auto-preview class for auto-preview status area",
        )

    def test_auto_preview_loading_text(self):
        """Auto-preview must show a loading message when in flight."""
        self.assertIn(
            "Compiling preview",
            self.m.text,
            "Expected 'Compiling preview' loading text in auto-preview flow",
        )

    def test_auto_preview_result_prefix(self):
        """Auto-preview success must show a result with cell/checkpoint counts."""
        self.assertIn(
            "Preview:",
            self.m.text,
            "Expected 'Preview:' prefix in auto-preview result display",
        )

    def test_auto_preview_request_sequencing(self):
        """Auto-preview must use a sequence counter to discard stale responses."""
        text = self.m.text
        self.assertIn(
            "previewSeq",
            text,
            "Expected previewSeq counter for request sequencing",
        )
        self.assertIn(
            "seq !== previewSeq",
            text,
            "Expected stale-response guard: seq !== previewSeq",
        )

    def test_auto_preview_debounce_timeout(self):
        """Auto-preview must use a debounce timer (setTimeout with delay)."""
        self.assertIn(
            "setTimeout",
            self.m.text,
            "Expected setTimeout for debounced auto-preview",
        )
        # Verify the debounce delay is reasonable (300-500ms range)
        self.assertIn(
            "400",
            self.m.text,
            "Expected 400ms debounce delay for auto-preview",
        )

    def test_auto_preview_schedule_function(self):
        """Auto-preview must have a schedule function name visible."""
        self.assertTrue(
            self.m.has_function("scheduleAutoPreview"),
            "Expected scheduleAutoPreview function for triggering auto-preview",
        )

    def test_auto_preview_cancelled_on_destroy(self):
        """Auto-preview timer must be cleared on destroy."""
        self.assertIn(
            "clearTimeout",
            self.m.text,
            "Expected clearTimeout in destroy path for auto-preview cleanup",
        )

    def test_auto_preview_calls_do_compile(self):
        """Auto-preview must call the backend compile endpoint."""
        self.assertIn(
            "doCompile(snapSpec, apiBase)",
            self.m.text,
            "Expected doCompile call in auto-preview with captured spec snapshot",
        )

    def test_sticky_summary_updatable_container(self):
        """Sticky summary must use a replaceable container class."""
        self.assertIn(
            "testing-setup-sticky-container",
            self.m.text,
            "Expected testing-setup-sticky-container for replaceable sticky summary",
        )

    def test_auto_preview_separate_from_draft(self):
        """Auto-preview state must stay out of the persisted draft (no preview in normalizeDraft)."""
        # Confirm that the preview section doesn't write into spec
        has_update_preview_in_draft = "spec.autoPreview" in self.m.text or "spec.preview" in self.m.text
        self.assertFalse(
            has_update_preview_in_draft,
            "Auto-preview state should not be written into the spec/draft",
        )


if __name__ == "__main__":
    unittest.main()
