"""Tests for the legacy migration seam (history_v2_migration.py)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from history_v2_migration import LegacyMigrationSeam
from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store


def _write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.db_path = self.root / "history_v2.db"
        self.store = HistoryV2Store(self.db_path)
        self.repo = HistoryV2Repository(self.store)
        self.seam = LegacyMigrationSeam(self.repo)

    # ── RunHistoryService (r_*) meta ────────────────────────────────────

    def test_migrate_runhistory_service_meta(self):
        output = self.root / "outputs" / "result.png"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"png-bytes")
        meta_path = _write_json(self.root / "run_history" / "r_abc123" / "meta.json", {
            "run_id": "r_abc123",
            "kind": "studio_run",
            "prompt_id": "p_1",
            "workflow_hash": "wh_1",
            "status": "completed",
            "started_at": "2026-01-01T00:00:00.000+00:00",
            "updated_at": "2026-01-01T00:01:00.000+00:00",
            "output_path": str(output),
            "extra": {
                "studio_preset_id": "preset_a",
                "studio_preset_label": "Preset A",
                "resolved_controls": {
                    "prompt": "a cat",
                    "negative_prompt": "blur",
                    "seed": 42,
                    "steps": 20,
                },
                "workflow_json": {"3": {"class_type": "KSampler", "inputs": {}}},
            },
            "annotations": {"favorite": True, "note": "my note"},
        })

        generation = self.seam.migrate_legacy_run_meta(meta_path)
        assert generation is not None
        detail = self.repo.get_generation(generation.generation_id)
        assert detail is not None
        self.assertIs(detail.generation.favorite, True)
        self.assertEqual(detail.generation.note, "my note")
        self.assertEqual(detail.generation.workflow_id, "wh_1")
        self.assertEqual(detail.generation.preset_id, "preset_a")
        self.assertEqual(detail.generation.preset_name, "Preset A")
        self.assertEqual(detail.generation.prompt_text, "a cat")
        self.assertEqual(detail.generation.negative_prompt_text, "blur")
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].mode, "original")
        self.assertEqual(detail.attempts[0].status, "completed")
        self.assertEqual(len(detail.assets), 1)
        # copy=False -> the asset points at the legacy path (absolute).
        self.assertEqual(Path(detail.assets[0].managed_path), output.resolve())
        self.assertEqual(detail.assets[0].filename, "result.png")
        # Snapshot captured from extra.workflow_json.
        assert detail.request_snapshot is not None
        self.assertEqual(detail.request_snapshot.workflow,
                         {"3": {"class_type": "KSampler", "inputs": {}}})
        self.assertEqual(detail.request_snapshot.generation_params["seed"], 42)
        self.assertEqual(detail.request_snapshot.generation_params["prompt"], "a cat")

    def test_migrate_legacy_run_history_meta(self):
        output = self.root / "legacy_out.png"
        output.write_bytes(b"legacy-bytes")
        meta_path = _write_json(self.root / "run_history" / "run_legacy1" / "meta.json", {
            "schema_version": 2,
            "run_id": "run_legacy1",
            "kind": "ordinary",
            "started_at": "2026-01-02T00:00:00.000+00:00",
            "workflow_name": "wf",
            "workflow_hash": "wh_legacy",
            "model_stack": {"checkpoint": {"name": "sd15", "type": "checkpoint"}},
            "prompt": "legacy prompt",
            "negative_prompt": "legacy neg",
            "seed": 123,
            "steps": 25,
            "status": "completed",
            "output_path": str(output),
            "timings": {"total_ms": 100},
        })

        generation = self.seam.migrate_legacy_run_meta(meta_path)
        assert generation is not None
        detail = self.repo.get_generation(generation.generation_id)
        assert detail is not None
        self.assertEqual(detail.generation.prompt_text, "legacy prompt")
        self.assertEqual(detail.generation.negative_prompt_text, "legacy neg")
        self.assertEqual(detail.generation.workflow_id, "wh_legacy")
        self.assertEqual(detail.generation.model_stack,
                         [{"checkpoint": {"name": "sd15", "type": "checkpoint"}}])
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].status, "completed")
        self.assertEqual(detail.attempts[0].timing, {"total_ms": 100})
        self.assertEqual(len(detail.assets), 1)
        self.assertEqual(detail.assets[0].filename, "legacy_out.png")

    def test_migration_idempotent(self):
        output = self.root / "out.png"
        output.write_bytes(b"x")
        meta_path = _write_json(self.root / "run_history" / "r_idem" / "meta.json", {
            "run_id": "r_idem",
            "kind": "studio_run",
            "status": "completed",
            "started_at": "2026-01-01T00:00:00.000+00:00",
            "output_path": str(output),
            "extra": {},
            "annotations": {},
        })

        first = self.seam.migrate_legacy_run_meta(meta_path)
        second = self.seam.migrate_legacy_run_meta(meta_path)
        self.assertIsNotNone(first)
        self.assertIsNone(second)

        page = self.repo.query_generations(limit=200)
        self.assertEqual(page["total"], 1)
        mapping = self.store.execute(
            "SELECT COUNT(*) FROM legacy_mapping WHERE legacy_run_id = 'r_idem'"
        )
        self.assertEqual(mapping[0][0], 1)

    def test_legacy_files_untouched(self):
        output = self.root / "untouched.png"
        output.write_bytes(b"x")
        meta_path = _write_json(self.root / "run_history" / "r_untouched" / "meta.json", {
            "run_id": "r_untouched",
            "kind": "studio_run",
            "status": "completed",
            "started_at": "2026-01-01T00:00:00.000+00:00",
            "output_path": str(output),
            "extra": {},
            "annotations": {},
        })
        before_mtime = meta_path.stat().st_mtime
        before_content = meta_path.read_text(encoding="utf-8")

        self.seam.migrate_legacy_run_meta(meta_path)

        self.assertEqual(meta_path.read_text(encoding="utf-8"), before_content)
        self.assertEqual(meta_path.stat().st_mtime, before_mtime)
        # No extra files created next to the legacy meta.
        entries = sorted(p.name for p in meta_path.parent.iterdir())
        self.assertEqual(entries, ["meta.json"])

    def test_migrate_run_history_dir(self):
        root = self.root / "run_history"
        for i in range(3):
            run_dir = root / f"run_{i}"
            run_dir.mkdir(parents=True)
            if i == 2:
                # Malformed meta -> counted as failed.
                (run_dir / "meta.json").write_text("{not json", encoding="utf-8")
                continue
            out = self.root / f"out_{i}.png"
            out.write_bytes(b"x")
            _write_json(run_dir / "meta.json", {
                "run_id": f"r_dir_{i}",
                "kind": "studio_run",
                "status": "completed",
                "started_at": f"2026-01-01T00:0{i}:00.000+00:00",
                "output_path": str(out),
                "extra": {},
                "annotations": {},
            })

        report = self.seam.migrate_run_history_dir(root)
        self.assertEqual(report.total, 3)
        self.assertEqual(report.imported, 2)
        self.assertEqual(report.skipped, 0)
        self.assertEqual(report.failed, 1)
        self.assertEqual(len(report.errors), 1)
        self.assertIn("run_2", report.errors[0])

        # Both valid runs are now in the store.
        page = self.repo.query_generations(limit=200)
        self.assertEqual(page["total"], 2)

    def test_dry_run_report_does_not_write(self):
        root = self.root / "run_history"
        out = self.root / "out.png"
        out.write_bytes(b"x")
        _write_json(root / "run_a" / "meta.json", {
            "run_id": "r_dry",
            "kind": "studio_run",
            "status": "completed",
            "started_at": "2026-01-01T00:00:00.000+00:00",
            "output_path": str(out),
            "extra": {},
            "annotations": {},
        })
        report = self.seam.dry_run_report(root)
        self.assertEqual(report.total, 1)
        self.assertEqual(report.imported, 1)
        # Nothing written to the store.
        page = self.repo.query_generations(limit=200)
        self.assertEqual(page["total"], 0)


if __name__ == "__main__":
    unittest.main()
