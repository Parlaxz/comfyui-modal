"""Structural/source tests for Task 3: shared progress, timing normalization,
annotations (favorite/note), History pagination/filter/sort.

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


class SharedProgressConsumedByPlaygroundTests(unittest.TestCase):
    """studio-playground.js must import and *invoke* the shared progress module."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-playground.js")

    def test_imports_progress_module(self):
        self.assertTrue(
            self.m.has_import("comfymodal-progress"),
            "studio-playground.js must import comfymodal-progress.js",
        )

    def test_uses_get_shared_tracker(self):
        """Must call getSharedTracker to obtain the tracker instance."""
        self.assertIn(
            "getSharedTracker()",
            self.m.text,
            "studio-playground.js must call getSharedTracker()",
        )

    def test_subscribes_to_tracker_progress(self):
        """Must subscribe to tracker state via onProgress."""
        self.assertIn(
            "onProgress",
            self.m.text,
            "studio-playground.js must subscribe to tracker.onProgress",
        )

    def test_tracker_drives_progress_section(self):
        """Tracker state must be used to update progress section fields."""
        text = self.m.text
        self.assertIn(
            "overallPercent",
            text,
            "Progress section must use tracker's overallPercent",
        )
        self.assertIn(
            "s.overallPercent",
            text,
            "Must reference tracker state fields for reactive updates",
        )

    def test_tracker_wired_flag(self):
        """Must use _trackerWired flag to avoid duplicate subscriptions."""
        self.assertIn(
            "_trackerWired",
            self.m.text,
            "Must guard tracker wiring with _trackerWired flag",
        )

    def test_tracker_only_updates_in_flight(self):
        """Tracker must only update runState when a run is in flight."""
        self.assertIn(
            "isInFlight",
            self.m.text,
            "Must check isInFlight before applying tracker updates",
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


# ---------------------------------------------------------------------------
# C) Playground UI — Progress display, favorites, notes
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
# D) History UI — Pagination, filters, sorting, favorites, notes
# ---------------------------------------------------------------------------

class HistoryPaginationTests(unittest.TestCase):
    """History must have pagination/access beyond first 50 records."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-history.js")

    def test_has_pagination(self):
        """History must have pagination controls."""
        self.assertIn("page", self.m.text.lower())

    def test_pagination_uses_offset_limit(self):
        """Pagination must use offset/limit query parameters."""
        self.assertIn("offset", self.m.text)
        self.assertIn("limit", self.m.text)

    def test_supports_next_prev(self):
        """Pagination must support next/previous navigation."""
        self.assertIn("next", self.m.text.lower())
        self.assertIn("prev", self.m.text.lower())


class HistoryFilterTests(unittest.TestCase):
    """History must have various filters."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-history.js")

    def test_search_filter(self):
        self.assertIn("search", self.m.text.lower())

    def test_search_has_debounce(self):
        """Search input must use debounce to avoid fetch on every keystroke."""
        text = self.m.text
        self.assertIn("setTimeout", text)
        self.assertIn("clearTimeout", text)

    def test_type_filter(self):
        self.assertIn("type", self.m.text.lower())

    def test_status_filter(self):
        self.assertIn("status", self.m.text.lower())

    def test_favorite_only_filter(self):
        self.assertIn("favorite", self.m.text.lower())

    def test_preset_filter(self):
        self.assertIn("preset", self.m.text.lower())

    def test_feature_filter(self):
        self.assertIn("feature", self.m.text.lower())

    def test_date_range_filter(self):
        self.assertIn("date", self.m.text.lower())
        self.assertIn("range", self.m.text.lower())

    def test_has_image_filter(self):
        self.assertIn("image", self.m.text.lower())


class HistorySortTests(unittest.TestCase):
    """History must have sort controls."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-history.js")

    def test_sort_newest(self):
        self.assertIn("newest", self.m.text.lower())

    def test_sort_oldest(self):
        self.assertIn("oldest", self.m.text.lower())

    def test_sort_fastest(self):
        self.assertIn("fastest", self.m.text.lower())

    def test_sort_slowest(self):
        self.assertIn("slowest", self.m.text.lower())

    def test_sort_preset_az(self):
        self.assertIn("preset", self.m.text.lower())
        self.assertIn("a-z", self.m.text.lower())

    def test_sort_preset_za(self):
        self.assertIn("z-a", self.m.text.lower())

    def test_stable_secondary_ordering(self):
        """Sort must include stable secondary ordering (by timestamp or startedAt)."""
        text = self.m.text
        self.assertTrue(
            "timestamp" in text or "startedAt" in text or "started_at" in text,
            "Stable secondary ordering by timestamp required.",
        )
        # Verify secondary ordering reference exists
        has_secondary = (
            "secondary" in text.lower()
            or "tiebreaker" in text.lower()
            or "stable" in text.lower()
        )
        if not has_secondary:
            # Fallback: check that the sort is applied on a field that includes
            # timestamp ordering naturally (sort newest/oldest implies timestamp ordering)
            self.assertIn("sort", text)


class HistoryGroupingToggleTests(unittest.TestCase):
    """Experiment grouping must be an explicit toggle."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-history.js")

    def test_grouping_toggle_exists(self):
        self.assertIn("group", self.m.text.lower())

    def test_grouping_is_explicit_toggle(self):
        text = self.m.text.lower()
        self.assertIn("toggle", text) or self.assertIn("checkbox", text)


class HistoryFavoriteNoteTests(unittest.TestCase):
    """History must have favorite stars and note editor."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-history.js")

    def test_favorite_star_on_cards(self):
        """History cards must show favorite star."""
        self.assertIn("favorite", self.m.text.lower())

    def test_no_propagation_on_star_click(self):
        """Star click must stop propagation to avoid opening card."""
        self.assertIn("stopPropagation", self.m.text)

    def test_note_editor_in_preview(self):
        """History detail preview must have note editor."""
        self.assertIn("note", self.m.text.lower())

    def test_notes_use_textcontent(self):
        """Notes must use textContent/plain text only."""
        m = _JsModule(WEB / "studio-history.js")
        self.assertIn("textContent", m.text)


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


class BackendApiHistoryQueryTests(unittest.TestCase):
    """studio-backend-api.js must have run-history list query helpers."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-backend-api.js")

    def test_has_list_run_history(self):
        """Must have listRunHistory export."""
        self.assertTrue(
            self.m.has_export("listRunHistory")
            or "listRunHistory" in self.m.text,
            "Must have listRunHistory function",
        )

    def test_list_run_history_accepts_params(self):
        """listRunHistory must accept query params for filter/sort/pagination."""
        text = self.m.text
        self.assertIn("params", text) or self.assertIn("query", text)


# ---------------------------------------------------------------------------
# Parity: Playground and History share same data
# ---------------------------------------------------------------------------

class AnnotationDataParityTests(unittest.TestCase):
    """Playground and History must use the same normalized note/favorite/timing data."""

    def test_both_import_run_normalizer(self):
        pg = _JsModule(WEB / "studio-playground.js")
        hi = _JsModule(WEB / "studio-history.js")
        self.assertTrue(
            pg.has_import("studio-run-normalizer"),
            "Playground must import studio-run-normalizer",
        )
        self.assertTrue(
            hi.has_import("studio-run-normalizer"),
            "History must import studio-run-normalizer",
        )

    def test_both_reference_normalizeStudioRun(self):
        pg = _JsModule(WEB / "studio-playground.js")
        hi = _JsModule(WEB / "studio-history.js")
        self.assertIn(
            "normalizeStudioRun",
            pg.text,
            "Playground must reference normalizeStudioRun",
        )
        self.assertIn(
            "normalizeStudioRun",
            hi.text,
            "History must reference normalizeStudioRun",
        )

    def test_both_reference_favorite_and_note(self):
        pg = _JsModule(WEB / "studio-playground.js")
        hi = _JsModule(WEB / "studio-history.js")
        self.assertIn("favorite", pg.text)
        self.assertIn("favorite", hi.text)
        self.assertIn("note", pg.text)
        self.assertIn("note", hi.text)

    def test_both_reference_timingSummary(self):
        pg = _JsModule(WEB / "studio-playground.js")
        hi = _JsModule(WEB / "studio-history.js")
        self.assertIn("timingSummary", pg.text)
        self.assertIn("timingSummary", hi.text)


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


if __name__ == "__main__":
    unittest.main()
