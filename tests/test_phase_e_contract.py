"""Phase-E deterministic contract fixtures and pending production gates."""
from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store
from history_v2_writer import (
    _gen_id,
    _run_id,
    get_writer,
    reset_writer_config,
    set_asset_resolver,
)

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


_LATER = "2026-01-01T10:05:00.000+00:00"
_E5D1_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class PhaseEE2CPreviewHandoffTests(unittest.TestCase):
    """E5 cross-layer contract retiring the E2C production-pending skip.

    Drives the REAL History V2 writer/result handoff — record_run → producer
    descriptor resolution → update_run attach → repository read-back — the
    same seam tests.test_e2c_history_handoff pins in depth. Asserted here as
    ONE concise cross-layer contract instead of duplicating that suite.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_root = Path(self._tmp.name)
        self.addCleanup(reset_writer_config)
        self.writer = get_writer(self.tmp_root)
        self.repo = HistoryV2Repository(
            HistoryV2Store(self.tmp_root / ".studio_history_v2" / "history_v2.db")
        )

    def _descriptor(self, asset_id, path, *, variant, parent_asset_id=""):
        record = {
            "asset_id": asset_id,
            "path": str(path),
            "mime_type": "image/png",
            "content_hash": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "width": 1,
            "height": 1,
            "byte_size": Path(path).stat().st_size,
            "variant": variant,
            "node_id": "6",
            "output_key": "images",
            "output_index": 0,
        }
        if parent_asset_id:
            record["parent_asset_id"] = parent_asset_id
        return record

    def test_preview_request_persists_preview_attempt_assets_and_gate(self):
        key = "node:6:slot:images:item:0"
        primary_path = self.tmp_root / "e5d1_primary.png"
        primary_path.write_bytes(_E5D1_PNG)
        thumb_path = self.tmp_root / "e5d1_thumb.png"
        thumb_path.write_bytes(_E5D1_PNG[::-1])
        primary = self._descriptor("ast_e5d1_primary", primary_path, variant="preview")
        thumb = self._descriptor(
            "ast_e5d1_thumb", thumb_path, variant="thumbnail",
            parent_asset_id="ast_e5d1_primary",
        )
        table = {r["asset_id"]: r for r in (primary, thumb)}
        set_asset_resolver(lambda asset_id: table.get(asset_id))

        meta = {
            "output_mode": "preview",
            "primary_asset_id": "ast_e5d1_primary",
            "derivative_asset_ids": ["ast_e5d1_thumb"],
        }
        self.writer.record_run(
            run_id="r_e5d1_preview", kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w", meta=dict(meta),
        )
        # The required Preview association exists BEFORE terminal completion.
        self.assertTrue(self.writer.generation_has_output_association("r_e5d1_preview"))
        self.writer.update_run(
            "r_e5d1_preview", status="completed", completed_at=_LATER,
            meta=dict(meta),
        )

        attempt = self.repo.get_attempt(_run_id("r_e5d1_preview"))
        self.assertEqual(attempt.mode, "preview")
        self.assertEqual(attempt.status, "completed")

        detail = self.repo.get_generation(_gen_id("r_e5d1_preview"))
        by_type = {a.type: a for a in detail.assets}
        self.assertEqual(sorted(by_type), ["preview", "thumbnail"])
        self.assertNotIn(
            "original", by_type,
            "Preview-only execution must not retain a managed Original",
        )
        self.assertEqual(by_type["preview"].logical_output_key, key)
        self.assertEqual(
            by_type["thumbnail"].logical_output_key,
            by_type["preview"].logical_output_key,
        )

    # NOTE: the former generate-original-replays-frozen-plan pending skip was
    # retired: the landed E3B2 suite tests.test_history_v2_generate_original
    # proves same-Generation/new-Attempt frozen-plan replay against the real
    # repository, service, and routes and is wired into this gate.
    #
    # NOTE: the former E2C production Preview persistence pending skip was
    # retired above: PhaseEE2CPreviewHandoffTests drives the landed writer/
    # result handoff end to end and tests.test_e2c_history_handoff pins the
    # seam in depth (gate membership decided in STUDIO_TEST_GATE.md).


if __name__ == "__main__":
    unittest.main()
