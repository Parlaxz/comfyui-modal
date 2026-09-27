"""F9 HTTP integration tests — History V2 configured-folder Export route.

Exercises the PRODUCTION backend integration end-to-end against a real
aiohttp test server + temp History V2 store:

- BODYLESS ``POST /comfymodal/history-v2/assets/{asset_id}/export``
- server-derived generation association, REAL logical-output index and
  naming context (immutable snapshot only — never current Workflow/Preset)
- live canonical Output settings via injected ``settings_provider``
- local + fake ``modal://`` sources through the SHARED byte-resolution
  helper (same semantics as managed-asset GET; no Modal/network/GPU)
- response/error contract mapping (200/404/502/500, stable reasons,
  bounded secret-free messages, partial preservation)
- per-variant projection (Preview/Original independent, lazy missing),
  winner identity after retries/rerenders, Experiment cell parity
- Browser Download (asset GET) writes ZERO export state
- per-Asset concurrency safety under duplicate simultaneous POSTs
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from history_v2_repository import HistoryV2Repository
from history_v2_routes import register_history_v2_routes
from history_v2_store import HistoryV2Store


def _png_bytes() -> bytes:
    """Tiny deterministic 1x1 PNG."""
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class ExportRouteTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.data_root = self.tmp / "data"
        db_path = self.data_root / ".studio_history_v2" / "history_v2.db"
        self.repo = HistoryV2Repository(HistoryV2Store(db_path))
        self.save_root_a = self.tmp / "save_a"
        self.save_root_b = self.tmp / "save_b"
        # Live canonical Output settings — mutated by tests to prove the
        # provider is consulted AT EXPORT TIME.
        self.settings = {
            "save_folder": str(self.save_root_a),
            "output_format": "original",
            "quality": 75,
            "webp_lossless_compression": "balanced",
            "save_metadata_sidecar": True,
        }
        self.app = web.Application()
        register_history_v2_routes(
            self.app.router,
            self.data_root,
            settings_provider=lambda: dict(self.settings),
        )
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()
        self.addCleanup(self.client.close)

    # ── Seeding helpers ──────────────────────────────────────────────

    def _gen(self, created="2026-08-23T10:00:00.000+00:00", **kw):
        return self.repo.create_generation(
            prompt_text="a cat",
            preset_id=kw.pop("preset_id", "preset_gen"),
            preset_name=kw.pop("preset_name", "Gen Preset"),
            created_at=created,
            **kw,
        )

    def _snapshot(self, generation_id, name="Immutable Snapshot WF"):
        return self.repo.create_request_snapshot(
            generation_id=generation_id,
            workflow_json={"extra": {"workflow": {"name": name}}},
            workflow_hash="wh_deadbeef1234",
            generation_params={"seed": 4242},
            preset_snapshot={"preset_id": "preset_snap", "preset_name": "Snap Preset"},
        )

    def _completed_attempt(self, generation_id, mode="preview", created=None):
        attempt = self.repo.add_attempt(generation_id, mode=mode)
        self.repo.update_attempt_terminal(attempt.run_id, status="completed")
        return attempt

    def _attach_local(
        self,
        generation_id,
        run_id,
        asset_type="preview",
        key="node:9:slot:images:item:0",
        created=None,
        payload=None,
    ):
        payload = payload if payload is not None else _png_bytes()
        return self.repo.attach_asset(
            generation_id,
            run_id=run_id,
            asset_type=asset_type,
            data=payload,
            filename=f"{asset_type}.png",
            fmt="png",
            width=1,
            height=1,
            created_at=created,
            logical_output_key=key,
        ), payload

    def _adopt_remote(
        self,
        generation_id,
        run_id,
        payload,
        asset_type="preview",
        key="node:9:slot:images:item:0",
        sha256=None,
        created=None,
    ):
        return self.repo.adopt_asset(
            generation_id,
            run_id=run_id,
            reference=f"modal://ws_test||gpu_x||remote_volumes/{asset_type}_out.png",
            filename=f"{asset_type}_out.png",
            fmt="png",
            sha256=sha256 if sha256 is not None else _sha(payload),
            width=1,
            height=1,
            created_at=created,
            logical_output_key=key,
        )

    def _install_remote(self, payloads=None, error=None):
        """Patch the shared remote-read seam (no Modal/network/GPU)."""
        calls: list[dict] = []

        async def fake_read_output_asset(
            backend_path, *, expected_sha256="", gpu=None, workspace=None
        ):
            calls.append(
                {"path": backend_path, "sha": expected_sha256, "n": len(calls)}
            )
            if error is not None:
                raise error
            for suffix, payload in (payloads or {}).items():
                if backend_path.endswith(suffix):
                    return {"data": payload}
            raise FileNotFoundError(f"remote asset missing: {backend_path}")

        workspace_patch = mock.patch(
            "history_v2_routes._resolve_workspace_dict",
            return_value={"workspace_id": "ws_test"},
        )
        read_patch = mock.patch(
            "modal_client.read_output_asset", fake_read_output_asset
        )
        workspace_patch.start()
        read_patch.start()
        self.addCleanup(workspace_patch.stop)
        self.addCleanup(read_patch.stop)
        return calls

    # ── Request helpers ──────────────────────────────────────────────

    async def _export(self, asset_id, **kwargs):
        resp = await self.client.post(
            f"/comfymodal/history-v2/assets/{asset_id}/export", **kwargs
        )
        return resp.status, await resp.json()

    async def _detail(self, generation_id):
        resp = await self.client.get(
            f"/comfymodal/history-v2/generations/{generation_id}"
        )
        self.assertEqual(resp.status, 200)
        return (await resp.json())["item"]

    async def _experiment_detail(self, experiment_id):
        resp = await self.client.get(
            f"/comfymodal/history-v2/experiments/{experiment_id}"
        )
        self.assertEqual(resp.status, 200)
        return (await resp.json())["item"]

    def _images(self, root: Path) -> list[Path]:
        images = root / "images"
        if not images.is_dir():
            return []
        return sorted(p for p in images.iterdir() if p.is_file())


# ── 1–4. Local + fake modal:// Preview/Original exports ───────────────────


class SuccessfulExportTests(ExportRouteTestBase):
    async def test_local_preview_export_response_contract(self):
        gen = self._gen()
        self._snapshot(gen.generation_id)
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset, payload = self._attach_local(
            gen.generation_id, attempt.run_id, "preview"
        )
        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["asset_id"], asset.asset_id)
        self.assertEqual(body["export_state"], "exported")
        self.assertTrue(body["saved"])
        self.assertFalse(body["already_exported"])
        self.assertEqual(Path(body["destination_path"]).read_bytes(), payload)
        self.assertTrue(body["destination_path"].startswith(str(self.save_root_a)))
        self.assertEqual(body["byte_count"], len(payload))
        self.assertEqual(body["file_ext"], ".png")
        self.assertEqual(body["mime_type"], "image/png")
        self.assertTrue(body["exported_at"])
        record = self.repo.get_export_record(asset.asset_id)
        self.assertEqual(record.state, "exported")

    async def test_local_original_export_success(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        original, payload = self._attach_local(
            gen.generation_id, attempt.run_id, "original"
        )
        status, body = await self._export(original.asset_id)
        self.assertEqual(status, 200)
        self.assertTrue(body["saved"])
        self.assertEqual(body["export_state"], "exported")
        written = self._images(self.save_root_a)
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0].read_bytes(), payload)

    async def test_remote_preview_export_via_fake_modal(self):
        payload = _png_bytes()
        calls = self._install_remote(payloads={"preview_out.png": payload})
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset = self._adopt_remote(gen.generation_id, attempt.run_id, payload)
        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 200, body)
        self.assertTrue(body["saved"])
        self.assertEqual(body["export_state"], "exported")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["sha"], asset.sha256)
        self.assertEqual(
            Path(body["destination_path"]).read_bytes(), payload
        )
        self.assertEqual(self.repo.get_export_record(asset.asset_id).state, "exported")

    async def test_remote_original_export_via_fake_modal(self):
        payload = _png_bytes()
        calls = self._install_remote(payloads={"original_out.png": payload})
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset = self._adopt_remote(
            gen.generation_id, attempt.run_id, payload, asset_type="original"
        )
        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 200, body)
        self.assertTrue(body["saved"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(self._images(self.save_root_a)), 1)


# ── 5–9. Error contract ───────────────────────────────────────────────────


class ExportErrorContractTests(ExportRouteTestBase):
    async def test_unknown_asset_404_error_shape(self):
        status, body = await self._export("ast_does_not_exist")
        self.assertEqual(status, 404)
        self.assertEqual(
            set(body.keys()),
            {"status", "asset_id", "reason", "message", "export_state", "partial"},
        )
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["reason"], "asset_not_found")
        self.assertEqual(body["export_state"], "not_exported")
        self.assertFalse(body["partial"])
        self.assertIsNone(self.repo.get_export_record("ast_does_not_exist"))

    async def test_remote_retrieval_failure_maps_502_failed(self):
        calls = self._install_remote(error=RuntimeError("connection reset"))
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset = self._adopt_remote(gen.generation_id, attempt.run_id, _png_bytes())
        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 502)
        self.assertEqual(body["reason"], "source_unreadable")
        self.assertEqual(body["export_state"], "failed")
        self.assertFalse(body["partial"])
        self.assertLessEqual(len(body["message"]), 200)
        self.assertNotIn("Traceback", body["message"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.repo.get_export_record(asset.asset_id).state, "failed")
        self.assertEqual(self._images(self.save_root_a), [])

    async def test_remote_missing_after_retries_maps_404(self):
        self._install_remote()  # resolver up; backend file missing
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset = self._adopt_remote(gen.generation_id, attempt.run_id, _png_bytes())
        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 404)
        self.assertEqual(body["reason"], "source_unreadable")
        self.assertEqual(body["export_state"], "failed")
        self.assertEqual(self.repo.get_export_record(asset.asset_id).state, "failed")

    async def test_workspace_unavailable_404_without_record_write(self):
        patch = mock.patch(
            "history_v2_routes._resolve_workspace_dict", return_value=None
        )
        patch.start()
        self.addCleanup(patch.stop)
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset = self._adopt_remote(gen.generation_id, attempt.run_id, _png_bytes())
        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 404)
        self.assertEqual(body["reason"], "source_unreadable")
        self.assertEqual(body["export_state"], "not_exported")
        self.assertIsNone(self.repo.get_export_record(asset.asset_id))

    async def test_local_source_missing_404_without_record_write(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset, _ = self._attach_local(gen.generation_id, attempt.run_id)
        Path(asset.managed_path).unlink()
        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 404)
        self.assertIn("asset file not found", body["message"])
        self.assertEqual(body["export_state"], "not_exported")
        self.assertIsNone(self.repo.get_export_record(asset.asset_id))

    async def test_sha_mismatch_maps_502_no_output_written(self):
        payload = _png_bytes()
        self._install_remote(payloads={"preview_out.png": payload})
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset = self._adopt_remote(
            gen.generation_id,
            attempt.run_id,
            payload,
            sha256=_sha(b"totally-different-bytes"),
        )
        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 502)
        self.assertEqual(body["reason"], "hash_mismatch")
        self.assertEqual(body["export_state"], "failed")
        self.assertEqual(self._images(self.save_root_a), [])
        self.assertEqual(self.repo.get_export_record(asset.asset_id).state, "failed")

    async def test_conversion_failure_maps_500(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset, _ = self._attach_local(gen.generation_id, attempt.run_id)
        self.settings["output_format"] = "webp_lossy"

        def _boom(*args, **kwargs):
            raise RuntimeError("encoder exploded")

        patch = mock.patch("output_converter.convert_image_bytes", _boom)
        patch.start()
        self.addCleanup(patch.stop)
        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 500)
        self.assertEqual(body["reason"], "conversion_failed")
        self.assertEqual(body["export_state"], "failed")
        self.assertEqual(self._images(self.save_root_a), [])
        self.assertEqual(self.repo.get_export_record(asset.asset_id).state, "failed")

    async def test_write_failure_maps_500(self):
        blocker = self.tmp / "blocker_file"
        blocker.write_bytes(b"not a directory")
        self.settings["save_folder"] = str(blocker)
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset, _ = self._attach_local(gen.generation_id, attempt.run_id)
        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 500)
        self.assertEqual(body["reason"], "write_failed")
        self.assertEqual(body["export_state"], "failed")


# ── 10–12. Duplicate / missing / re-export ────────────────────────────────


class DuplicateMissingTests(ExportRouteTestBase):
    async def test_already_exported_reuses_existing_copy(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset, _ = self._attach_local(gen.generation_id, attempt.run_id)
        status1, first = await self._export(asset.asset_id)
        self.assertTrue(first["saved"])
        status2, second = await self._export(asset.asset_id)
        self.assertEqual(status2, 200)
        self.assertFalse(second["saved"])
        self.assertTrue(second["already_exported"])
        self.assertEqual(second["export_state"], "exported")
        self.assertEqual(second["destination_path"], first["destination_path"])
        self.assertEqual(len(self._images(self.save_root_a)), 1)

    async def test_deleted_destination_projects_missing_then_reexports(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset, _ = self._attach_local(gen.generation_id, attempt.run_id)
        _, first = await self._export(asset.asset_id)
        Path(first["destination_path"]).unlink()

        item = await self._detail(gen.generation_id)
        out = item["outputs"][0]
        self.assertEqual(out["preview_export_state"], "missing")
        self.assertEqual(item["export_state"], "none")

        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 200)
        self.assertTrue(body["saved"])
        self.assertFalse(body["already_exported"])
        self.assertEqual(body["export_state"], "exported")
        item = await self._detail(gen.generation_id)
        self.assertEqual(item["outputs"][0]["preview_export_state"], "exported")


# ── 13–16. Per-variant independence, indices, winners ─────────────────────


class ProjectionTests(ExportRouteTestBase):
    async def test_preview_and_original_states_independent(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        preview, _ = self._attach_local(
            gen.generation_id, attempt.run_id, "preview"
        )
        original, _ = self._attach_local(
            gen.generation_id, attempt.run_id, "original"
        )
        await self._export(preview.asset_id)
        item = await self._detail(gen.generation_id)
        out = item["outputs"][0]
        self.assertEqual(out["preview_asset_id"], preview.asset_id)
        self.assertEqual(out["preview_export_state"], "exported")
        self.assertEqual(out["original_asset_id"], original.asset_id)
        self.assertEqual(out["original_export_state"], "not_exported")
        self.assertEqual(out["preview_url"], f"/comfymodal/history-v2/assets/{preview.asset_id}")
        self.assertEqual(item["export_state"], "exported")

        await self._export(original.asset_id)
        item = await self._detail(gen.generation_id)
        out = item["outputs"][0]
        self.assertEqual(out["preview_export_state"], "exported")
        self.assertEqual(out["original_export_state"], "exported")

    async def test_nonexistent_original_is_not_reported_not_exported(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        preview, _ = self._attach_local(gen.generation_id, attempt.run_id)
        item = await self._detail(gen.generation_id)
        out = item["outputs"][0]
        self.assertIsNone(out["original_asset_id"])
        self.assertIsNone(out["original_export_state"])

    async def test_two_logical_outputs_use_distinct_real_indices(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        first, _ = self._attach_local(
            gen.generation_id,
            attempt.run_id,
            "preview",
            key="node:9:slot:images:item:0",
            created="2026-08-23T10:00:01.000+00:00",
        )
        second, _ = self._attach_local(
            gen.generation_id,
            attempt.run_id,
            "preview",
            key="node:9:slot:images:item:1",
            created="2026-08-23T10:00:02.000+00:00",
        )
        status_a, body_a = await self._export(first.asset_id)
        status_b, body_b = await self._export(second.asset_id)
        self.assertEqual((status_a, status_b), (200, 200))
        self.assertTrue(Path(body_a["destination_path"]).name.endswith("_0.png"))
        self.assertTrue(Path(body_b["destination_path"]).name.endswith("_1.png"))

        item = await self._detail(gen.generation_id)
        outputs = item["outputs"]
        self.assertEqual([o["index"] for o in outputs], [0, 1])
        self.assertEqual(outputs[0]["preview_asset_id"], first.asset_id)
        self.assertEqual(outputs[0]["preview_export_state"], "exported")
        self.assertEqual(outputs[1]["preview_asset_id"], second.asset_id)
        self.assertEqual(outputs[1]["preview_export_state"], "exported")

    async def test_retained_original_after_failed_retry_keeps_winner_identity(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        winner, _ = self._attach_local(
            gen.generation_id, attempt.run_id, "original",
            created="2026-08-23T10:00:01.000+00:00",
        )
        _, body = await self._export(winner.asset_id)
        self.assertTrue(body["saved"])

        # Failed retry: newest ORIGINAL attempt fails; its (unusable) asset
        # must never be projected while the retained winner stays usable.
        failed = self.repo.add_attempt(
            gen.generation_id, mode="original",
            started_at="2026-08-23T11:00:00.000+00:00",
        )
        self.repo.update_attempt_terminal(
            failed.run_id, status="failed", error="boom"
        )
        self._attach_local(
            gen.generation_id, failed.run_id, "original",
            key="node:9:slot:images:item:0",
            created="2026-08-23T11:00:01.000+00:00",
        )

        item = await self._detail(gen.generation_id)
        out = item["outputs"][0]
        self.assertEqual(out["original_asset_id"], winner.asset_id)
        self.assertEqual(
            out["original_url"],
            f"/comfymodal/history-v2/assets/{winner.asset_id}",
        )
        self.assertEqual(out["original_export_state"], "exported")
        status, body = await self._export(winner.asset_id)
        self.assertEqual(status, 200)
        self.assertTrue(body["already_exported"])

    async def test_rerender_new_winner_starts_not_exported(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        old_winner, _ = self._attach_local(
            gen.generation_id, attempt.run_id, "original",
            created="2026-08-23T10:00:01.000+00:00",
        )
        _, body = await self._export(old_winner.asset_id)
        self.assertTrue(body["saved"])

        rerender = self._completed_attempt(
            gen.generation_id, "original"
        )
        new_winner, _ = self._attach_local(
            gen.generation_id, rerender.run_id, "original",
            key="node:9:slot:images:item:0",
            created="2026-08-23T12:00:00.000+00:00",
        )
        self.assertNotEqual(new_winner.asset_id, old_winner.asset_id)

        item = await self._detail(gen.generation_id)
        out = item["outputs"][0]
        self.assertEqual(out["original_asset_id"], new_winner.asset_id)
        self.assertEqual(out["original_export_state"], "not_exported")
        # Historical truth for the superseded asset is untouched.
        self.assertEqual(
            self.repo.get_export_record(old_winner.asset_id).state, "exported"
        )
        status, body = await self._export(new_winner.asset_id)
        self.assertEqual(status, 200)
        self.assertTrue(body["saved"])


# ── 17–19. Experiment parity, eager-fetch, download separation ────────────


class ParityAndSeparationTests(ExportRouteTestBase):
    async def test_experiment_cell_projection_parity(self):
        exp = self.repo.create_experiment(name="grid", cells=[{}])
        cell = exp.cells[0]
        gen = self._gen(experiment_id=exp.experiment.experiment_id)
        attempt = self.repo.add_attempt(
            gen.generation_id, mode="preview", experiment_id=exp.experiment.experiment_id,
            cell_id=cell.cell_id,
        )
        self.repo.update_attempt_terminal(attempt.run_id, status="completed")
        preview, _ = self._attach_local(gen.generation_id, attempt.run_id)
        self.repo.update_experiment_cell(cell.cell_id, generation_id=gen.generation_id)

        status, body = await self._export(preview.asset_id)
        self.assertEqual(status, 200)

        exp_item = await self._experiment_detail(exp.experiment.experiment_id)
        cell_out = exp_item["cells"][0]["generation"]["outputs"][0]
        gen_out = (await self._detail(gen.generation_id))["outputs"][0]
        self.assertEqual(cell_out["preview_asset_id"], preview.asset_id)
        self.assertEqual(cell_out["preview_export_state"], "exported")
        self.assertEqual(cell_out, gen_out)

    async def test_no_remote_bytes_fetched_during_detail_projection(self):
        payload = _png_bytes()
        calls = self._install_remote(payloads={"preview_out.png": payload})
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset = self._adopt_remote(gen.generation_id, attempt.run_id, payload)

        await self._detail(gen.generation_id)
        await self._detail(gen.generation_id)
        self.assertEqual(calls, [])

        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(calls), 1)

    async def test_browser_download_get_writes_no_export_state(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset, payload = self._attach_local(gen.generation_id, attempt.run_id)
        resp = await self.client.get(
            f"/comfymodal/history-v2/assets/{asset.asset_id}"
        )
        self.assertEqual(resp.status, 200)
        self.assertEqual(await resp.read(), payload)
        self.assertIsNone(self.repo.get_export_record(asset.asset_id))
        item = await self._detail(gen.generation_id)
        self.assertEqual(item["outputs"][0]["preview_export_state"], "not_exported")
        self.assertEqual(item["export_state"], "none")


# ── 20–22. Concurrency, live settings, immutable naming ──────────────────


class SettingsAndConcurrencyTests(ExportRouteTestBase):
    async def test_concurrent_duplicate_posts_are_safe(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset, _ = self._attach_local(gen.generation_id, attempt.run_id)
        results = await asyncio.gather(
            self._export(asset.asset_id), self._export(asset.asset_id)
        )
        statuses = [status for status, _ in results]
        self.assertEqual(statuses, [200, 200])
        flags = sorted(body["saved"] for _, body in results)
        self.assertEqual(flags, [False, True])
        self.assertEqual(len(self._images(self.save_root_a)), 1)
        record = self.repo.get_export_record(asset.asset_id)
        self.assertEqual(record.state, "exported")
        destinations = {
            body["destination_path"] for _, body in results
        }
        self.assertEqual(len(destinations), 1)

    async def test_settings_read_at_export_time_not_registration(self):
        gen = self._gen()
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset, _ = self._attach_local(gen.generation_id, attempt.run_id)
        status, first = await self._export(asset.asset_id)
        self.assertEqual(status, 200)
        self.assertTrue(first["destination_path"].startswith(str(self.save_root_a)))

        self.settings["save_folder"] = str(self.save_root_b)
        status, second = await self._export(asset.asset_id)
        self.assertEqual(status, 200)
        self.assertTrue(second["saved"], "folder change is an explicit export")
        self.assertFalse(second["already_exported"])
        self.assertTrue(second["destination_path"].startswith(str(self.save_root_b)))
        self.assertEqual(len(self._images(self.save_root_a)), 1)
        self.assertEqual(len(self._images(self.save_root_b)), 1)

    async def test_naming_derived_from_immutable_snapshot_only(self):
        gen = self._gen(preset_id="preset_gen", preset_name="Gen Preset")
        self._snapshot(gen.generation_id, name="Immutable Snapshot WF")
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset, _ = self._attach_local(gen.generation_id, attempt.run_id)
        status, body = await self._export(asset.asset_id)
        self.assertEqual(status, 200, body)
        filename = Path(body["destination_path"]).name
        self.assertIn("Immutable Snapshot WF", filename)
        self.assertIn("seed-4242", filename)
        self.assertTrue(filename.endswith("_0.png"))

        sidecar = json.loads(Path(body["metadata_path"]).read_text(encoding="utf-8"))
        self.assertEqual(sidecar["workflow_name"], "Immutable Snapshot WF")
        self.assertEqual(sidecar["workflow_hash"], "wh_deadbeef1234")
        self.assertEqual(sidecar["seed"], "4242")
        self.assertEqual(sidecar["preset_id"], "preset_snap")
        self.assertEqual(sidecar["preset_name"], "Snap Preset")
        self.assertEqual(sidecar["output_index"], 0)
        self.assertEqual(sidecar["asset_id"], asset.asset_id)

    async def test_bodyless_route_ignores_client_supplied_identity(self):
        gen = self._gen()
        self._snapshot(gen.generation_id)
        attempt = self._completed_attempt(gen.generation_id, "preview")
        asset, _ = self._attach_local(gen.generation_id, attempt.run_id)
        other = self._gen(created="2026-08-23T09:00:00.000+00:00")
        status, body = await self._export(
            asset.asset_id,
            json={
                "generation_id": other.generation_id,
                "output_index": 99,
                "variant": "thumbnail",
                "filename": "hax",
                "workflow_name": "Client WF",
            },
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["saved"])
        filename = Path(body["destination_path"]).name
        self.assertIn("Immutable Snapshot WF", filename)
        self.assertTrue(filename.endswith("_0.png"))


if __name__ == "__main__":
    unittest.main()
