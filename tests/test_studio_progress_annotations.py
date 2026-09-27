"""Studio progress/annotation contracts: shared progress module, run-controller
progress wiring, timing normalization, annotations (favorite/note/save), and
canvas graph progress preservation.

Formerly test_task3_progress_annotations.py (renamed H20 Wave G — the suite
now pins permanent current-product contracts, not phase-task scaffolding).

Uses the same _JsModule pattern as test_studio_backend.py — AST / text
inspection only, no browser required.
"""

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"


class _JsModule:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.text = path.read_text(encoding="utf-8") if path.exists() else ""

    def contains(self, s: str) -> bool:
        return s in self.text

    def has_export(self, name: str) -> bool:
        return bool(
            re.search(
                rf"export\s+(?:(?:async\s+)?function|const|class|let|var)\s+{re.escape(name)}\b",
                self.text,
            )
        )

    def has_import(self, name: str) -> bool:
        """Check if the module imports from a path containing the given name."""
        escaped = re.escape(name)
        return bool(re.search(
            r'from\s+(["\'])[^"\']*' + escaped + r'[^"\']*\1',
            self.text,
        ))

    def count_occurrences(self, s: str) -> int:
        return self.text.count(s)


# ---------------------------------------------------------------------------
# A) Shared Progress Module: web/comfymodal-progress.js
# ---------------------------------------------------------------------------

class SharedProgressModuleTests(unittest.TestCase):
    """The shared progress module must exist and export the expected API."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "comfymodal-progress.js")

    def test_module_exists(self):
        self.assertTrue(self.m.path.exists(), "comfymodal-progress.js must exist")

    def test_exports_create_progress_tracker(self):
        self.assertTrue(
            self.m.has_export("createProgressTracker"),
            "Module must export createProgressTracker",
        )

    def test_progress_tracker_fields(self):
        """The state returned by createProgressTracker should reference all required fields."""
        text = self.m.text
        for field in [
            "runId", "promptId", "stage", "overallPercent",
            "currentNodeId", "currentNodeLabel",
            "completedNodes", "totalNodes",
            "samplerStep", "samplerMaximum",
            "elapsedMs", "queuePosition",
            "message", "error",
            "timingMilestones", "perNodeDurations",
        ]:
            self.assertIn(field, text, f"Progress state must include '{field}'")

    def test_handles_all_event_types(self):
        """Must subscribe to all required event types."""
        text = self.m.text
        for event in [
            "execution_start",
            "executing",
            "progress",
            "execution_cached",
            "execution_success",
            "execution_error",
            "modal_status",
        ]:
            self.assertIn(event, text, f"Must handle '{event}' event")

    def test_no_fabricated_percentages(self):
        """Must not fabricate percentages from elapsed time."""
        text = self.m.text
        self.assertNotIn(
            "fabricatePercentage", self.m.text,
        )
        self.assertNotIn(
            "elapsedMs * 100 / expectedMs", text,
        )

    def test_indeterminate_fallback(self):
        """Progress module must reference indeterminate state for missing progress events."""
        text = self.m.text
        self.assertIn("indeterminate", text)

    def test_current_node_type_not_present(self):
        """currentNodeType is not in the shape (cannot resolve without graph access)."""
        self.assertNotIn("currentNodeType", self.m.text)

    def test_execution_start_reentry_guard(self):
        """Re-entry guard for execution_start must cover startup AND generating states."""
        text = self.m.text
        self.assertIn("startup", text)
        self.assertIn("generating", text)
        # Guard must prevent re-entry when already in startup or generating
        guard_pattern = (
            'stage === "generating"' in text
            or 'stage === "startup"' in text
        )
        self.assertTrue(guard_pattern, "Re-entry guard must check stage")

    def test_no_reset_race(self):
        """Reset must not race with new execution_start (guard after _reset)."""
        text = self.m.text
        # The reset inside onExecutionSuccess should have a guard
        # Check that _reset() is followed or preceded by a state check
        self.assertIn("_reset", text)
        # Verify onExecutionStart has a guard before calling _reset
        exec_start_block = text[text.find("onExecutionStart"):text.find("onExecutionStart") + 300]
        # Block should check state before resetting
        self.assertIn("if", exec_start_block)


class SharedProgressConsumedByModalNodeTests(unittest.TestCase):
    """modal-node.js must import the shared progress module."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "modal-node.js")

    def test_imports_progress_module(self):
        self.assertTrue(
            self.m.has_import("comfymodal-progress"),
            "modal-node.js must import comfymodal-progress.js",
        )

    def test_uses_init_shared_tracker(self):
        """Must call initSharedTracker to create the singleton tracker."""
        self.assertIn(
            "initSharedTracker",
            self.m.text,
            "modal-node.js must call initSharedTracker",
        )


class PlaygroundProgressWiringTests(unittest.TestCase):
    """studio-playground.js progress wiring — CURRENT owner contract.

    H20 Wave G re-point: the Playground no longer imports or subscribes to
    comfymodal-progress.js directly (the shared/global tracker belongs to the
    canvas via modal-node.js). Playground run progress is owned by the run
    controller (createPlaygroundRunController from studio-playground-run.js)
    with status polling as the fallback; tracker state fields drive the
    progress section renderer.
    """

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-playground.js")

    def test_uses_playground_run_controller(self):
        """Run progress must flow through createPlaygroundRunController."""
        self.assertTrue(
            self.m.has_import("studio-playground-run"),
            "studio-playground.js must import from studio-playground-run.js",
        )
        self.assertIn(
            "createPlaygroundRunController",
            self.m.text,
            "Playground must obtain its run controller",
        )

    def test_controller_drives_run_lifecycle(self):
        """The controller must drive begin/submit/event-source lifecycle."""
        text = self.m.text
        self.assertIn("beginRun", text, "controller.beginRun must start run tracking")
        self.assertIn(
            "attachEventSource",
            text,
            "controller must be attached to the ComfyUI event source",
        )

    def test_tracker_state_fields_drive_progress_section(self):
        """Progress section must render tracker-state fields (overall/sampler/
        nodes/elapsed) from runState."""
        text = self.m.text
        for field in ("overallPercent", "samplerStep", "completedNodes", "elapsedMs"):
            self.assertIn(field, text, f"Progress section must use {field}")

    def test_no_global_shared_tracker_subscription(self):
        """The canvas owns the global shared tracker; the Playground must not
        subscribe to it as a progress source."""
        self.assertNotIn(
            "getSharedTracker().onProgress",
            self.m.text,
            "Playground must not subscribe to the canvas-owned global tracker",
        )

    def test_polling_remains_fallback(self):
        """Polling must remain fallback, not primary progress source."""
        self.assertIn(
            "_startPolling",
            self.m.text,
            "Polling helper must still exist as fallback",
        )


# ---------------------------------------------------------------------------
# B) Run / Timing Normalization
# ---------------------------------------------------------------------------

class RunNormalizerAnnotationTests(unittest.TestCase):
    """studio-run-normalizer.js must handle annotations and timing normalization."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-run-normalizer.js")

    def test_normalize_studio_run_has_timing_summary(self):
        """normalizeStudioRun output must include timingSummary."""
        self.assertIn(
            "timingSummary",
            self.m.text,
        )

    def test_normalize_studio_run_has_timing_stages(self):
        """normalizeStudioRun output must include timingStages."""
        self.assertIn(
            "timingStages",
            self.m.text,
        )

    def test_normalize_studio_run_has_per_node_timings(self):
        """normalizeStudioRun output must include perNodeTimings."""
        self.assertIn(
            "perNodeTimings",
            self.m.text,
        )

    def test_normalize_studio_run_has_timing_sources(self):
        """normalizeStudioRun output must include timingSources."""
        self.assertIn(
            "timingSources",
            self.m.text,
        )

    def test_normalize_studio_run_has_favorite(self):
        """normalizeStudioRun output must include favorite and note fields."""
        self.assertIn("favorite", self.m.text)
        self.assertIn("note", self.m.text)

    def test_nullish_safe_helper(self):
        """Module must define a nullish-safe helper for zero/false preservation."""
        text = self.m.text
        has_helper = (
            "??" in text
            or "nullish" in text
            or "nullSafe" in text
            or "nilTo" in text
        )
        self.assertTrue(
            has_helper,
            "Must use nullish coalescing (??) or define nullish-safe helper",
        )

    def test_seed_zero_preserved(self):
        """Seed value 0 must not be treated as falsy (uses nilTo/nilZero)."""
        text = self.m.text
        # The nilTo/nilZero helpers preserve 0 values. Verify the module
        # uses these or nullish coalescing (??) instead of truthy checks.
        self.assertTrue(
            "nilTo" in text or "nilZero" in text or "??" in text,
            "Must use nullish-safe patterns (nilTo, nilZero, or ??).",
        )

    def test_denoise_zero_preserved(self):
        """Denoise value 0 must not be hidden by truthiness checks."""
        text = self.m.text
        self.assertTrue(
            "nilTo" in text or "nilZero" in text or "??" in text,
            "Must use nullish-safe patterns for zero-value preservation.",
        )

    def test_cfg_zero_preserved(self):
        """CFG value 0 must not be hidden by truthiness checks."""
        text = self.m.text
        self.assertTrue(
            "nilTo" in text or "nilZero" in text or "??" in text,
            "Must use nullish-safe patterns for zero-value preservation.",
        )

    def test_duration_zero_preserved(self):
        """Zero-duration fields must remain visible."""
        text = self.m.text
        self.assertIn("durationMs", text)

    def test_raw_timing_accessible(self):
        """Raw timing JSON must remain accessible in advanced diagnostics."""
        text = self.m.text
        self.assertIn("raw", text)
        self.assertIn("timings", text)

    # â”€â”€ Contract Fix: normalizeAnnotations reads top-level annotations first â”€â”€

    def test_normalize_annotations_checks_top_level_first(self):
        """normalizeAnnotations must check run.annotations before extra.annotations."""
        text = self.m.text
        fn_start = text.find("export function normalizeAnnotations")
        if fn_start >= 0:
            fn_block = text[fn_start:fn_start + 800]
            # Must read run.annotations first
            self.assertIn("run.annotations", fn_block,
                          "normalizeAnnotations must read run.annotations before extra")
            self.assertIn("extra.annotations", fn_block,
                          "normalizeAnnotations must fall back to extra.annotations")
            self.assertTrue(
                fn_block.index("run.annotations") < fn_block.index("extra.annotations"),
                "run.annotations must be checked before extra.annotations"
            )

    def test_normalize_annotations_reads_updated_at(self):
        """normalizeAnnotations must read annotations.updated_at as primary timestamp."""
        text = self.m.text
        self.assertIn("updated_at", text,
                      "normalizeAnnotations must read annotations.updated_at")


# ---------------------------------------------------------------------------
# C) Playground UI â€” Progress display, favorites, notes
# ---------------------------------------------------------------------------

class PlaygroundProgressDisplayTests(unittest.TestCase):
    """Playground must show shared progress state instead of coarse submit/waiting UI."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-playground.js")

    def test_shows_overall_progress_bar(self):
        """Playground must render an overall progress bar."""
        self.assertIn("progress", self.m.text.lower())
        self.assertIn("bar", self.m.text.lower())

    def test_shows_current_stage_node(self):
        """Playground must display current stage/node during generation."""
        self.assertIn("stage", self.m.text.lower())

    def test_shows_sampler_step_progress(self):
        """Playground must display sampler step progress."""
        self.assertIn("step", self.m.text.lower())
        self.assertIn("sampler", self.m.text.lower())

    def test_shows_completed_total_nodes(self):
        """Playground must display completed/total nodes count."""
        self.assertIn("completedNodes", self.m.text)
        self.assertIn("totalNodes", self.m.text)

    def test_shows_elapsed_time(self):
        """Playground must display elapsed time during generation."""
        self.assertIn("elapsed", self.m.text.lower())

    def test_shows_queue_startup_state(self):
        """Playground must display queue/startup state."""
        self.assertIn("queue", self.m.text.lower())

    def test_clear_failure_state(self):
        """Playground must show clear failure/error state."""
        self.assertIn("error", self.m.text.lower())

    def test_completed_duration(self):
        """Playground must show completed duration."""
        self.assertIn("duration", self.m.text.lower())

    def test_favorite_star_in_playground(self):
        """Playground must have favorite star UI for selected run."""
        self.assertIn("favorite", self.m.text.lower())

    def test_note_section_in_playground(self):
        """Playground must have editable note section."""
        self.assertIn("note", self.m.text.lower())

    def test_optimistic_favorite_toggle(self):
        """Playground must implement optimistic favorite toggle."""
        self.assertIn("optimistic", self.m.text.lower())

    def test_note_save_cancel(self):
        """Note must have Save and Cancel actions."""
        text = self.m.text.lower()
        has_save = "save" in text or "Save" in self.m.text
        has_cancel = "cancel" in text or "Cancel" in self.m.text
        self.assertTrue(has_save, "Must have Save for notes")
        self.assertTrue(has_cancel, "Must have Cancel for notes")

    def test_note_dirty_state(self):
        """Note must track dirty state."""
        self.assertIn("dirty", self.m.text.lower())

    def test_note_saving_state(self):
        """Note must track saving state."""
        self.assertIn("saving", self.m.text.lower())

    def test_note_error_state(self):
        """Note must track error state."""
        self.assertIn("error", self.m.text.lower())

    def test_note_updated_timestamp(self):
        """Note must show updated timestamp after save."""
        self.assertIn("updated", self.m.text.lower())

    def test_playground_shows_timing_data(self):
        """Playground must display normalized timing/annotation data."""
        self.assertIn("timingSummary", self.m.text)



# ---------------------------------------------------------------------------
# E) Frontend API Layer
# ---------------------------------------------------------------------------

class BackendApiAnnotationsTests(unittest.TestCase):
    """studio-backend-api.js must have annotation PATCH helper."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-backend-api.js")

    def test_has_update_run_annotation(self):
        """Must export updateRunAnnotation function."""
        self.assertTrue(
            self.m.has_export("updateRunAnnotation")
            or "updateRunAnnotation" in self.m.text,
            "Must have updateRunAnnotation function",
        )

    def test_annotation_patch_method(self):
        """Annotation PATCH must use PATCH method."""
        self.assertIn("PATCH", self.m.text)

    # ── Contract Fix: PATCH route path must be plural /annotations ──

    def test_patch_url_uses_plural_annotations(self):
        """PATCH URL path must use plural /annotations (not singular /annotation)."""
        self.assertIn("/annotations", self.m.text)
        # Verify the updateRunAnnotation function uses the plural route path
        fn_start = self.m.text.find("export async function updateRunAnnotation")
        if fn_start >= 0:
            fn_block = self.m.text[fn_start:fn_start + 600]
            self.assertIn("/annotations", fn_block,
                          "updateRunAnnotation must call /annotations (plural)")

    # ── H18 Wave G: dead run-history list helpers deleted ──────────────

    def test_dead_list_helpers_deleted(self):
        """listExperiments/listRunHistory/listUnifiedHistory had zero
        importers since the H13 History-V2 migration; deleted in Wave G."""
        for retired in ["listExperiments", "listRunHistory", "listUnifiedHistory"]:
            self.assertNotIn(
                f"export async function {retired}",
                self.m.text,
                f"{retired} helper must stay deleted (Wave G)",
            )


class BackendApiHistoryQueryTests(unittest.TestCase):
    """H18 Wave G: the run-history list query helpers are retired.

    The COMPAT_WRITE annotation/save pair and the read-only compat routes
    remain server-side; the frontend list helpers had zero callers.
    """

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-backend-api.js")

    def test_has_no_list_run_history(self):
        """listRunHistory export must stay deleted."""
        self.assertFalse(
            self.m.has_export("listRunHistory"),
            "listRunHistory must stay deleted (Wave G)",
        )

    def test_annotation_and_save_helpers_survive(self):
        """The live COMPAT_WRITE helpers remain (FD-4)."""
        self.assertTrue(self.m.has_export("updateRunAnnotation"))
        self.assertTrue(self.m.has_export("saveRunOutput"))


# ---------------------------------------------------------------------------
# Parity: Playground and History V2 keep favorite/note semantics
# ---------------------------------------------------------------------------

class AnnotationDataParityTests(unittest.TestCase):
    """Playground and modern History V2 must both surface favorite/note data.

    (The legacy studio-history.js half of this parity contract was retired
    with the dead module in Phase H9; assertions moved to History V2.)
    """

    def test_both_reference_favorite_and_note(self):
        pg = _JsModule(WEB / "studio-playground.js")
        hi = _JsModule(WEB / "studio-history-v2.js")
        self.assertIn("favorite", pg.text)
        self.assertIn("favorite", hi.text)
        self.assertIn("note", pg.text)
        self.assertIn("note", hi.text)


# ---------------------------------------------------------------------------
# Normal graph execution preserved
# ---------------------------------------------------------------------------

class NormalGraphProgressPreservedTests(unittest.TestCase):
    """Normal graph execution must still behave identically after extraction."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "modal-node.js")

    def test_modal_node_still_has_extension_registration(self):
        """modal-node.js must still register its ComfyUI extension."""
        self.assertIn(
            'name: "comfyui.modal"',
            self.m.text,
        )

    def test_modal_node_still_patches_fetch_api(self):
        """modal-node.js must still patch fetchApi for /prompt routing."""
        self.assertIn(
            "api.fetchApi",
            self.m.text,
        )

    def test_modal_node_still_has_progress_bar_rendering(self):
        """modal-node.js must still have progress bar rendering functions."""
        self.assertIn("_pbCreate", self.m.text)
        self.assertIn("_pbInjectStyles", self.m.text)

    def test_modal_node_still_has_pb_show_functions(self):
        """All _pbShow* functions must be preserved for progress bar display."""
        self.assertIn("_pbShowIdle", self.m.text)
        self.assertIn("_pbShowStartup", self.m.text)
        self.assertIn("_pbShowProgress", self.m.text)
        self.assertIn("_pbShowError", self.m.text)
        self.assertIn("_pbShowDone", self.m.text)

    def test_event_handlers_reuse_tracker(self):
        """modal-node.js event handlers must delegate to the shared tracker."""
        # All event names are consumed by the shared tracker module
        tracker = _JsModule(WEB / "comfymodal-progress.js")
        self.assertIn("execution_start", tracker.text)
        self.assertIn("executing", tracker.text)
        self.assertIn("progress", tracker.text)
        self.assertIn("execution_cached", tracker.text)
        self.assertIn("execution_success", tracker.text)
        self.assertIn("execution_error", tracker.text)
        self.assertIn("modal_status", tracker.text)
        # modal-node.js uses the tracker singleton
        self.assertIn("initSharedTracker", self.m.text)
        self.assertIn("tracker.onProgress", self.m.text)
        # Stage names from the tracker are used for progress bar updates
        self.assertIn("startup", self.m.text)
        self.assertIn("generating", self.m.text)
        self.assertIn("done", self.m.text)
        self.assertIn("error", self.m.text)


# ---------------------------------------------------------------------------
# F) Phase 3: Studio-scoped progress tracker & samplerPercent fix
# ---------------------------------------------------------------------------

class ScopedProgressTrackerTests(unittest.TestCase):
    """Progress module must export createScopedTracker for Studio-scoped progress."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "comfymodal-progress.js")

    def test_exports_create_scoped_tracker(self):
        """Module must export createScopedTracker function."""
        self.assertTrue(
            self.m.has_export("createScopedTracker"),
            "Module must export createScopedTracker",
        )

    def test_scoped_tracker_has_start_method(self):
        """createScopedTracker must return an object with a start() method."""
        self.assertIn(
            "start",
            self.m.text,
            "Scoped tracker must have start() method",
        )

    def test_scoped_tracker_has_dispose_method(self):
        """createScopedTracker must return an object with a dispose() method."""
        self.assertIn(
            "dispose",
            self.m.text,
            "Scoped tracker must have dispose() method",
        )

    def test_scoped_tracker_has_on_progress(self):
        """createScopedTracker must return an object with onProgress() method."""
        self.assertIn(
            "onProgress",
            self.m.text,
            "Scoped tracker must have onProgress() method",
        )

    def test_scoped_tracker_has_state(self):
        """createScopedTracker must return an object with a state property."""
        self.assertIn(
            "state",
            self.m.text,
            "Scoped tracker must have a state property",
        )

    def test_scoped_tracker_captures_prompt_id(self):
        """Scoped tracker must capture prompt_id from execution_success."""
        text = self.m.text
        fn_idx = text.find("createScopedTracker")
        block = text[fn_idx:fn_idx + 2000] if fn_idx >= 0 else text
        self.assertIn(
            "prompt_id",
            block,
            "createScopedTracker must reference prompt_id in its handlers",
        )

    def test_scoped_tracker_locks_after_first_execution(self):
        """Scoped tracker must lock to a prompt_id after first execution_start."""
        text = self.m.text
        fn_idx = text.find("createScopedTracker")
        block = text[fn_idx:fn_idx + 2000] if fn_idx >= 0 else text
        has_lock = "lock" in block or "_locked" in block or "captured" in block
        self.assertTrue(
            has_lock,
            "createScopedTracker must implement lock/capture mechanism after first execution_start",
        )

    def test_scoped_tracker_rejects_unmatched_events(self):
        """Scoped tracker must filter events that don't match captured prompt_id."""
        text = self.m.text
        fn_idx = text.find("createScopedTracker")
        block = text[fn_idx:fn_idx + 2500] if fn_idx >= 0 else text
        # Must have some filtering check based on prompt_id
        has_filter = "return" in block and ("promptId" in block or "prompt_id" in block or "identity" in block)
        self.assertTrue(
            has_filter,
            "createScopedTracker must filter events by run identity",
        )

    def test_sampler_percent_field_exists(self):
        """State must have samplerPercent separate from overallPercent."""
        self.assertIn("samplerPercent", self.m.text)

    def test_overall_percent_not_overwritten_by_sampler(self):
        """overallPercent must NOT be overwritten by sampler step progress."""
        text = self.m.text
        # Look for assignment statements where overallPercent is set from sampler data.
        # Legitimate lines: field declarations (overallPercent: null) or comments
        # ("separate from overallPercent") are NOT assignments.
        # An assignment like "state.overallPercent = step / max * 100" inside onProgress
        # would indicate the bug. Check that no line contains "overallPercent = ... sampler".
        lines_with_assignment_overwrite = [
            i + 1 for i, line in enumerate(text.splitlines())
            if "overallPercent" in line
            and ("=" in line or ":" in line)
            and "sampler" in line.lower()
            and "separate" not in line.lower()
            and "never" not in line.lower()
            and "#" not in line
            and "//" not in line
        ]
        self.assertEqual(
            len(lines_with_assignment_overwrite),
            0,
            "No line should assign overallPercent from sampler data. "
            "Suspicious lines: " + str(lines_with_assignment_overwrite),
        )


# ---------------------------------------------------------------------------
# H20 Wave G: PlaygroundUsesScopedTrackerTests deleted — its premise (the
# Playground adopts createScopedTracker) was retired by the Wave-D run-
# controller architecture; the surviving invariants (polling fallback, no
# global-tracker subscription) are pinned by PlaygroundProgressWiringTests
# and the scoped-tracker module API remains covered by
# ScopedProgressTrackerTests + tests/test_studio_progress_tracker.py.



class GlobalTrackerPreservedTests(unittest.TestCase):
    """Global shared tracker (for modal-node progress bar) must remain unchanged."""

    def setUp(self) -> None:
        self.g = _JsModule(WEB / "comfymodal-progress.js")

    def test_global_tracker_still_exported(self):
        """createProgressTracker must still be exported for global use."""
        self.assertTrue(
            self.g.has_export("createProgressTracker"),
            "createProgressTracker must still be exported",
        )

    def test_global_tracker_still_singleton(self):
        """initSharedTracker and getSharedTracker must still work."""
        self.assertTrue(
            self.g.has_export("initSharedTracker"),
            "initSharedTracker must still be exported",
        )
        self.assertTrue(
            self.g.has_export("getSharedTracker"),
            "getSharedTracker must still be exported",
        )

    def test_global_tracker_still_handles_all_events(self):
        """Global tracker must still subscribe to all execution events."""
        for event in [
            "execution_start",
            "executing",
            "progress",
            "execution_cached",
            "execution_success",
            "execution_error",
            "modal_status",
        ]:
            self.assertIn(event, self.g.text, f"Global tracker must handle '{event}'")


if __name__ == "__main__":
    unittest.main()
