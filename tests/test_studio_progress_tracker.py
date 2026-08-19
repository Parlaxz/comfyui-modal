"""Structural AST tests for the Studio progress tracker in comfymodal-progress.js.

These tests verify that:
  1. The scoped tracker subscribes to experiment.worker.progress and experiment.event
  2. The experiment run path creates a scoped tracker instead of only disposing
  3. Modal execution sampler events map to state updates

All assertions are scoped to specific function sections to avoid false positives
from other handlers that contain the same strings (e.g. onProgress also has
samplerStep/samplerMaximum/samplerPercent assignments).
"""
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROGRESS_PATH = REPO_ROOT / "web" / "comfymodal-progress.js"
PLAYGROUND_PATH = REPO_ROOT / "web" / "studio-playground.js"
EXPERIMENT_MODE_PATH = REPO_ROOT / "web" / "studio-experiment-mode.js"


class _ProgressSourceMixin:
    """Mixin that precomputes narrow function-section slices of the progress JS."""

    def setUp(self):
        self.source = PROGRESS_PATH.read_text(encoding="utf-8")
        # Function boundaries within createScopedTracker (the exported function
        # that contains all the event handlers we care about).
        self._worker_start = self.source.index("function onExperimentWorkerProgress")
        self._event_start = self.source.index("function onExperimentEvent")
        # Narrow section covering only onExperimentWorkerProgress's body
        self._worker_section = self.source[self._worker_start:self._event_start]
        # Narrow section covering onExperimentEvent's body (1500 chars is enough)
        self._event_section = self.source[self._event_start:self._event_start + 1500]


class ScopedTrackerSubscriptionTests(_ProgressSourceMixin, unittest.TestCase):
    """Verify createScopedTracker wires experiment event handlers."""

    def test_subscribes_to_experiment_worker_progress(self):
        """Scoped tracker must subscribe to experiment.worker.progress."""
        # Check the exact _addListener line to avoid matching the comment
        # above the function definition in another section.
        self.assertIn(
            '_addListener("experiment.worker.progress"',
            self.source,
            "createScopedTracker must subscribe to experiment.worker.progress events",
        )

    def test_subscribes_to_experiment_event(self):
        """Scoped tracker must subscribe to experiment.event."""
        self.assertIn(
            '_addListener("experiment.event"',
            self.source,
            "createScopedTracker must subscribe to experiment.event",
        )

    def test_worker_progress_handler_updates_sampler_step(self):
        """experiment.worker.progress handler must update samplerStep."""
        self.assertIn(
            "state.samplerStep = d.step ?? d.value",
            self._worker_section,
            "experiment.worker.progress must map step/value to samplerStep",
        )

    def test_worker_progress_handler_updates_sampler_maximum(self):
        """experiment.worker.progress handler must update samplerMaximum."""
        self.assertIn(
            "state.samplerMaximum = d.max ?? d.max_step ?? d.maxStep ?? state.samplerMaximum",
            self._worker_section,
            "experiment.worker.progress must map max fields to samplerMaximum",
        )

    def test_worker_progress_handler_updates_sampler_percent(self):
        """experiment.worker.progress handler must compute samplerPercent."""
        self.assertIn(
            "state.samplerPercent = (state.samplerStep / state.samplerMaximum) * 100",
            self._worker_section,
            "experiment.worker.progress must compute sampler percent from step/max",
        )

    def test_worker_progress_handler_updates_queue_position(self):
        """experiment.worker.progress handler must update queuePosition."""
        self.assertIn(
            "state.queuePosition = d.queue",
            self._worker_section,
            "experiment.worker.progress must map queue field to queuePosition",
        )

    def test_worker_progress_soft_locks_tracker(self):
        """experiment.worker.progress must set _locked = true on matching experiment_id."""
        self.assertIn(
            "_locked = true",
            self._worker_section,
            "experiment.worker.progress must soft-lock the tracker",
        )

    def test_worker_progress_starts_timer_on_soft_lock(self):
        """experiment.worker.progress must start timer on soft-lock."""
        self.assertIn(
            "_startTimer",
            self._worker_section,
            "experiment.worker.progress handler must start timer on soft-lock",
        )

    def test_worker_progress_matches_experiment_id(self):
        """experiment.worker.progress must filter by experiment_id matching identity."""
        self.assertIn(
            "eventExperimentId === _identity.experimentId",
            self._worker_section,
            "experiment.worker.progress must only respond to matching experiment_id",
        )


class ExperimentEventHandlerTests(_ProgressSourceMixin, unittest.TestCase):
    """Verify the experiment.event handler detects terminal events."""

    def test_experiment_completed_maps_to_done(self):
        """experiment.completed must set stage to 'done'."""
        self.assertIn(
            'eventType === "experiment.completed"',
            self._event_section,
            "experiment.event must detect experiment.completed",
        )

    def test_experiment_stopped_maps_to_done(self):
        """experiment.stopped must set stage to 'done'."""
        self.assertIn(
            'eventType === "experiment.stopped"',
            self._event_section,
            "experiment.event must detect experiment.stopped",
        )

    def test_experiment_error_maps_to_error(self):
        """experiment.error must set stage to 'error'."""
        self.assertIn(
            'eventType === "experiment.error"',
            self._event_section,
            "experiment.event must detect experiment.error",
        )

    def test_experiment_failed_fatal_maps_to_error(self):
        """experiment.failed_fatal must set stage to 'error'."""
        self.assertIn(
            'eventType === "experiment.failed_fatal"',
            self._event_section,
            "experiment.event must detect experiment.failed_fatal",
        )

    def test_experiment_event_sets_state_done_on_terminal(self):
        """Terminal experiment events must set state.stage = 'done'."""
        self.assertIn(
            'state.stage = "done"',
            self._event_section,
            "experiment.event handler must set stage to 'done' on terminal events",
        )

    def test_experiment_event_sets_state_error_on_failure(self):
        """Error experiment events must set state.stage = 'error'."""
        self.assertIn(
            'state.stage = "error"',
            self._event_section,
            "experiment.event handler must set stage to 'error' on failure events",
        )

    def test_experiment_event_rejects_single_run_stray_events(self):
        """onExperimentEvent must reject events with experiment_id when identity has none."""
        # The guard: if eventExperimentId is set AND identity lacks experimentId → return.
        # Look for the pattern just after eventExperimentId is extracted.
        self.assertIn(
            "if (eventExperimentId)",
            self._event_section,
            "experiment.event must guard on eventExperimentId presence",
        )
        self.assertIn(
            "!_identity.experimentId",
            self._event_section,
            "experiment.event must check _identity.experimentId is not set",
        )


class ExperimentRunPathTests(unittest.TestCase):
    """Verify the experiment run submission path in studio-playground.js and
    the scoped-tracker wiring in studio-experiment-mode.js."""

    def setUp(self):
        self.source = PLAYGROUND_PATH.read_text(encoding="utf-8")
        # Scope to the experiment run onclick handler — the first
        # `btn.onclick = async () => {` in the file (experiment mode).
        self._exp_section = self.source[self.source.index("btn.onclick = async () => {"):]
        # The experiment click handler in studio-experiment-mode.js wires the
        # scoped tracker after executeExperimentRun returns. Narrow section
        # covering the import → create → dispose-old → assign-new block.
        exp_source = EXPERIMENT_MODE_PATH.read_text(encoding="utf-8")
        self._tracker_section = exp_source[
            exp_source.index('var { createScopedTracker } = await import("./comfymodal-progress.js")'):exp_source.index("_expTracker.start();")
        ]

    def test_experiment_run_creates_scoped_tracker(self):
        """Experiment run path must import and call createScopedTracker."""
        self.assertIn(
            'var { createScopedTracker } = await import("./comfymodal-progress.js")',
            self._tracker_section,
            "Experiment run path must import createScopedTracker to wire experiment events",
        )
        self.assertIn(
            "createScopedTracker(_expApi",
            self._tracker_section,
            "Experiment run path must create the scoped tracker with the api",
        )

    def test_experiment_run_passes_experiment_id(self):
        """Experiment run path must pass experimentId to scoped tracker."""
        self.assertIn(
            "result.experimentId",
            self._exp_section,
            "Experiment run path must pass result.experimentId to scoped tracker",
        )

    def test_experiment_run_does_not_only_dispose(self):
        """Experiment run path must not have the 'experiments use polling' dispose pattern."""
        self.assertNotIn(
            "experiments use polling",
            self._exp_section,
            "Experiment run path should not have 'experiments use polling' comment"
            " — scoped tracker is now wired for experiment events",
        )

    def test_experiment_run_disposes_before_create(self):
        """Experiment run path must dispose previous tracker before assigning new one."""
        self.assertIn(
            "var _old = state.playground._scopedTracker",
            self._tracker_section,
            "Experiment run path must capture the previous scoped tracker",
        )
        self.assertIn(
            "_old.dispose()",
            self._tracker_section,
            "Experiment run path must dispose the previous scoped tracker",
        )
        self.assertIn(
            "state.playground._scopedTracker = _expTracker",
            self._tracker_section,
            "Experiment run path must assign the new scoped tracker after disposing the old one",
        )


class ModalExecutionSamplerMappingTests(_ProgressSourceMixin, unittest.TestCase):
    """Verify sampler progress from Modal execution maps to scoped tracker state."""

    def test_modal_sampler_step_maps_to_state(self):
        """Modal sampler step must map to state.samplerStep in worker progress."""
        self.assertIn(
            "state.samplerStep",
            self._worker_section,
            "experiment.worker.progress handler must reference state.samplerStep",
        )

    def test_modal_sampler_max_maps_to_state(self):
        """Modal sampler max must map to state.samplerMaximum in worker progress."""
        self.assertIn(
            "state.samplerMaximum",
            self._worker_section,
            "experiment.worker.progress handler must reference state.samplerMaximum",
        )

    def test_modal_queue_position_maps_to_state(self):
        """Modal queue position must map to state.queuePosition in worker progress."""
        self.assertIn(
            "state.queuePosition",
            self._worker_section,
            "experiment.worker.progress handler must reference state.queuePosition",
        )

    def test_modal_progress_triggers_notify(self):
        """experiment.worker.progress handler must call _notify()."""
        self.assertIn(
            "_notify()",
            self._worker_section,
            "experiment.worker.progress handler must call _notify() to publish updates",
        )


class StartupTimerInitializationTests(unittest.TestCase):
    """Verify onModalStatus in both trackers starts timer on first startup phase.

    Root cause: modal_status startup phases set stage='startup' but did not
    initialize startTime. Subsequent execution_start is ignored by the re-entry
    guard (stage==='startup'), so the timer only started at phase='execution',
    losing all startup time. The fix adds startTime initialization at the first
    matching startup status when no startTime exists.
    """

    def setUp(self):
        self.source = PROGRESS_PATH.read_text(encoding="utf-8")

    def test_global_tracker_onModalStatus_starts_timer_on_startup_phase(self):
        """Global tracker onModalStatus must init startTime on startup phase."""
        # Locate the global tracker's onModalStatus (first occurrence)
        fn_start = self.source.index("  function onModalStatus(detail) {")
        # Termination: the Wire up events section follows in the global tracker
        fn_end = self.source.index("  // ── Wire up events", fn_start)
        section = self.source[fn_start:fn_end]
        self.assertIn(
            "if (!state.startTime)",
            section,
            "Global tracker onModalStatus must guard startTime initialization",
        )
        self.assertIn(
            "_startTimer();",
            section,
            "Global tracker onModalStatus must call _startTimer() on startup phase",
        )

    def test_scoped_tracker_onModalStatus_starts_timer_on_startup_phase(self):
        """Scoped tracker onModalStatus must init startTime on startup phase."""
        # Find the second onModalStatus (inside createScopedTracker)
        first_fn = self.source.index("  function onModalStatus(detail) {")
        fn_start = self.source.index("  function onModalStatus(detail) {", first_fn + 1)
        # The scoped tracker's onModalStatus is followed by Experiment event handlers
        fn_end = self.source.index("  // ── Experiment event handlers", fn_start)
        section = self.source[fn_start:fn_end]
        self.assertIn(
            "if (!state.startTime)",
            section,
            "Scoped tracker onModalStatus must guard startTime initialization",
        )
        self.assertIn(
            "_startTimer();",
            section,
            "Scoped tracker onModalStatus must call _startTimer() on startup phase",
        )


if __name__ == "__main__":
    unittest.main()
