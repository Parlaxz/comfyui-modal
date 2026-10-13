"""Focused E1B logical-output identity and projection regressions."""
from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from history_v2_models import (
    Asset,
    ExperimentCell,
    Generation,
    GenerationDetail,
    RunAttempt,
)
from history_v2_repository import HistoryV2Repository
from history_v2_routes import (
    _build_outputs,
    _cell_generation_payload,
    _detail_cell,
    _generation_feed_item,
    _launch_local_path,
    _model_names,
    _probe_image_dimensions,
    _probe_image_format,
    _recover_embedded_params,
    _resolve_local_asset_file,
)
from history_v2_store import HistoryV2Store
from history_v2_writer import (
    HistoryV2ProductionWriter,
    reset_writer_config,
    set_asset_resolver,
)


T0 = "2026-08-17T10:00:00.000+00:00"
T1 = "2026-08-17T10:01:00.000+00:00"
T2 = "2026-08-17T10:02:00.000+00:00"
KEY_A = "node:9:slot:images:item:0"
KEY_B = "node:9:slot:images:item:1"
KEY_OTHER_NODE = "node:10:slot:images:item:0"


def _asset(
    asset_id: str,
    asset_type: str,
    path: str,
    *,
    key: str | None = KEY_A,
    run_id: str | None = None,
    created_at: str = T0,
) -> Asset:
    return Asset(
        asset_id=asset_id,
        generation_id="gen_e1b",
        type=asset_type,
        managed_path=path,
        filename=f"{asset_id}.png",
        created_at=created_at,
        run_id=run_id,
        format="png",
        logical_output_key=key,
    )


def _attempt(
    run_id: str,
    mode: str = "original",
    status: str = "completed",
    *,
    created_at: str = T0,
    error: str | None = None,
) -> RunAttempt:
    return RunAttempt(
        run_id=run_id,
        generation_id="gen_e1b",
        mode=mode,
        status=status,
        created_at=created_at,
        error=error,
    )


def _feed_generation(assets, attempts, featured_asset_id=None):
    return _generation_feed_item(
        {
            "generation_id": "gen_e1b",
            "status": "completed",
            "created_at": T0,
            "featured_asset_id": featured_asset_id,
        },
        assets,
        attempts,
    )


class LogicalOutputProjectionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _path(self, name: str) -> str:
        path = self.root / name
        path.write_bytes(name.encode())
        return str(path)

    def test_thumbnail_and_original_same_key_are_one_output(self):
        original = _asset("original", "original", self._path("original.png"), run_id="run_o")
        thumb = _asset("thumb", "thumbnail", self._path("thumb.png"), run_id="run_o")
        attempts = [_attempt("run_o")]

        item = _feed_generation([original, thumb], attempts)

        self.assertEqual(item["output_count"], 1)
        self.assertEqual(len(item["outputs"]), 1)
        self.assertEqual(item["outputs"][0]["original_url"].split("/")[-1], "original")
        self.assertTrue(item["outputs"][0]["thumb_url"].endswith("/thumb"))

    def test_preview_and_original_across_attempts_are_one_output(self):
        preview = _asset("preview", "preview", self._path("preview.png"), run_id="run_p")
        original = _asset("original", "original", self._path("original.png"), run_id="run_o")
        attempts = [
            _attempt("run_p", "preview"),
            _attempt("run_o", "original", created_at=T1),
        ]

        outputs = _build_outputs([preview, original], attempts=attempts)

        self.assertEqual(len(outputs), 1)
        self.assertTrue(outputs[0]["preview_url"].endswith("/preview"))
        self.assertTrue(outputs[0]["original_url"].endswith("/original"))

    def test_failed_original_retry_and_successful_retry_are_one_output(self):
        preview = _asset("preview", "preview", self._path("preview.png"), run_id="run_p")
        original = _asset("original", "original", self._path("original.png"), run_id="run_o2")
        attempts = [
            _attempt("run_p", "preview"),
            _attempt("run_o1", "original", "failed", created_at=T1, error="OOM"),
            _attempt("run_o2", "original", "completed", created_at=T2),
        ]

        outputs = _build_outputs([preview, original], attempts=attempts)

        self.assertEqual(len(outputs), 1)
        self.assertTrue(outputs[0]["original_url"].endswith("/original"))
        self.assertFalse(outputs[0]["original_failed"])

    def test_two_successful_original_retries_newest_wins(self):
        old = _asset("old", "original", self._path("old.png"), run_id="run_o1")
        new = _asset("new", "original", self._path("new.png"), run_id="run_o2", created_at=T1)
        attempts = [
            _attempt("run_o1", created_at=T0),
            _attempt("run_o2", created_at=T1),
        ]

        outputs = _build_outputs([old, new], attempts=attempts)

        self.assertEqual(len(outputs), 1)
        self.assertTrue(outputs[0]["original_url"].endswith("/new"))
        self.assertFalse(outputs[0]["original_failed"])

    def test_failed_latest_retry_preserves_earlier_original(self):
        old = _asset("old", "original", self._path("old.png"), run_id="run_o1")
        attempts = [
            _attempt("run_o1"),
            _attempt("run_o2", "original", "failed", created_at=T1, error="retry failed"),
        ]

        outputs = _build_outputs([old], attempts=attempts)

        self.assertEqual(len(outputs), 1)
        self.assertTrue(outputs[0]["original_url"].endswith("/old"))
        self.assertFalse(outputs[0]["original_failed"])

    def test_item_indexes_and_output_nodes_are_distinct(self):
        assets = [
            _asset("a", "original", self._path("a.png"), key=KEY_A, run_id="run_a"),
            _asset("b", "original", self._path("b.png"), key=KEY_B, run_id="run_b"),
            _asset("other", "original", self._path("other.png"), key=KEY_OTHER_NODE, run_id="run_c"),
        ]
        attempts = [_attempt("run_a"), _attempt("run_b"), _attempt("run_c")]

        item = _feed_generation(assets, attempts)

        self.assertEqual(item["output_count"], 3)
        self.assertEqual(len(item["outputs"]), 3)

    def test_featured_thumbnail_maps_by_logical_membership(self):
        a = _asset("a", "original", self._path("a.png"), key=KEY_A, run_id="run_a")
        a_thumb = _asset("a_thumb", "thumbnail", self._path("a_thumb.png"), key=KEY_A, run_id="run_a")
        b = _asset("b", "original", self._path("b.png"), key=KEY_B, run_id="run_b")
        attempts = [_attempt("run_a"), _attempt("run_b")]

        item = _feed_generation([a, a_thumb, b], attempts, featured_asset_id="a_thumb")

        self.assertEqual(item["featured_output_index"], 0)

    def test_featured_preview_maps_by_logical_membership(self):
        a = _asset("a", "original", self._path("a.png"), key=KEY_A, run_id="run_a")
        b_preview = _asset("b_preview", "preview", self._path("b_preview.png"), key=KEY_B, run_id="run_b")
        attempts = [_attempt("run_a"), _attempt("run_b", "preview")]

        item = _feed_generation([a, b_preview], attempts, featured_asset_id="b_preview")

        self.assertEqual(item["featured_output_index"], 1)

    def test_featured_older_original_stays_in_same_group_after_newer_success(self):
        old = _asset("old", "original", self._path("old.png"), key=KEY_A, run_id="run_old")
        new = _asset("new", "original", self._path("new.png"), key=KEY_A, run_id="run_new", created_at=T1)
        other = _asset("other", "original", self._path("other.png"), key=KEY_B, run_id="run_other")
        attempts = [_attempt("run_old"), _attempt("run_new", created_at=T1), _attempt("run_other")]

        item = _feed_generation([old, new, other], attempts, featured_asset_id="old")

        self.assertEqual(item["featured_output_index"], 0)
        self.assertTrue(item["outputs"][0]["original_url"].endswith("/new"))

    def test_remote_keyed_original_keeps_e1a_uri_semantics(self):
        remote = _asset(
            "remote",
            "original",
            "modal://ws_e1b||output_assets/remote.png",
            key=KEY_A,
            run_id="run_remote",
        )

        output = _build_outputs([remote], attempts=[_attempt("run_remote")])[0]

        self.assertTrue(output["original_url"].endswith("/remote"))
        self.assertFalse(output["original_failed"])

    def test_experiment_cell_uses_same_keyed_generation_grouping(self):
        original = _asset("original", "original", self._path("original.png"), key=KEY_A, run_id="run_o")
        thumb = _asset("thumb", "thumbnail", self._path("thumb.png"), key=KEY_A, run_id="run_p")
        attempts = [_attempt("run_p", "preview"), _attempt("run_o")]
        generation = Generation(
            generation_id="gen_e1b",
            created_at=T0,
            status="completed",
            featured_asset_id="thumb",
        )
        payload = _cell_generation_payload(
            GenerationDetail(generation=generation, attempts=attempts, assets=[original, thumb])
        )

        self.assertEqual(len(payload["outputs"]), 1)
        self.assertEqual(payload["featured_output_index"], 0)

        cell = ExperimentCell(
            cell_id="cell_e1b",
            experiment_id="exp_e1b",
            position=0,
            status="completed",
            updated_at=T0,
            generation_id="gen_e1b",
        )
        projected = _detail_cell(
            cell,
            {"gen_e1b": [original, thumb]},
            {"cell_e1b": attempts},
            {},
        )
        self.assertTrue(projected["original_url"].endswith("/original"))

    def test_legacy_unkeyed_assets_group_only_by_run(self):
        first = _asset("first", "original", self._path("first.png"), key=None, run_id="run_legacy")
        second = _asset("second", "thumbnail", self._path("second.png"), key=None, run_id="run_legacy")
        orphan = _asset("orphan", "original", self._path("orphan.png"), key=None)

        outputs = _build_outputs([first, second, orphan])

        self.assertEqual(len(outputs), 2)

    def test_mixed_keyed_and_legacy_data_is_deterministic(self):
        keyed = _asset("keyed", "original", self._path("keyed.png"), key=KEY_A, run_id="run_k")
        keyed_thumb = _asset("keyed_thumb", "thumbnail", self._path("keyed_thumb.png"), key=KEY_A, run_id="run_k")
        legacy = _asset("legacy", "original", self._path("legacy.png"), key=None, run_id="run_l")
        legacy_thumb = _asset("legacy_thumb", "thumbnail", self._path("legacy_thumb.png"), key=None, run_id="run_l")
        orphan = _asset("orphan", "original", self._path("orphan.png"), key=None)

        first = _build_outputs([orphan, legacy_thumb, keyed, legacy, keyed_thumb])
        second = _build_outputs([keyed_thumb, legacy, orphan, keyed, legacy_thumb])

        self.assertEqual(
            [output["asset_id"] for output in first],
            [output["asset_id"] for output in second],
        )
        self.assertEqual(len(first), 3)


class LogicalOutputPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.db_path = self.root / ".studio_history_v2" / "history_v2.db"
        self.repo = HistoryV2Repository(HistoryV2Store(self.db_path))

    def test_repository_round_trips_logical_output_key(self):
        generation = self.repo.create_generation(generation_id="gen_e1b")
        asset = self.repo.attach_asset(
            generation.generation_id,
            asset_type="original",
            data=b"original",
            filename="original.png",
            fmt="png",
            logical_output_key=KEY_A,
        )

        stored = self.repo.get_asset(asset.asset_id)

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.logical_output_key, KEY_A)

    def test_migration_adds_key_column_and_is_idempotent(self):
        legacy_path = self.root / "legacy.db"
        conn = sqlite3.connect(legacy_path)
        conn.execute(
            """CREATE TABLE assets (
                asset_id TEXT PRIMARY KEY,
                generation_id TEXT NOT NULL,
                run_id TEXT,
                type TEXT NOT NULL,
                managed_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                width INTEGER,
                height INTEGER,
                format TEXT,
                sha256 TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            "INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("legacy", "gen_legacy", None, "original", "/missing", "old.png",
             None, None, "png", None, "{}", T0),
        )
        conn.commit()
        conn.close()

        store = HistoryV2Store(legacy_path)
        store.initialize()
        store.initialize()
        columns = {
            row["name"] for row in store.execute("PRAGMA table_info(assets)")
        }
        row = store.execute(
            "SELECT logical_output_key FROM assets WHERE asset_id = ?", ("legacy",)
        )[0]

        self.assertIn("logical_output_key", columns)
        self.assertIsNone(row["logical_output_key"])
        self.assertEqual(store.execute("PRAGMA user_version")[0][0], 2)


class LogicalOutputWriterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.writer = HistoryV2ProductionWriter(self.root)
        self.addCleanup(reset_writer_config)

    def _file(self, name: str) -> str:
        path = self.root / name
        path.write_bytes(name.encode())
        return str(path)

    def test_writer_consumes_explicit_and_derived_output_keys(self):
        explicit_path = self._file("explicit.png")
        self.writer.record_run(
            run_id="run_explicit",
            kind="studio_run",
            status="submitted",
            meta={
                "output_paths": [explicit_path],
                "logical_output_key": KEY_A,
            },
        )
        self.writer.update_run("run_explicit", status="completed", meta={})

        derived_path = self._file("derived.png")
        self.writer.record_run(
            run_id="run_derived",
            kind="studio_run",
            status="submitted",
            meta={
                "output_paths": [derived_path],
                "node_id": "9",
                "output_key": "images",
                "output_index": 1,
            },
        )
        self.writer.update_run("run_derived", status="completed", meta={})

        repo = HistoryV2Repository(HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db"))
        explicit = repo.get_generation_assets("gen_" + hashlib.sha256(b"v2gen:run_explicit").hexdigest()[:12])
        derived = repo.get_generation_assets("gen_" + hashlib.sha256(b"v2gen:run_derived").hexdigest()[:12])

        self.assertEqual({a.logical_output_key for a in explicit if a.type == "original"}, {KEY_A})
        self.assertEqual(
            {a.logical_output_key for a in derived if a.type == "original"},
            {"node:9:slot:images:item:1"},
        )

    def test_producer_adoption_consumes_explicit_key(self):
        producer_id = "producer_e1b"
        path = self._file("producer.png")
        record = {
            "asset_id": producer_id,
            "path": path,
            "mime_type": "image/png",
            "content_hash": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "node_id": "9",
            "output_key": "images",
            "output_index": 0,
            "logical_output_key": KEY_A,
        }
        set_asset_resolver(lambda asset_id: record if asset_id == producer_id else None)

        self.writer.record_run(
            run_id="run_producer",
            kind="studio_run",
            status="submitted",
            meta={"primary_asset_id": producer_id},
        )
        self.writer.update_run(
            "run_producer",
            status="completed",
            primary_asset_id=producer_id,
            meta={},
        )

        repo = HistoryV2Repository(HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db"))
        generation_id = "gen_" + hashlib.sha256(b"v2gen:run_producer").hexdigest()[:12]
        assets = repo.get_generation_assets(generation_id)

        self.assertEqual([a.logical_output_key for a in assets], [KEY_A])


class ViewerContentProjectionTests(unittest.TestCase):
    """Resolution + file size reach the viewer even without a request snapshot.

    A generation recorded with no snapshot (no params/workflow/model data)
    must still show resolution: the output projects asset-measured dims and
    the local managed-file size, and omits both (None) for remote-only
    assets instead of fabricating values.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _path(self, name: str, size: int = 10) -> str:
        path = self.root / name
        path.write_bytes(b"x" * size)
        return str(path)

    def test_output_projects_dimensions_and_local_file_size(self):
        asset = Asset(
            asset_id="preview",
            generation_id="gen_viewer",
            type="preview",
            managed_path=self._path("preview.png", size=1234),
            filename="preview.png",
            created_at=T0,
            run_id="run_p",
            width=1024,
            height=768,
            format="png",
            logical_output_key=KEY_A,
        )
        outputs = _build_outputs([asset], attempts=[_attempt("run_p", "preview")])

        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["width"], 1024)
        self.assertEqual(outputs[0]["height"], 768)
        self.assertEqual(outputs[0]["byte_size"], 1234)

    def test_remote_or_missing_file_projects_no_size_but_keeps_dimensions(self):
        remote = Asset(
            asset_id="remote",
            generation_id="gen_viewer",
            type="preview",
            managed_path="modal://workspace/remote.png",
            filename="remote.png",
            created_at=T0,
            run_id="run_p",
            width=512,
            height=512,
            format="png",
            logical_output_key=KEY_A,
        )
        outputs = _build_outputs([remote], attempts=[_attempt("run_p", "preview")])

        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["width"], 512)
        self.assertEqual(outputs[0]["height"], 512)
        self.assertIsNone(outputs[0]["byte_size"])

    def test_missing_recorded_dimensions_are_probed_from_the_image_file(self):
        from PIL import Image

        image_path = str(self.root / "probed.png")
        Image.new("RGB", (640, 480)).save(image_path)
        asset = Asset(
            asset_id="probed",
            generation_id="gen_viewer",
            type="preview",
            managed_path=image_path,
            filename="probed.png",
            created_at=T0,
            run_id="run_p",
            width=None,
            height=None,
            format="png",
            logical_output_key=KEY_A,
        )
        # Detail-only: feed pages never pay for header probes.
        outputs = _build_outputs(
            [asset], attempts=[_attempt("run_p", "preview")], include_embedded=True
        )

        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["width"], 640)
        self.assertEqual(outputs[0]["height"], 480)

    def test_probe_ignores_remote_and_unreadable_files(self):
        self.assertEqual(_probe_image_dimensions("modal://workspace/x.png"), (None, None))
        self.assertEqual(_probe_image_dimensions(str(self.root / "absent.png")), (None, None))
        bad = self.root / "bad.png"
        bad.write_bytes(b"not an image")
        self.assertEqual(_probe_image_dimensions(str(bad)), (None, None))

    def test_probe_image_format_reads_bytes_not_names(self):
        from PIL import Image

        png_path = str(self.root / "real.png")
        Image.new("RGB", (8, 8)).save(png_path)
        self.assertEqual(_probe_image_format(png_path), "png")
        webp_path = str(self.root / "real.webp")
        Image.new("RGB", (8, 8)).save(webp_path, format="WEBP")
        self.assertEqual(_probe_image_format(webp_path), "webp")
        # WebP bytes under a .png name (golden materialization before
        # extension sniffing) still probe as webp.
        misnamed = str(self.root / "misnamed.png")
        Image.new("RGB", (8, 8)).save(misnamed, format="WEBP")
        self.assertEqual(_probe_image_format(misnamed), "webp")
        self.assertIsNone(_probe_image_format("modal://workspace/x.png"))
        self.assertIsNone(_probe_image_format(str(self.root / "absent.png")))
        bad = self.root / "bad.bin"
        bad.write_bytes(b"not an image at all!!!!!")
        self.assertIsNone(_probe_image_format(str(bad)))

    def test_detail_format_prefers_byte_truth_over_stored(self):
        from PIL import Image

        # Mirrors the field case: webp bytes, .png name, stored format png.
        misnamed = str(self.root / "truth.webp")
        Image.new("RGB", (16, 16)).save(misnamed, format="WEBP")
        asset = Asset(
            asset_id="truthy",
            generation_id="gen_viewer",
            type="original",
            managed_path=misnamed,
            filename="truth.png",
            created_at=T0,
            run_id="run_o",
            width=None,
            height=None,
            format="png",
            logical_output_key=KEY_A,
        )
        attempts = [_attempt("run_o", "original")]
        rich = _build_outputs([asset], attempts=attempts, include_embedded=True)[0]
        self.assertEqual(rich["format"], "webp")
        self.assertEqual(rich["original_format"], "webp")
        self.assertEqual(rich["width"], 16)
        self.assertEqual(rich["height"], 16)
        # Feed path never opens files: stored value stands.
        plain = _build_outputs([asset], attempts=attempts)[0]
        self.assertEqual(plain["format"], "png")

    def test_role_keyed_model_stack_projects_each_model_name(self):
        self.assertEqual(
            _model_names({"clip": ["qwen_3_4b.safetensors"], "unet": ["z_image_turbo_bf16.safetensors"], "vae": ["ae.safetensors"]}),
            ["qwen_3_4b.safetensors", "z_image_turbo_bf16.safetensors", "ae.safetensors"],
        )
        self.assertEqual(_model_names({"name": "named.safetensors"}), ["named.safetensors"])
        self.assertEqual(_model_names({}), [])

        item = _generation_feed_item(
            {
                "generation_id": "gen_models",
                "status": "completed",
                "created_at": T0,
                "model_stack": [{"clip": ["qwen_3_4b.safetensors"], "unet": ["z_image_turbo_bf16.safetensors"]}],
            },
            [],
            [],
        )
        self.assertEqual(
            [m["name"] for m in item["models"]],
            ["qwen_3_4b.safetensors", "z_image_turbo_bf16.safetensors"],
        )

    def _prompt_png(self, name, prompt):
        import json as _json

        from PIL import Image
        from PIL.PngImagePlugin import PngInfo

        path = str(self.root / name)
        info = PngInfo()
        info.add_text("prompt", _json.dumps(prompt))
        Image.new("RGB", (320, 240)).save(path, pnginfo=info)
        return path

    def test_embedded_prompt_recovers_sampler_params_and_models(self):
        path = self._prompt_png("embedded.png", {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "u.safetensors"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.safetensors"}},
            "3": {"class_type": "KSampler", "inputs": {
                "seed": 23, "steps": 25, "cfg": 1.0, "sampler_name": "euler",
                "scheduler": "simple", "denoise": 0.8}},
        })
        params, models = _recover_embedded_params(path)

        self.assertEqual(params, {
            "seed": 23, "steps": 25, "cfg": 1.0,
            "sampler": "euler", "scheduler": "simple", "denoise": 0.8,
        })
        self.assertEqual(models, ["u.safetensors", "c.safetensors"])

    def test_embedded_prompt_supports_advanced_sampler_seed_alias(self):
        path = self._prompt_png("adv.png", {
            "9": {"class_type": "KSamplerAdvanced", "inputs": {
                "noise_seed": 7, "steps": 10, "cfg": 3.5,
                "sampler_name": "dpmpp_2m", "scheduler": "karras"}},
        })
        params, models = _recover_embedded_params(path)

        self.assertEqual(params["seed"], 7)
        self.assertEqual(params["sampler"], "dpmpp_2m")
        self.assertEqual(models, [])

    def test_embedded_recovery_ignores_remote_missing_and_foreign_chunks(self):
        params, models = _recover_embedded_params("modal://workspace/x.png")
        self.assertEqual((params, models), ({}, []))
        params, models = _recover_embedded_params(str(self.root / "absent.png"))
        self.assertEqual((params, models), ({}, []))

        from PIL import Image

        foreign = str(self.root / "foreign.png")
        Image.new("RGB", (8, 8)).save(foreign)
        params, models = _recover_embedded_params(foreign)
        self.assertEqual((params, models), ({}, []))

    def test_build_outputs_embeds_recovery_only_on_detail(self):
        path = self._prompt_png("flag.png", {
            "3": {"class_type": "KSampler", "inputs": {"seed": 5, "steps": 4}},
        })
        asset = Asset(
            asset_id="flag", generation_id="gen_viewer", type="preview",
            managed_path=path, filename="flag.png", created_at=T0,
            run_id="run_p", width=None, height=None, format="png",
            logical_output_key=KEY_A,
        )
        attempts = [_attempt("run_p", "preview")]

        plain = _build_outputs([asset], attempts=attempts)[0]
        self.assertEqual(plain["embedded_params"], {})
        self.assertEqual(plain["embedded_models"], [])
        self.assertIsNone(plain["width"])
        self.assertEqual(plain["filename"], "flag.png")
        self.assertEqual(plain["format"], "png")

        rich = _build_outputs([asset], attempts=attempts, include_embedded=True)[0]
        self.assertEqual(rich["embedded_params"], {"seed": 5, "steps": 4})
        self.assertEqual(rich["width"], 320)
        self.assertEqual(rich["height"], 240)

    def test_feed_item_backfills_models_from_embedded_only_when_stack_empty(self):
        path = self._prompt_png("models.png", {
            "1": {"class_type": "VAELoader", "inputs": {"vae_name": "v.safetensors"}},
        })
        asset = Asset(
            asset_id="m", generation_id="gen_models", type="preview",
            managed_path=path, filename="m.png", created_at=T0,
            run_id="run_p", width=8, height=8, format="png",
            logical_output_key=KEY_A,
        )
        attempts = [_attempt("run_p", "preview")]

        backfilled = _generation_feed_item(
            {"generation_id": "gen_models", "status": "completed",
             "created_at": T0, "model_stack": []},
            [asset], attempts, include_embedded=True,
        )
        self.assertEqual(backfilled["models"], [{"name": "v.safetensors"}])

        kept = _generation_feed_item(
            {"generation_id": "gen_models", "status": "completed",
             "created_at": T0, "model_stack": [{"name": "stored.safetensors"}]},
            [asset], attempts, include_embedded=True,
        )
        self.assertEqual(kept["models"], [{"name": "stored.safetensors"}])

    def test_resolve_local_asset_file(self):
        from types import SimpleNamespace

        missing_repo = SimpleNamespace(get_asset=lambda asset_id: None)
        path, error = _resolve_local_asset_file(missing_repo, "ast_nope")
        self.assertIsNone(path)
        self.assertTrue(error and error[0] == "asset_not_found" and error[2] == 404)

        remote = SimpleNamespace(get_asset=lambda asset_id: SimpleNamespace(
            managed_path="modal://ws|gpu|/remote.png"))
        path, error = _resolve_local_asset_file(remote, "ast_remote")
        self.assertIsNone(path)
        self.assertTrue(error and error[0] == "remote_asset")

        gone = SimpleNamespace(get_asset=lambda asset_id: SimpleNamespace(
            managed_path=str(self.root / "gone.png")))
        path, error = _resolve_local_asset_file(gone, "ast_gone")
        self.assertIsNone(path)
        self.assertTrue(error and error[0] == "file_missing")

        real = self._path("local.png")
        found_repo = SimpleNamespace(get_asset=lambda asset_id: SimpleNamespace(
            managed_path=real))
        path, error = _resolve_local_asset_file(found_repo, "ast_local")
        self.assertIsNone(error)
        self.assertEqual(str(path), real)

    def test_launch_local_path_reveal_selects_file(self):
        from unittest import mock

        import history_v2_routes as routes

        target = Path(self.root / "local.png")
        target.write_bytes(b"x")
        with mock.patch.object(routes.subprocess, "Popen") as popen, \
            mock.patch.object(routes.os, "name", "nt"):
            _launch_local_path(target, reveal=True)
        popen.assert_called_once_with(["explorer", "/select,", str(target)])

    def test_launch_local_path_open_uses_default_app(self):
        from unittest import mock

        import history_v2_routes as routes

        target = Path(self.root / "local.png")
        target.write_bytes(b"x")
        with mock.patch.object(routes.os, "name", "nt"), \
            mock.patch("os.startfile", create=True) as startfile:
            _launch_local_path(target, reveal=False)
        startfile.assert_called_once_with(str(target))


class DeleteGenerationTests(unittest.TestCase):
    """Generation deletion beyond the HTTP contract: referenced sources are
    never touched, snapshots/mappings go with the record, experiment cells
    detach (the experiment survives), and missing ids report False.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.store = HistoryV2Store(self.root / ".studio_history_v2" / "history_v2.db")
        self.store.initialize()
        self.repo = HistoryV2Repository(self.store)

    def _gen(self, gen_id, experiment_id=None):
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO generations (generation_id, created_at, experiment_id,"
                " favorite, note, status, updated_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (gen_id, T0, experiment_id, 0, "", "completed", T0),
            )

    def _attempt(self, run_id, gen_id, mode="preview"):
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO run_attempts (run_id, generation_id, mode, status,"
                " created_at) VALUES (?,?,?,?,?)",
                (run_id, gen_id, mode, "completed", T0),
            )

    def _asset(self, asset_id, gen_id, managed_path, asset_type="preview"):
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO assets (asset_id, generation_id, type, managed_path,"
                " filename, created_at) VALUES (?,?,?,?,?,?)",
                (asset_id, gen_id, asset_type, managed_path, Path(managed_path).name, T0),
            )

    def _snapshot(self, gen_id):
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO request_snapshots (snapshot_id, generation_id,"
                " workflow_json, created_at) VALUES (?,?,?,?)",
                ("snap_" + gen_id, gen_id, "{}", T0),
            )

    def _mapping(self, run_id, gen_id):
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO legacy_mapping (legacy_run_id, generation_id, source,"
                " migrated_at) VALUES (?,?,?,?)",
                (run_id, gen_id, "test", T0),
            )

    def _count(self, table, gen_id):
        rows = self.store.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE generation_id = ?", (gen_id,)
        )
        return rows[0]["n"]

    def test_delete_clears_snapshots_mapping_and_spares_referenced_files(self):
        gen_id = "gen_del_full"
        self._gen(gen_id)
        self._attempt("run_del", gen_id)
        owned_dir = self.store.assets_root() / gen_id
        owned_dir.mkdir(parents=True)
        owned = owned_dir / "ast_owned.png"
        owned.write_bytes(b"owned")
        self._asset("ast_owned", gen_id, str(owned))
        referenced = self.root / "keep_me.png"
        referenced.write_bytes(b"source-of-truth")
        self._asset("ast_ref", gen_id, str(referenced), asset_type="original")
        self._snapshot(gen_id)
        self._mapping("run_del", gen_id)

        self.assertTrue(self.repo.delete_generation(gen_id))

        self.assertEqual(self._count("generations", gen_id), 0)
        self.assertEqual(self._count("run_attempts", gen_id), 0)
        self.assertEqual(self._count("assets", gen_id), 0)
        self.assertEqual(self._count("request_snapshots", gen_id), 0)
        self.assertEqual(self._count("legacy_mapping", gen_id), 0)
        self.assertFalse(owned.exists(), "store-owned file removed")
        self.assertTrue(referenced.exists(), "referenced source file untouched")
        self.assertFalse(owned_dir.exists(), "emptied generation dir removed")
        self.assertIsNone(self.repo.get_generation(gen_id))

    def test_missing_generation_returns_false(self):
        self.assertFalse(self.repo.delete_generation("gen_absent"))

    def test_experiment_member_detaches_cell_and_keeps_experiment(self):
        gen_id = "gen_del_cell"
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO experiments (experiment_id, status, created_at,"
                " updated_at) VALUES (?,?,?,?)",
                ("exp_1", "running", T0, T0),
            )
        self._gen(gen_id, experiment_id="exp_1")
        with self.store.transaction() as conn:
            conn.execute(
                "INSERT INTO experiment_cells (cell_id, experiment_id, position,"
                " generation_id, status, updated_at) VALUES (?,?,?,?,?,?)",
                ("cell_1", "exp_1", 0, gen_id, "completed", T0),
            )

        self.assertTrue(self.repo.delete_generation(gen_id))

        self.assertEqual(self._count("generations", gen_id), 0)
        cell = self.store.execute(
            "SELECT generation_id, status FROM experiment_cells WHERE cell_id = ?",
            ("cell_1",),
        )[0]
        self.assertIsNone(cell["generation_id"], "cell detached, not deleted")
        self.assertIsNotNone(
            self.repo.get_experiment("exp_1"), "experiment survives its cell's deletion")

    def test_missing_owned_file_is_tolerated(self):
        gen_id = "gen_del_nofile"
        self._gen(gen_id)
        ghost = self.store.assets_root() / gen_id / "ast_ghost.png"
        self._asset("ast_ghost", gen_id, str(ghost))

        self.assertTrue(self.repo.delete_generation(gen_id))
        self.assertEqual(self._count("generations", gen_id), 0)


if __name__ == "__main__":
    unittest.main()
