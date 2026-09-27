"""Focused Phase E1 History asset projection regressions."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from history_v2_models import Asset, ExperimentCell, RunAttempt
from history_v2_routes import _build_outputs, _detail_cell


T0 = "2026-08-17T10:00:00.000+00:00"
T1 = "2026-08-17T10:01:00.000+00:00"
T2 = "2026-08-17T10:02:00.000+00:00"


def _asset(
    asset_id: str,
    asset_type: str,
    managed_path: str,
    *,
    created_at: str = T0,
    run_id: str | None = None,
    logical_output_key: str | None = None,
) -> Asset:
    return Asset(
        asset_id=asset_id,
        generation_id="gen_e1",
        type=asset_type,
        managed_path=managed_path,
        filename=f"{asset_id}.png",
        created_at=created_at,
        run_id=run_id,
        format="png",
        logical_output_key=logical_output_key,
    )


def _attempt(
    run_id: str,
    mode: str,
    status: str,
    *,
    created_at: str = T0,
    error: str | None = None,
) -> RunAttempt:
    return RunAttempt(
        run_id=run_id,
        generation_id="gen_e1",
        mode=mode,
        status=status,
        created_at=created_at,
        error=error,
    )


class HistoryProjectionTests(unittest.TestCase):
    def test_local_original_is_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "original.png"
            path.write_bytes(b"png")
            asset = _asset("local", "original", str(path), run_id="run_original")
            attempt = _attempt("run_original", "original", "completed")

            output = _build_outputs([asset], attempts=[attempt])[0]

        self.assertEqual(output["original_url"], "/comfymodal/history-v2/assets/local")
        self.assertFalse(output["original_failed"])

    def test_modal_original_is_structurally_available_without_fetch(self):
        asset = _asset(
            "remote",
            "original",
            "modal://ws_e1||output_assets/remote.png",
            run_id="run_original",
        )
        attempt = _attempt("run_original", "original", "completed")

        output = _build_outputs([asset], attempts=[attempt])[0]

        self.assertEqual(output["original_url"], "/comfymodal/history-v2/assets/remote")
        self.assertFalse(output["original_failed"])

    def test_failed_original_preserves_preview_and_sets_failure(self):
        preview = _asset("preview", "preview", "/missing/preview.png", run_id="run_preview")
        attempts = [
            _attempt("run_preview", "preview", "completed"),
            _attempt("run_original", "original", "failed", created_at=T1, error="OOM"),
        ]

        output = _build_outputs([preview], attempts=attempts)[0]

        self.assertEqual(output["preview_url"], "/comfymodal/history-v2/assets/preview")
        self.assertEqual(output["original_url"], "")
        self.assertTrue(output["original_failed"])

    def test_failed_original_preserves_preview_url_when_preview_is_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preview.png"
            path.write_bytes(b"png")
            preview = _asset("preview", "preview", str(path), run_id="run_preview")
            attempts = [
                _attempt("run_preview", "preview", "completed"),
                _attempt("run_original", "original", "failed", created_at=T1, error="OOM"),
            ]

            output = _build_outputs([preview], attempts=attempts)[0]

        self.assertEqual(output["preview_url"], "/comfymodal/history-v2/assets/preview")
        self.assertEqual(output["original_url"], "")
        self.assertTrue(output["original_failed"])

    def test_failed_retry_does_not_hide_earlier_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "original.png"
            path.write_bytes(b"png")
            original = _asset("original", "original", str(path), run_id="run_success")
            attempts = [
                _attempt("run_success", "original", "completed"),
                _attempt("run_retry", "original", "failed", created_at=T1, error="OOM"),
            ]

            output = _build_outputs([original], attempts=attempts)[0]

        self.assertEqual(output["original_url"], "/comfymodal/history-v2/assets/original")
        self.assertFalse(output["original_failed"])
        self.assertEqual(attempts[-1].error, "OOM")

    def test_newest_successful_original_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path = Path(tmp) / "old.png"
            new_path = Path(tmp) / "new.png"
            old_path.write_bytes(b"old")
            new_path.write_bytes(b"new")
            old = _asset("old", "original", str(old_path), created_at=T0, run_id="run_original")
            new = _asset("new", "original", str(new_path), created_at=T1, run_id="run_original")
            attempt = _attempt("run_original", "original", "completed")

            output = _build_outputs([old, new], attempts=[attempt])[0]

        self.assertEqual(output["original_url"], "/comfymodal/history-v2/assets/new")
        self.assertFalse(output["original_failed"])

    def test_queued_or_running_original_is_not_failed(self):
        preview = _asset("preview", "preview", "/missing/preview.png")
        for status in ("queued", "running"):
            with self.subTest(status=status):
                attempt = _attempt("run_original", "original", status)
                output = _build_outputs([preview], attempts=[attempt])[0]
                self.assertEqual(output["original_url"], "")
                self.assertFalse(output["original_failed"])

    def test_missing_local_original_is_failed(self):
        asset = _asset("missing", "original", "/missing/original.png", run_id="run_original")
        attempt = _attempt("run_original", "original", "completed")

        output = _build_outputs([asset], attempts=[attempt])[0]

        self.assertEqual(output["original_url"], "")
        self.assertTrue(output["original_failed"])

    def test_experiment_cell_uses_same_original_projection(self):
        cell = ExperimentCell(
            cell_id="cell_e1",
            experiment_id="exp_e1",
            position=0,
            status="completed",
            updated_at=T0,
            generation_id="gen_e1",
        )
        asset = _asset(
            "remote",
            "original",
            "modal://ws_e1||output_assets/remote.png",
            run_id="run_original",
        )
        attempts = {"cell_e1": [_attempt("run_original", "original", "completed")]}

        projected = _detail_cell(
            cell,
            {"gen_e1": [asset]},
            attempts,
            {},
        )

        self.assertEqual(projected["original_url"], "/comfymodal/history-v2/assets/remote")
        self.assertFalse(projected["original_failed"])

    def test_keyed_variants_form_one_logical_output_group(self):
        # Retired E1B-pending skip: logical-output identity HAS landed, so
        # this is now an executable projection assertion. Preview/Thumbnail/
        # Original variants sharing one stable logical_output_key project as
        # ONE output group; a second slot stays distinct.
        key0 = "node:9:slot:images:item:0"
        key1 = "node:9:slot:images:item:1"
        with tempfile.TemporaryDirectory() as tmp:
            thumb_path = Path(tmp) / "thumb.webp"
            thumb_path.write_bytes(b"thumb")
            original_path = Path(tmp) / "original.png"
            original_path.write_bytes(b"png")
            second_path = Path(tmp) / "second.png"
            second_path.write_bytes(b"second")

            preview = _asset(
                "preview", "preview", "/missing/preview.png",
                run_id="run_preview", logical_output_key=key0,
            )
            thumb = _asset(
                "thumb", "thumbnail", str(thumb_path),
                run_id="run_preview", logical_output_key=key0,
            )
            original = _asset(
                "original", "original", str(original_path),
                run_id="run_original", logical_output_key=key0,
            )
            second = _asset(
                "second", "original", str(second_path),
                created_at=T1, run_id="run_second", logical_output_key=key1,
            )
            attempts = [
                _attempt("run_preview", "preview", "completed"),
                _attempt("run_original", "original", "completed"),
                _attempt("run_second", "original", "completed", created_at=T1),
            ]

            outputs = _build_outputs([preview, thumb, original, second], attempts=attempts)

        self.assertEqual(len(outputs), 2)
        self.assertEqual(outputs[0]["asset_id"], "original")
        self.assertEqual(outputs[0]["thumb_url"], "/comfymodal/history-v2/assets/thumb")
        self.assertEqual(outputs[0]["preview_url"], "/comfymodal/history-v2/assets/preview")
        self.assertEqual(outputs[0]["original_url"], "/comfymodal/history-v2/assets/original")
        self.assertFalse(outputs[0]["original_failed"])
        self.assertEqual(outputs[1]["asset_id"], "second")


if __name__ == "__main__":
    unittest.main()
