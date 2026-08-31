import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class RA11FSubprocessTests(unittest.TestCase):
    def test_each_arm_emits_schema_and_experiment_uses_fresh_processes(self):
        for arm in ("FULL", "DERIVED", "FALLBACK", "SEQUENCE"):
            completed = subprocess.run([sys.executable, "-m", "ra11f", "--arm", arm], capture_output=True, text=True, check=True)
            result = json.loads(completed.stdout)
            self.assertEqual(result["schema_version"], "ra11f.v1")
            self.assertEqual(result["arm"], arm)
            self.assertIn("resource_capture", result)
            self.assertIn("filesystem", result)
            evidence = result["output_behavior_evidence"]
            self.assertTrue(evidence["synthetic_only"])
            self.assertFalse(evidence["execution_claim"])
            if arm in ("FULL", "DERIVED"):
                self.assertEqual(evidence["status"], "UNPROVEN_NOT_EXECUTED")
                self.assertEqual(evidence["reason"], "models/GPU/Modal/output path were not run")
            else:
                self.assertEqual(evidence["status"], "SYNTHETIC_ONLY")
                self.assertEqual(len(evidence["behavior"]["digest"]), 64)
        with tempfile.TemporaryDirectory(prefix="ra11f_test_") as directory:
            artifact = Path(directory) / "experiment.json"
            completed = subprocess.run([sys.executable, "-m", "ra11f", "--experiment", str(artifact)], capture_output=True, text=True, check=True)
            result = json.loads(completed.stdout)
            self.assertTrue(result["command_metadata"]["fresh_subprocesses"])
            self.assertEqual(set(result["arms"]), {"FULL", "DERIVED", "FALLBACK", "SEQUENCE"})
            self.assertEqual(result["arms"]["FALLBACK"]["operation"]["mode"], "complete_fallback")
            self.assertTrue(result["parity"]["full_vs_derived_relevant_v1_mapping_parity"])
            raw_parity = result["parity"]["raw_registration_global_parity"]
            self.assertTrue(raw_parity["all_relevant_fields_match"])
            for field in ("display_mappings", "v3_node_list", "v3_schemas", "RELATIVE_PYTHON_MODULE", "aliases", "generated_ids", "sampler_scheduler_registries", "mutable_registries", "model_attention_hooks", "graph_global_providers", "preprocessing", "routes", "web_dirs", "model_paths", "import_order", "import_failures", "collision_override_errors"):
                self.assertIn(field, raw_parity["fields"])
            self.assertTrue(raw_parity["full_out_of_scope"]["collision_override_errors"])
            self.assertTrue(artifact.exists())


if __name__ == "__main__":
    unittest.main()
