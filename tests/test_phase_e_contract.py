"""Phase-E deterministic contract fixtures and pending production gates."""
from __future__ import annotations

import json
import unittest

from tests.phase_e_fixtures import (
    HISTORY_ASSET_PREFIX,
    PREVIEW_DEFAULTS,
    REMOTE_ORIGIN,
    generate_original_placeholder_response,
    irreproducible_snapshot,
    original_rerender_failed_generation,
    preview_failed_original_generation,
    preview_only_generation,
    preview_successful_original_generation,
    remote_original_generation,
    replay_complete_snapshot,
    sparse_generation,
)


class PhaseEContractFixtureTests(unittest.TestCase):
    def test_preview_defaults_are_global_and_distinct_from_thumbnail(self):
        self.assertEqual(PREVIEW_DEFAULTS, {"enabled": False, "codec": "webp", "quality": 70})
        record = preview_only_generation()
        output = record["outputs"][0]
        self.assertEqual(record["attempts"][0]["mode"], "preview")
        self.assertNotEqual(output["thumb_url"], output["preview_url"])
        self.assertTrue(output["preview_url"].startswith(HISTORY_ASSET_PREFIX))
        self.assertEqual(record["attempts"][0]["status"], "completed")
        self.assertEqual(len(record["attempts"]), 1)

    def test_failed_original_retains_preview_and_error(self):
        record = preview_failed_original_generation()
        output = record["outputs"][0]
        self.assertTrue(output["preview_url"])
        self.assertEqual(output["original_url"], "")
        self.assertTrue(output["original_failed"])
        self.assertEqual([a["mode"] for a in record["attempts"]], ["preview", "original"])
        self.assertEqual(record["attempts"][1]["status"], "failed")
        self.assertEqual(record["errors"][0]["message"], "Original replay failed")

    def test_successful_original_is_preferred_and_both_attempts_remain(self):
        record = preview_successful_original_generation()
        output = record["outputs"][0]
        self.assertTrue(output["preview_url"])
        self.assertTrue(output["original_url"])
        self.assertFalse(output["original_failed"])
        self.assertEqual([a["mode"] for a in record["attempts"]], ["preview", "original"])
        self.assertEqual(record["attempts"][-1]["status"], "completed")

    def test_failed_rerender_does_not_hide_earlier_original(self):
        record = original_rerender_failed_generation()
        output = record["outputs"][0]
        self.assertTrue(output["original_url"])
        self.assertFalse(output["original_failed"])
        self.assertEqual([a["status"] for a in record["attempts"]], ["completed", "completed", "failed"])
        self.assertEqual(record["attempts"][-1]["mode"], "original")
        self.assertEqual(record["errors"][0]["message"], "Rerender timed out")

    def test_remote_original_uses_managed_url_not_raw_uri(self):
        record = remote_original_generation()
        serialized = json.dumps(record)
        self.assertNotIn(REMOTE_ORIGIN, serialized)
        self.assertNotIn("modal://", serialized)
        self.assertTrue(record["outputs"][0]["original_url"].startswith(HISTORY_ASSET_PREFIX))

    def test_sparse_failed_and_interrupted_records_keep_empty_output_shape(self):
        failed = sparse_generation("failed")
        interrupted = sparse_generation("interrupted")
        for record, status in ((failed, "failed"), (interrupted, "interrupted")):
            self.assertEqual(record["status"], status)
            self.assertEqual(record["outputs"], [])
            self.assertEqual(record["params"], {})
            self.assertEqual(len(record["attempts"]), 1)

    def test_replay_snapshot_is_fail_closed(self):
        complete = replay_complete_snapshot()
        incomplete = irreproducible_snapshot()
        self.assertTrue(complete["execution_plan_json"])
        self.assertTrue(complete["deployment_identity_json"])
        self.assertFalse(incomplete["execution_plan_json"])
        self.assertFalse(incomplete["deployment_identity_json"])

    def test_generate_original_placeholder_shape_is_explicit(self):
        response = generate_original_placeholder_response()
        self.assertEqual(
            set(response),
            {"status", "generation_id", "run_id", "purpose", "mode", "attempt_status", "reused"},
        )
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["purpose"], "original")
        self.assertEqual(response["mode"], "original")
        self.assertFalse(response["reused"])


@unittest.skip("Pending E1/E2/E3/E4 production seams; fake fixtures are not proof")
class PhaseEProductionPendingTests(unittest.TestCase):
    def test_production_preview_request_snapshot(self):
        self.fail("Preview request propagation is not implemented yet")

    def test_generate_original_replays_frozen_plan(self):
        self.fail("Generate Original replay service is not implemented yet")


if __name__ == "__main__":
    unittest.main()
