import threading
import time
import unittest

import ra11f.harness as harness
from ra11f.harness import ProcessState, SyntheticDiscoveryAdapter, SyntheticPublishedEnvironment, WorkflowClosureResolver, _initialize, default_records, semantic_prompt, synthetic_prompt, unsafe_prompt


class RA11FProcessTests(unittest.TestCase):
    def test_unsafe_requirement_falls_back_before_selective_initialization(self):
        records = default_records()
        with SyntheticPublishedEnvironment(records) as env:
            state = ProcessState(env)
            result = _initialize(WorkflowClosureResolver(records), SyntheticDiscoveryAdapter(env, state), state, unsafe_prompt())
            self.assertEqual(result["mode"], "complete_fallback")
            self.assertEqual(result["selection_trace"][-1], "complete_discovery")
            self.assertFalse(result["selective_initialization_before_complete"])
            self.assertIn("synthetic_unsafe", state.attempted)

    def test_abab_initialization_is_monotonic_and_duplicate_safe(self):
        records = default_records()
        with SyntheticPublishedEnvironment(records) as env:
            state = ProcessState(env)
            resolver = WorkflowClosureResolver(records)
            adapter = SyntheticDiscoveryAdapter(env, state)
            for prompt in (synthetic_prompt(), semantic_prompt(), synthetic_prompt(), semantic_prompt()):
                _initialize(resolver, adapter, state, prompt)
            self.assertEqual(len(state.import_order), len(set(state.import_order)))
            self.assertTrue({"synthetic_v1", "synthetic_global", "synthetic_sampler"}.issubset(state.initialized))
            self.assertIn("synthetic_euler", state.registries["samplers"])
            self.assertIn("synthetic_attention_hook", state.hooks)
            self.assertIn("everywhere.provider", state.global_providers)

    def test_partial_failure_is_sticky_and_not_clean_uninitialized(self):
        records = default_records()
        with SyntheticPublishedEnvironment(records) as env:
            state = ProcessState(env)
            adapter = SyntheticDiscoveryAdapter(env, state)
            adapter.discover(["synthetic_partial"])
            self.assertNotIn("synthetic_partial", state.initialized)
            self.assertIn("synthetic_partial", state.attempted)
            self.assertIn("synthetic_partial", state.partial_failures)
            adapter.discover(["synthetic_partial"])
            self.assertEqual(state.import_order.count("synthetic_partial"), 1)
            self.assertEqual(len(state.errors), 1)

    def test_concurrent_initializers_are_serialized_across_import_and_registration(self):
        records = default_records()
        with SyntheticPublishedEnvironment(records) as env:
            state = ProcessState(env)
            adapter = SyntheticDiscoveryAdapter(env, state)
            start = threading.Barrier(4)
            counters_lock = threading.Lock()
            active_imports = 0
            max_active_imports = 0
            original_import = harness.importlib.import_module

            def observed_import(name):
                nonlocal active_imports, max_active_imports
                with counters_lock:
                    active_imports += 1
                    max_active_imports = max(max_active_imports, active_imports)
                try:
                    time.sleep(0.01)
                    return original_import(name)
                finally:
                    with counters_lock:
                        active_imports -= 1

            harness.importlib.import_module = observed_import
            errors = []
            try:
                def worker(package_id):
                    try:
                        start.wait()
                        adapter.discover([package_id])
                    except BaseException as exc:
                        errors.append(exc)

                threads = [
                    threading.Thread(target=worker, args=(package_id,))
                    for package_id in ("synthetic_v1", "synthetic_v3", "synthetic_global", "synthetic_lazy")
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)
                    if thread.is_alive():
                        errors.append("initializer thread did not finish")
            finally:
                harness.importlib.import_module = original_import

            self.assertEqual(errors, [])
            self.assertEqual(max_active_imports, 1)
            evidence = state.snapshot()["initialization_serialization"]
            self.assertTrue(evidence["serialized"])
            self.assertEqual(evidence["lock_scope"], "complete_package_initializer")
            self.assertEqual(evidence["max_concurrent_initializers"], 1)
            self.assertEqual(len(evidence["initializer_events"]), 4)

    def test_declared_side_effects_are_in_state_and_resource_snapshots(self):
        from ra11f.harness import run_arm

        result = run_arm("FULL")
        state = result["operation"]["state"]
        self.assertEqual(result["resource_capture"]["after"]["declared_side_effects"], state["declared_side_effects"])
        self.assertEqual(state["declared_side_effects"]["golden_fixture"]["routes"], ["/synthetic/golden"])
        self.assertIn("package-owned/synthetic_global/provider.marker", result["filesystem"]["package_owned_mutations"])


if __name__ == "__main__":
    unittest.main()
