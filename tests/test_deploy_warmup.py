import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "deploy_warmup.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("deploy_warmup.py missing")
    spec = importlib.util.spec_from_file_location("deploy_warmup", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _callable(module, name):
    fn = getattr(module, name, None)
    if fn is None:
        raise AssertionError(f"deploy_warmup.py missing public symbol: {name}")
    return fn


class DeploymentGenerationTests(unittest.TestCase):
    def test_same_inputs_same_generation(self):
        m = load_module()
        a = m.deployment_generation("v1.0", "fp_abc", 12345.0)
        b = m.deployment_generation("v1.0", "fp_abc", 12345.0)
        self.assertEqual(a, b)

    def test_different_version_different_generation(self):
        m = load_module()
        a = m.deployment_generation("v1.0", "fp_abc", 12345.0)
        b = m.deployment_generation("v1.1", "fp_abc", 12345.0)
        self.assertNotEqual(a, b)

    def test_different_fingerprint_different_generation(self):
        m = load_module()
        a = m.deployment_generation("v1.0", "fp_abc", 12345.0)
        b = m.deployment_generation("v1.0", "fp_xyz", 12345.0)
        self.assertNotEqual(a, b)

    def test_different_timestamp_different_generation(self):
        m = load_module()
        a = m.deployment_generation("v1.0", "fp_abc", 12345.0)
        b = m.deployment_generation("v1.0", "fp_abc", 12346.0)
        self.assertNotEqual(a, b)


class WarmupStateTests(unittest.TestCase):
    def test_initial_state_is_invalid(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            self.assertFalse(state.is_warmed())
            self.assertEqual(state.deployment_generation(), "")

    def test_invalidate_marks_unwarmed(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".deploy_warmup_state.json"
            state = m.WarmupState(path)
            state.mark_warmed(m.deployment_generation("v1", "fp", 1.0),
                               warmup_run_id="run_warm")
            self.assertTrue(state.is_warmed())
            state.invalidate()
            self.assertFalse(state.is_warmed())
            self.assertEqual(state.warmup_run_id(), "")

    def test_mark_warmed_persists(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".deploy_warmup_state.json"
            state = m.WarmupState(path)
            gen = m.deployment_generation("v1", "fp", 1.0)
            state.mark_warmed(gen, warmup_run_id="run_warm")
            state2 = m.WarmupState(path)
            self.assertTrue(state2.is_warmed())
            self.assertEqual(state2.deployment_generation(), gen)
            self.assertEqual(state2.warmup_run_id(), "run_warm")

    def test_new_generation_marks_unwarmed(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".deploy_warmup_state.json"
            state = m.WarmupState(path)
            state.mark_warmed(m.deployment_generation("v1", "fp", 1.0), warmup_run_id="r1")
            self.assertTrue(state.is_warmed())
            state.mark_deploy_started("v2", "fp", 2.0)
            self.assertFalse(state.is_warmed())


class EnsureWarmupTests(unittest.TestCase):
    def test_ensure_warmup_returns_already_warmed(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            gen = m.deployment_generation("v1", "fp", 1.0)
            state.mark_warmed(gen, warmup_run_id="r1")
            result = m.ensure_warmup(state, "v1", "fp", 1.0)
            self.assertEqual(result["status"], "already_warmed")
            self.assertEqual(result["warmup_run_id"], "r1")

    def test_ensure_warmup_runs_warmup_when_unwarmed(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            result = m.ensure_warmup(state, "v1", "fp", 1.0)
            self.assertEqual(result["status"], "warmed")
            self.assertTrue(state.is_warmed())
            self.assertNotEqual(result["warmup_run_id"], "")

    def test_ensure_warmup_reruns_when_deployment_changed(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            state.mark_warmed(m.deployment_generation("v1", "fp", 1.0), warmup_run_id="r1")
            result = m.ensure_warmup(state, "v2", "fp", 1.0)
            self.assertEqual(result["status"], "warmed")
            self.assertNotEqual(result["warmup_run_id"], "r1")


class ExperimentGateTests(unittest.TestCase):
    def test_gate_blocks_when_unwarmed(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            with self.assertRaises(m.WarmupRequiredError):
                m.gate_experiment(state, "v1", "fp", 1.0)

    def test_gate_passes_when_warmed(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            state.mark_warmed(m.deployment_generation("v1", "fp", 1.0), warmup_run_id="r1")
            m.gate_experiment(state, "v1", "fp", 1.0)


class RedeployStateMachineTests(unittest.TestCase):
    def test_redeploy_walkthrough(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            seq = m.RedeployStateMachine(state)
            self.assertEqual(seq.status(), "idle")
            seq.start_deploy()
            self.assertEqual(seq.status(), "deploying")
            seq.deploy_succeeded("v1", "fp", 1000.0)
            self.assertEqual(seq.status(), "waiting_for_modal")
            seq.modal_ready()
            self.assertEqual(seq.status(), "restarting_comfyui")
            seq.comfyui_restarting()
            self.assertEqual(seq.status(), "waiting_for_comfyui")
            seq.comfyui_ready()
            self.assertEqual(seq.status(), "restoring_ui")
            seq.ui_restored()
            self.assertEqual(seq.status(), "running_warmup")
            seq.warmup_succeeded(warmup_run_id="r1")
            self.assertEqual(seq.status(), "ready")
            self.assertTrue(state.is_warmed())

    def test_deploy_failure_does_not_restart(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            seq = m.RedeployStateMachine(state)
            seq.start_deploy()
            seq.deploy_failed("boom")
            self.assertEqual(seq.status(), "failed")
            self.assertFalse(state.is_warmed())

    def test_warmup_failure_keeps_unwarmed(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            seq = m.RedeployStateMachine(state)
            seq.start_deploy()
            seq.deploy_succeeded("v1", "fp", 1.0)
            seq.modal_ready()
            seq.comfyui_restarting()
            seq.comfyui_ready()
            seq.ui_restored()
            seq.warmup_failed("oops")
            self.assertEqual(seq.status(), "unwarmed")
            self.assertFalse(state.is_warmed())

    def test_invalid_transition_raises(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            seq = m.RedeployStateMachine(state)
            with self.assertRaises(m.WarmupError):
                seq.modal_ready()  # from "idle"


class UIRestorationStateTests(unittest.TestCase):
    def test_persist_and_load_ui_state(self):
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            state.set_ui_state({"active_tab": "results",
                                "selected_experiment": "exp_x",
                                "results_open": True})
            state2 = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            ui = state2.get_ui_state()
            self.assertEqual(ui["active_tab"], "results")
            self.assertEqual(ui["selected_experiment"], "exp_x")
            self.assertTrue(ui["results_open"])


class WarmupLifecycleTests(unittest.TestCase):
    """Warmup lifecycle correctness:
    - deployment should not be treated ready while warmup pending
    - missing or failing warmup workflow keeps state unwarmed/failed
    - stale warmup completion rejected
    - exactly one warmup per deployment generation"""

    def test_not_warmed_while_warming(self):
        """is_warmed() must return False while warmup is in progress (warming)."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            gen = m.deployment_generation("v1", "fp", 1.0)
            state.mark_warmup_started(gen, warmup_run_id="w1")
            self.assertTrue(state.is_warming())
            self.assertFalse(state.is_warmed())

    def test_warmup_succeeded_becomes_warmed(self):
        """mark_warmed after warmup_started transitions to warmed."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            gen = m.deployment_generation("v1", "fp", 1.0)
            state.mark_warmup_started(gen, warmup_run_id="w1")
            state.mark_warmed(gen, warmup_run_id="w1")
            self.assertFalse(state.is_warming())
            self.assertTrue(state.is_warmed())

    def test_warmup_failed_keeps_unwarmed(self):
        """mark_warmup_failed transitions to failed/unwarmed."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            gen = m.deployment_generation("v1", "fp", 1.0)
            state.mark_warmup_started(gen, warmup_run_id="w1")
            state.mark_warmup_failed(gen, "oops")
            self.assertFalse(state.is_warming())
            self.assertFalse(state.is_warmed())
            self.assertIn("oops", state.warmup_error())

    def test_double_warmup_start_rejected(self):
        """Exactly one warmup per deployment generation — second start raises."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            gen = m.deployment_generation("v1", "fp", 1.0)
            state.mark_warmup_started(gen, warmup_run_id="w1")
            with self.assertRaises(m.WarmupError):
                state.mark_warmup_started(gen, warmup_run_id="w2")

    def test_stale_warmup_completion_rejected(self):
        """Completing warmup with wrong generation raises WarmupError."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            gen1 = m.deployment_generation("v1", "fp", 1.0)
            gen2 = m.deployment_generation("v2", "fp", 1.0)
            state.mark_deploy_started("v1", "fp", 1.0)
            with self.assertRaises(m.WarmupError):
                state.mark_warmed(gen2, warmup_run_id="w_stale")

    def test_new_deploy_resets_warming(self):
        """mark_deploy_started resets warmup_status so a new warmup can start."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            gen1 = m.deployment_generation("v1", "fp", 1.0)
            state.mark_warmup_started(gen1, warmup_run_id="w1")
            state.mark_deploy_started("v2", "fp", 2.0)
            self.assertFalse(state.is_warming())
            self.assertFalse(state.is_warmed())
            # New warmup should work
            gen2 = state.deployment_generation()
            state.mark_warmup_started(gen2, warmup_run_id="w2")
            state.mark_warmed(gen2, warmup_run_id="w2")
            self.assertTrue(state.is_warmed())

    def test_gate_blocks_warming(self):
        """gate_experiment_on_stored_generation blocks when warming (not yet warmed)."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            gen = m.deployment_generation("v1", "fp", 1.0)
            state.mark_deploy_started("v1", "fp", 1.0)
            state.mark_warmup_started(gen, warmup_run_id="w1")
            with self.assertRaises(m.WarmupRequiredError):
                m.gate_experiment_on_stored_generation(state)

    def test_ensure_warmup_rejects_when_already_warming(self):
        """ensure_warmup raises when warmup is already in progress."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            gen = m.deployment_generation("v1", "fp", 1.0)
            state.mark_warmup_started(gen, warmup_run_id="w1")
            with self.assertRaises(m.WarmupError):
                m.ensure_warmup(state, "v1", "fp", 1.0)

    def test_ensure_warmup_runs_when_not_yet_warming(self):
        """ensure_warmup runs warmup when state is not warming and not warmed."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            result = m.ensure_warmup(state, "v1", "fp", 1.0)
            self.assertEqual(result["status"], "warmed")
            self.assertTrue(state.is_warmed())

    def test_warmup_failed_persists_error_message(self):
        """Error event preserves error message in warmup_error."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            gen = m.deployment_generation("v1", "fp", 1.0)
            state.mark_deploy_started("v1", "fp", 1.0)
            state.mark_warmup_failed(gen, "connection timeout")
            self.assertFalse(state.is_warmed())
            self.assertEqual(state.warmup_error(), "connection timeout")
            self.assertIn("timeout", state.snapshot().get("warmup_error", ""))


class DeployStatusLifecycleTests(unittest.TestCase):
    """Verifies the deploy → unwarmed → warming → ready/failed lifecycle.

    The WarmupState must NOT report is_warmed() immediately after
    mark_deploy_started; must report is_warming() during warmup;
    must report is_warmed() only after mark_warmed.

    These tests validate the contract that _deploy_status mirrors —
    the __init__.py code reads WarmupState to determine UI-facing
    deploy status.
    """

    def test_deploy_started_is_unwarmed_not_warming(self):
        """After mark_deploy_started, state is unwarmed
        (not warmed, not warming, empty warmup_status)."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            state.mark_deploy_started("v1", "fp", 1000.0)
            self.assertFalse(state.is_warmed())
            self.assertFalse(state.is_warming())
            self.assertEqual(state.warmup_status(), "")

    def test_full_deploy_warmup_lifecycle_success(self):
        """Full lifecycle: deploy → warmup_started → warmup_succeeded."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")

            # Deploy starts — unwarmed
            gen = state.mark_deploy_started("v1", "fp", 1000.0)
            self.assertFalse(state.is_warmed())
            self.assertFalse(state.is_warming())
            self.assertEqual(state.warmup_status(), "")

            # Warmup starts — warming, not warmed
            state.mark_warmup_started(gen, warmup_run_id="w1")
            self.assertTrue(state.is_warming())
            self.assertFalse(state.is_warmed())
            self.assertEqual(state.warmup_status(), "warming")

            # Warmup succeeds — warmed, not warming
            state.mark_warmed(gen, warmup_run_id="w1")
            self.assertTrue(state.is_warmed())
            self.assertFalse(state.is_warming())
            self.assertEqual(state.warmup_status(), "warmed")

    def test_deploy_then_warmup_failed(self):
        """Deploy → warmup_failed keeps state unwarmed with error."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            gen = state.mark_deploy_started("v1", "fp", 1000.0)
            state.mark_warmup_started(gen, warmup_run_id="w1")
            state.mark_warmup_failed(gen, "connection error")
            self.assertFalse(state.is_warmed())
            self.assertFalse(state.is_warming())
            self.assertEqual(state.warmup_status(), "failed")
            self.assertIn("connection error", state.warmup_error())

    def test_deploy_unwarmed_not_ready_for_experiments(self):
        """After deploy, gate_experiment_on_stored_generation blocks
        because the deployment is not warmed."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            state = m.WarmupState(Path(tmp) / ".deploy_warmup_state.json")
            state.mark_deploy_started("v1", "fp", 1000.0)
            with self.assertRaises(m.WarmupRequiredError):
                m.gate_experiment_on_stored_generation(state)


class WorkspaceSwitchInvalidationTests(unittest.TestCase):
    """A8: Workspace switch invalidates stale warmup generation."""

    def test_workspace_change_invalidates_warmup(self):
        """on_workspace_changed with different IDs invalidates warmup."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".deploy_warmup_state.json"
            state = m.WarmupState(path)
            gen = m.deployment_generation("v1", "fp", 1.0)
            state.mark_warmed(gen, warmup_run_id="r1")
            self.assertTrue(state.is_warmed())

            state.on_workspace_changed("ws_old", "ws_new")
            self.assertFalse(state.is_warmed(),
                "warmup must be invalidated after workspace change")

    def test_same_workspace_preserves_warmup(self):
        """on_workspace_changed with same ID preserves warmup."""
        m = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".deploy_warmup_state.json"
            state = m.WarmupState(path)
            gen = m.deployment_generation("v1", "fp", 1.0)
            state.mark_warmed(gen, warmup_run_id="r1")
            self.assertTrue(state.is_warmed())

            state.on_workspace_changed("ws_same", "ws_same")
            self.assertTrue(state.is_warmed(),
                "warmup must be preserved when workspace ID is unchanged")


if __name__ == "__main__":
    unittest.main()
