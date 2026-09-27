import unittest

from ra11f.harness import WorkflowClosureResolver, default_records, semantic_prompt, synthetic_prompt, unsafe_prompt


class RA11FResolverTests(unittest.TestCase):
    def setUp(self):
        self.resolver = WorkflowClosureResolver(default_records())

    def test_generic_closure_collects_semantics_and_preserves_string_ids(self):
        result = self.resolver.resolve(semantic_prompt())
        self.assertTrue(result.safe)
        self.assertEqual(result.node_ids, ["B-v3", "B-global", "B-lazy", "B-sampler"])
        self.assertIn("synthetic_v3", result.workflow_runtime_closure)
        self.assertIn("synthetic_global", result.workflow_runtime_closure)
        self.assertIn("synthetic_lazy", result.workflow_runtime_closure)
        self.assertIn("synthetic_sampler", result.workflow_runtime_closure)
        self.assertIn("sampler_scheduler", result.semantic_requirements)
        self.assertIn("graph_global_providers", result.semantic_requirements)
        self.assertIn("preprocessing", result.semantic_requirements)
        resumed = self.resolver.resolve(semantic_prompt(), initialized=["synthetic_v3"])
        self.assertIn("synthetic_v3", resumed.process_initialized_set)
        self.assertNotIn("synthetic_v3", resumed.missing_from_process)

    def test_aliases_and_collision_records_are_not_numeric(self):
        result = self.resolver.resolve(synthetic_prompt())
        self.assertTrue(result.safe)
        self.assertEqual(result.node_ids[0], "A-1")
        self.assertIn("v1-alias", result.aliases)
        self.assertIn("synthetic_collision_early", result.workflow_runtime_closure)
        self.assertIn("synthetic_collision_late", result.workflow_runtime_closure)

    def test_unknown_or_unsafe_is_not_authorized(self):
        result = self.resolver.resolve(unsafe_prompt())
        self.assertFalse(result.safe)
        self.assertTrue(any("P3" in reason or "safe" in reason for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
