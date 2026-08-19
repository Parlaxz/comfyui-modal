"""Shape checks shared by the Phase-E fake and production contract tests."""
from __future__ import annotations

import json
import unittest

from tests.phase_e_fixtures import (
    GLOBAL_CONCURRENCY,
    HISTORY_ASSET_PREFIX,
    modern_experiment_definition,
    original_rerender_failed_generation,
    preview_failed_original_generation,
    preview_only_generation,
    preview_successful_original_generation,
    remote_original_generation,
    sparse_generation,
)


class PhaseEFakeParityTests(unittest.TestCase):
    def test_generation_detail_fixture_uses_production_wire_fields(self):
        required = {
            "id", "kind", "status", "workflow_id", "workflow_name", "workflow_version",
            "preset_id", "preset", "preset_name", "prompt", "negative_prompt", "created_at",
            "started_at", "completed_at", "duration_ms", "favorite", "note", "tags", "models",
            "output_count", "has_image", "preview_only", "original_available",
            "featured_output_index", "outputs", "attempts", "errors", "export_state", "params",
            "timing", "workflow_json",
        }
        records = [
            preview_only_generation(),
            preview_failed_original_generation(),
            preview_successful_original_generation(),
            original_rerender_failed_generation(),
            remote_original_generation(),
            sparse_generation("failed"),
            sparse_generation("interrupted"),
        ]
        for record in records:
            self.assertEqual(record["kind"], "generation")
            self.assertTrue(required.issubset(record))
            for output in record["outputs"]:
                for key in ("thumb_url", "preview_url", "original_url"):
                    if output[key]:
                        self.assertTrue(output[key].startswith(HISTORY_ASSET_PREFIX))
                        self.assertNotIn("modal://", output[key])
            for attempt in record["attempts"]:
                self.assertEqual(
                    set(attempt),
                    {"run_id", "mode", "status", "started_at", "finished_at", "duration_ms", "error", "timing"},
                )

    def test_experiment_acceptance_has_one_definition_and_frozen_preview_options(self):
        definition = modern_experiment_definition()
        body = {"experiment_id": "exp_phase_e_preview", "name": definition["name"], "definition": definition}
        self.assertEqual(set(body), {"experiment_id", "name", "definition"})
        self.assertNotIn("cells", body)
        self.assertNotIn("concurrency", body)
        self.assertEqual(definition["modal_options"], {"enabled": True, "codec": "webp", "quality": 70})
        self.assertEqual(GLOBAL_CONCURRENCY, 6)

    def test_fake_remote_fixture_never_serializes_producer_uri(self):
        payload = json.dumps(remote_original_generation())
        self.assertNotIn("modal://", payload)
        self.assertIn(HISTORY_ASSET_PREFIX, payload)


if __name__ == "__main__":
    unittest.main()
