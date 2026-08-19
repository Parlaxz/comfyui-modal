"""Wave-2 logical-output and replay contract scaffolding."""
from __future__ import annotations

import json
import unittest

from tests.phase_e_wave2_fixtures import (
    HISTORY_ASSET_PREFIX,
    PREVIEW_OPTIONS,
    featured_variant_generation,
    generate_original_placeholder_response,
    irreproducible_snapshot,
    logical_output_generation,
    missing_raw_hash_snapshot,
    output_intent_only_delta,
    remote_original_only_generation,
    replay_complete_snapshot,
    replay_experiment_cell_snapshot,
    retry_generation,
    two_logical_outputs_generation,
)


class PhaseEWave2LogicalOutputTests(unittest.TestCase):
    def test_derivatives_share_one_logical_output_and_preserve_provenance(self):
        record = logical_output_generation()
        self.assertEqual(record["output_count"], 1)
        self.assertEqual(len(record["outputs"]), 1)
        output = record["outputs"][0]
        self.assertEqual(output["logical_output_key"], "gen_wave2_logical_o0")
        self.assertEqual(output["attempt_ids"], [
            "run_wave2_preview", "run_wave2_original_old", "run_wave2_original_new",
        ])
        self.assertEqual([item["asset_type"] for item in output["asset_provenance"]], [
            "thumbnail", "preview", "original", "original",
        ])
        self.assertEqual(len(output["original_urls"]), 2)
        self.assertTrue(output["original_url"].endswith("gen_wave2_logical_new_orig"))

    def test_two_logical_keys_have_output_count_two_not_asset_count(self):
        record = two_logical_outputs_generation()
        self.assertEqual(record["output_count"], 2)
        self.assertEqual([o["logical_output_key"] for o in record["outputs"]], [
            "gen_wave2_two_o0", "gen_wave2_two_o1",
        ])
        self.assertEqual(sum(len(o["asset_provenance"]) for o in record["outputs"]), 5)

    def test_preview_variant_carries_mode_codec_quality_and_thumbnail(self):
        record = logical_output_generation()
        preview_attempt = record["attempts"][0]
        output = record["outputs"][0]
        self.assertEqual(PREVIEW_OPTIONS, {"enabled": True, "codec": "webp", "quality": 70})
        self.assertEqual(preview_attempt["mode"], "preview")
        self.assertEqual(preview_attempt["codec"], "webp")
        self.assertEqual(preview_attempt["quality"], 70)
        self.assertTrue(output["thumb_url"].startswith(HISTORY_ASSET_PREFIX))
        self.assertEqual(output["preview_codec"], "webp")
        self.assertEqual(output["preview_quality"], 70)

    def test_failed_original_retry_keeps_prior_preview_and_new_success(self):
        record = retry_generation()
        output = record["outputs"][0]
        self.assertEqual([a["status"] for a in record["attempts"]], ["completed", "failed", "completed"])
        self.assertTrue(output["preview_url"])
        self.assertTrue(output["original_url"])
        self.assertFalse(output["original_failed"])
        self.assertEqual(record["errors"][0]["message"], "Original upload failed")

    def test_featured_derivative_resolves_to_logical_output(self):
        for variant, expected_index in (("thumbnail", 0), ("preview", 1), ("older_original", 1)):
            with self.subTest(variant=variant):
                record = featured_variant_generation(variant)
                self.assertEqual(record["featured_output_index"], expected_index)
                featured = record["outputs"][expected_index]
                self.assertEqual(featured["logical_output_key"], f"gen_wave2_featured_{variant}_o{expected_index}")
                if variant == "older_original":
                    self.assertTrue(featured["original_url"].endswith("new_orig"))
                    self.assertTrue(any(item["asset_id"].endswith("old_orig") for item in featured["asset_provenance"]))

    def test_remote_original_only_is_available_without_raw_producer_uri(self):
        record = remote_original_only_generation()
        payload = json.dumps(record)
        output = record["outputs"][0]
        self.assertNotIn("modal://", payload)
        self.assertEqual(output["thumb_url"], "")
        self.assertEqual(output["preview_url"], "")
        self.assertTrue(output["original_url"].startswith(HISTORY_ASSET_PREFIX))
        self.assertFalse(output["original_failed"])


class PhaseEWave2ReplayContractTests(unittest.TestCase):
    def test_single_and_experiment_cell_replay_snapshots_are_complete(self):
        single = replay_complete_snapshot()
        cell = replay_experiment_cell_snapshot()
        self.assertEqual(single["execution_plan_json"]["workflow_hash"], single["workflow_hash"])
        self.assertEqual(cell["request_snapshot"], single)
        self.assertEqual(cell["generation_id"], "gen_phase_e_wave2_cell_0")

    def test_exact_plan_round_trip_and_output_intent_only_delta(self):
        original = replay_complete_snapshot()
        changed = output_intent_only_delta(original)
        original_plan = original["execution_plan_json"]
        changed_plan = changed["execution_plan_json"]
        self.assertEqual(changed_plan["workflow"], original_plan["workflow"])
        self.assertEqual(changed_plan["workflow_hash"], original_plan["workflow_hash"])
        self.assertEqual(changed_plan["source_workflow_hash"], original_plan["source_workflow_hash"])
        self.assertEqual(changed_plan["execution_options"]["output_conversion_options"]["format"], "webp_lossy")
        self.assertNotEqual(
            changed_plan["execution_options"]["output_conversion_options"],
            original_plan["execution_options"]["output_conversion_options"],
        )

    def test_missing_hash_and_legacy_snapshot_fail_closed(self):
        self.assertFalse(missing_raw_hash_snapshot()["execution_plan_json"]["workflow_hash"])
        legacy = irreproducible_snapshot()
        self.assertFalse(legacy["request_json"])
        self.assertFalse(legacy["execution_plan_json"])
        self.assertFalse(legacy["deployment_identity_json"])

    def test_future_generate_original_contract_remains_explicit(self):
        response = generate_original_placeholder_response()
        self.assertEqual(set(response), {
            "status", "generation_id", "run_id", "purpose", "mode", "attempt_status", "reused",
        })
        self.assertEqual(response["generation_id"], "gen_phase_e_wave2_logical")
        self.assertEqual(response["purpose"], "original")


@unittest.skip("Pending E3B2 production Generate Original route/service")
class PhaseEWave2ProductionPendingTests(unittest.TestCase):
    def test_generate_original_is_same_generation_new_attempt(self):
        self.fail("Generate Original production routing is not proven by the fake contract")


if __name__ == "__main__":
    unittest.main()
