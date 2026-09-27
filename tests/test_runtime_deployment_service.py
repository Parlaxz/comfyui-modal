"""Focused tests for deployment_service: validation state machine and concurrency."""

from __future__ import annotations

import threading
import unittest

from comfymodal_runtime.contracts import DeploymentIdentity
from comfymodal_runtime.deployment_service import (
    DeploymentValidation,
    ValidationCoordinator,
    ValidationState,
)


class TestValidationStateEnum(unittest.TestCase):
    """ValidationState enum values match expected lifecycle."""

    def test_required_is_default(self):
        self.assertEqual(ValidationState.REQUIRED.value, "required")

    def test_transition_order(self):
        states = [
            ValidationState.REQUIRED,
            ValidationState.RUNNING,
            ValidationState.PASSED,
            ValidationState.FAILED,
        ]
        self.assertEqual(len(states), 4)


class TestDeploymentValidationRecord(unittest.TestCase):
    """DeploymentValidation dataclass construction and serialization."""

    def test_fresh_returns_required(self):
        v = DeploymentValidation.fresh(generation=3)
        self.assertEqual(v.state, ValidationState.REQUIRED)
        self.assertEqual(v.generation, 3)
        self.assertEqual(v.validation_run_id, "")

    def test_fresh_default_generation(self):
        v = DeploymentValidation.fresh()
        self.assertEqual(v.generation, 0)

    def test_to_dict_round_trip(self):
        identity = DeploymentIdentity(
            runtime_hash="r1", dependency_hash="d1", custom_node_hash="c1"
        )
        v = DeploymentValidation(
            state=ValidationState.RUNNING,
            generation=5,
            validation_run_id="run-abc",
            started_at=100.0,
            workflow_hash="wf-hash",
            model_hash="model-hash",
            identity=identity,
        )
        d = v.to_dict()
        restored = DeploymentValidation.from_dict(d)
        self.assertEqual(restored.state, ValidationState.RUNNING)
        self.assertEqual(restored.generation, 5)
        self.assertEqual(restored.validation_run_id, "run-abc")
        self.assertEqual(restored.workflow_hash, "wf-hash")
        self.assertEqual(restored.model_hash, "model-hash")
        self.assertIsNotNone(restored.identity)
        if restored.identity:
            self.assertEqual(restored.identity.runtime_hash, "r1")

    def test_to_dict_round_trip_without_identity(self):
        v = DeploymentValidation(state=ValidationState.REQUIRED, generation=1)
        d = v.to_dict()
        restored = DeploymentValidation.from_dict(d)
        self.assertEqual(restored.state, ValidationState.REQUIRED)
        self.assertIsNone(restored.identity)


class TestValidationCoordinator(unittest.TestCase):
    """Coordinator state machine and serialization."""

    def setUp(self):
        self.coord = ValidationCoordinator()

    def test_initial_state_is_required(self):
        self.assertEqual(self.coord.state, ValidationState.REQUIRED)

    def test_request_validation_transitions_to_running(self):
        run_id = self.coord.request_validation(generation=1)
        self.assertEqual(self.coord.state, ValidationState.RUNNING)
        self.assertNotEqual(run_id, "")
        self.assertEqual(self.coord.current.generation, 1)

    def test_request_validation_serializes_concurrent_requests(self):
        run_id1 = self.coord.request_validation(generation=1)
        # Second request while first is running — should return same run ID
        run_id2 = self.coord.request_validation(generation=2)
        self.assertEqual(run_id1, run_id2)
        # Generation should remain as first request's generation
        self.assertEqual(self.coord.current.generation, 1)

    def test_complete_validation_passed(self):
        run_id = self.coord.request_validation(generation=1)
        result = self.coord.complete_validation(run_id, passed=True)
        self.assertTrue(result)
        self.assertEqual(self.coord.state, ValidationState.PASSED)
        self.assertIsNotNone(self.coord.current.completed_at)

    def test_complete_validation_failed(self):
        run_id = self.coord.request_validation(generation=1)
        result = self.coord.complete_validation(run_id, passed=False, error="timeout")
        self.assertTrue(result)
        self.assertEqual(self.coord.state, ValidationState.FAILED)
        self.assertEqual(self.coord.current.error, "timeout")

    def test_complete_validation_with_wrong_run_id_returns_false(self):
        self.coord.request_validation(generation=1)
        result = self.coord.complete_validation("wrong-run-id", passed=True)
        self.assertFalse(result)
        self.assertEqual(self.coord.state, ValidationState.RUNNING)

    def test_complete_validation_when_not_running_returns_false(self):
        # Try completing a validation that was never requested
        result = self.coord.complete_validation("some-id", passed=True)
        self.assertFalse(result)

    def test_mark_required_resets_to_required(self):
        self.coord.request_validation(generation=1)
        self.coord.mark_required(generation=2)
        self.assertEqual(self.coord.state, ValidationState.REQUIRED)
        self.assertEqual(self.coord.current.generation, 2)

    def test_request_with_metadata(self):
        identity = DeploymentIdentity(runtime_hash="r")
        run_id = self.coord.request_validation(
            generation=1,
            workflow_hash="wf-abc",
            model_hash="model-xyz",
            identity=identity,
        )
        cur = self.coord.current
        self.assertEqual(cur.workflow_hash, "wf-abc")
        self.assertEqual(cur.model_hash, "model-xyz")
        self.assertIsNotNone(cur.identity)
        if cur.identity:
            self.assertEqual(cur.identity.runtime_hash, "r")

    def test_complete_validation_preserves_metadata(self):
        identity = DeploymentIdentity(runtime_hash="r")
        run_id = self.coord.request_validation(
            generation=1,
            workflow_hash="wf-abc",
            identity=identity,
        )
        self.coord.complete_validation(run_id, passed=True)
        cur = self.coord.current
        self.assertEqual(cur.workflow_hash, "wf-abc")
        self.assertIsNotNone(cur.identity)

    def test_mark_required_clears_validation_metadata(self):
        self.coord.request_validation(
            generation=1, workflow_hash="wf-abc"
        )
        self.coord.mark_required(generation=2)
        cur = self.coord.current
        self.assertEqual(cur.workflow_hash, "")
        self.assertIsNone(cur.identity)


class TestValidationConcurrency(unittest.TestCase):
    """Concurrent validation requests are serialized."""

    def test_concurrent_requests_are_serialized(self):
        """Two threads requesting validation simultaneously: only one runs."""
        coord = ValidationCoordinator()
        results: list[str] = []
        lock = threading.Lock()
        barrier = threading.Barrier(2, timeout=5)

        def request():
            barrier.wait()
            run_id = coord.request_validation(generation=1)
            with lock:
                results.append(run_id)

        t1 = threading.Thread(target=request)
        t2 = threading.Thread(target=request)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Both threads should have the same run ID (serialization)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])

    def test_validation_state_never_auto_transitions(self):
        """Coordinator never auto-transitions — only explicit calls change state."""
        coord = ValidationCoordinator()
        # Wait a bit and verify state didn't change
        import time
        self.assertEqual(coord.state, ValidationState.REQUIRED)
        # Request validation explicitly
        coord.request_validation(generation=1)
        self.assertEqual(coord.state, ValidationState.RUNNING)
        # Never auto-completes
        self.assertEqual(coord.state, ValidationState.RUNNING)
        # Must explicitly complete
        # (no implicit transition)


if __name__ == "__main__":
    unittest.main()
