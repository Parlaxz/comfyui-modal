"""Focused tests for the History V2 configured-folder Export CORE service.

Covers ``history_v2_export.HistoryV2ExportService`` only — no HTTP route,
no frontend, no legacy run-history involvement:

- local PNG / WebP export through the canonical converter
- remote ``modal://`` export via an injected FAKE byte resolver (no Modal,
  no network, no GPU) + truthful remote-failure handling
- sha256 identity verification (mismatch → failed, no corrupted output)
- per-asset export state: Preview/Original independence, rerender
  successors start not_exported, no Generation-level collapse
- duplicate idempotent reuse; missing-destination detection + re-export;
  folder/format changes are explicit exports (never false hits)
- failure atomicity: conversion/write failures never lie; record-persist
  failure after file write is partial + cleaned up (orphan documented)
- real output index in filenames; traversal/hostile-name containment
- metadata sidecar on/off with full History identity
"""

from __future__ import annotations

import ast
import base64
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from history_v2_export import (
    ExportNamingContext,
    ExportOptions,
    HistoryV2ExportService,
    REASON_ASSET_NOT_FOUND,
    REASON_CONVERSION_FAILED,
    REASON_HASH_MISMATCH,
    REASON_RECORD_PERSIST_FAILED,
    REASON_REMOTE_RESOLVER_UNAVAILABLE,
    REASON_SOURCE_UNREADABLE,
    REASON_WRITE_FAILED,
)
from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _png_bytes(color=(180, 40, 40), size=(8, 8)) -> bytes:
    if not HAS_PIL:
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
            "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        )
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class FakeRemoteResolver:
    """Injected modal:// byte resolver — no network, no Modal, no GPU."""

    def __init__(self, payloads=None, error=None):
        self.payloads = dict(payloads or {})
        self.error = error
        self.calls: list[str] = []

    async def __call__(self, asset):
        self.calls.append(asset.asset_id)
        if self.error is not None:
            raise self.error
        managed = str(asset.managed_path)
        for suffix, payload in self.payloads.items():
            if managed.endswith(suffix):
                return payload
        raise FileNotFoundError(f"remote asset missing: {managed}")


class ExportServiceTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        db_path = self.tmp / ".studio_history_v2" / "history_v2.db"
        self.repo = HistoryV2Repository(HistoryV2Store(db_path))
        self.save_root = self.tmp / "save_root"
        self.gen = self.repo.create_generation(
            prompt_text="a cat",
            preset_id="preset_x",
            preset_name="Preset X",
            created_at="2026-08-23T10:00:00.000+00:00",
        )
        self.attempt = self.repo.add_attempt(self.gen.generation_id, mode="preview")
        self.repo.update_attempt_terminal(self.attempt.run_id, status="completed")
        self.service = HistoryV2ExportService(self.repo)

    def _options(self, **kw) -> ExportOptions:
        kw.setdefault("save_folder", str(self.save_root))
        return ExportOptions(**kw)

    def _naming(self, **kw) -> ExportNamingContext:
        kw.setdefault("workflow_name", "Test Workflow")
        kw.setdefault("workflow_hash", "wh_test_123456")
        kw.setdefault("seed", "42")
        kw.setdefault("preset_id", "preset_x")
        kw.setdefault("preset_name", "Preset X")
        return ExportNamingContext(**kw)

    def _attach_local(self, asset_type="preview", color=(180, 40, 40), key=None):
        payload = _png_bytes(color=color)
        return self.repo.attach_asset(
            self.gen.generation_id,
            run_id=self.attempt.run_id,
            asset_type=asset_type,
            data=payload,
            filename=f"{asset_type}.png",
            fmt="png",
            width=8,
            height=8,
            logical_output_key=key or "node:9:slot:images:item:0",
        ), payload

    def _adopt_remote(self, payload: bytes, name="remote_out.png", key=None):
        return self.repo.adopt_asset(
            self.gen.generation_id,
            run_id=self.attempt.run_id,
            reference=f"modal://ws_test||remote_volumes/{name}",
            filename=name,
            fmt="png",
            sha256=_sha(payload),
            width=8,
            height=8,
            logical_output_key=key or "node:9:slot:images:item:0",
        )

    def _images_dir(self) -> Path:
        return self.save_root / "images"

    def _written_images(self) -> list[Path]:
        images = self._images_dir()
        if not images.is_dir():
            return []
        return sorted(p for p in images.iterdir() if p.is_file())


# ── 1+17. Local PNG export; managed source untouched ──────────────────────

class LocalExportTests(ExportServiceTestBase):
    async def test_local_png_export_writes_file_and_exported_record(self):
        asset, payload = self._attach_local(asset_type="original")
        result = await self.service.export_asset(
            asset.asset_id, self._options(), self._naming(output_index=0)
        )
        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.saved)
        self.assertFalse(result.already_exported)
        self.assertEqual(result.state, "exported")
        self.assertEqual(result.file_ext, ".png")
        self.assertEqual(result.mime_type, "image/png")
        self.assertEqual(result.byte_count, len(payload))

        written = self._written_images()
        self.assertEqual(len(written), 1)
        self.assertEqual(Path(result.destination_path), written[0])
        self.assertEqual(written[0].read_bytes(), payload)

        record = self.repo.get_export_record(asset.asset_id)
        self.assertIsNotNone(record)
        self.assertEqual(record.state, "exported")
        self.assertEqual(record.destination_path, result.destination_path)
        self.assertTrue(record.exported_at)

    async def test_managed_source_unchanged_after_success_and_failure(self):
        asset, payload = self._attach_local(asset_type="original")
        managed_path = Path(asset.managed_path)
        before = managed_path.read_bytes()

        ok = await self.service.export_asset(
            asset.asset_id, self._options(), self._naming()
        )
        self.assertTrue(ok.ok)

        broken = HistoryV2ExportService(
            self.repo,
            byte_resolver=FakeRemoteResolver(error=RuntimeError("x")),
        )
        bad = await broken.export_asset(
            asset.asset_id,
            self._options(output_format="webp_lossy"),
            self._naming(),
        )
        # Conversion of the local asset still happens locally; force a
        # source-read failure instead by pointing at a missing file copy.
        ghost, _ = self._attach_local(asset_type="preview", color=(1, 2, 3))
        Path(ghost.managed_path).unlink()
        failed = await self.service.export_asset(
            ghost.asset_id, self._options(), self._naming()
        )
        self.assertEqual(failed.reason, REASON_SOURCE_UNREADABLE)

        self.assertEqual(managed_path.read_bytes(), before)
        self.assertEqual(_sha(managed_path.read_bytes()), asset.sha256)
        record = self.repo.get_export_record(asset.asset_id)
        self.assertEqual(record.state, "exported")

    async def test_unknown_asset_errors_without_record_write(self):
        result = await self.service.export_asset(
            "ast_does_not_exist", self._options(), self._naming()
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, REASON_ASSET_NOT_FOUND)
        self.assertIsNone(self.repo.get_export_record("ast_does_not_exist"))


# ── 2. WebP conversion ────────────────────────────────────────────────────

@unittest.skipUnless(HAS_PIL, "Pillow required for conversion tests")
class WebPExportTests(ExportServiceTestBase):
    async def test_local_webp_lossy_export_converts(self):
        asset, _ = self._attach_local(asset_type="original")
        result = await self.service.export_asset(
            asset.asset_id,
            self._options(output_format="webp_lossy", quality=60),
            self._naming(),
        )
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.file_ext, ".webp")
        self.assertEqual(result.mime_type, "image/webp")
        self.assertEqual(result.quality, 60)
        self.assertTrue(result.destination_path.endswith(".webp"))
        written = self._written_images()
        self.assertEqual(len(written), 1)
        with Image.open(written[0]) as img:
            self.assertEqual(img.format, "WEBP")

    async def test_original_format_is_byte_preserving_fast_path(self):
        asset, payload = self._attach_local(asset_type="original")
        converter_calls = []

        def _spy_converter(*args, **kwargs):
            converter_calls.append((args, kwargs))
            raise AssertionError("converter must not run on the fast path")

        service = HistoryV2ExportService(self.repo, converter=_spy_converter)
        result = await service.export_asset(
            asset.asset_id, self._options(output_format="original"), self._naming()
        )
        self.assertTrue(result.ok)
        self.assertEqual(converter_calls, [])
        self.assertEqual(Path(result.destination_path).read_bytes(), payload)


# ── 3+16. Remote modal:// export via fake resolver ────────────────────────

class RemoteExportTests(ExportServiceTestBase):
    async def test_remote_modal_asset_exports_via_fake_resolver(self):
        payload = _png_bytes(color=(10, 200, 30))
        asset = self._adopt_remote(payload)
        resolver = FakeRemoteResolver(payloads={"remote_out.png": payload})
        service = HistoryV2ExportService(self.repo, byte_resolver=resolver)

        result = await service.export_asset(
            asset.asset_id, self._options(), self._naming(output_index=1)
        )
        self.assertTrue(result.ok, result.message)
        self.assertEqual(resolver.calls, [asset.asset_id])
        written = self._written_images()
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0].read_bytes(), payload)
        record = self.repo.get_export_record(asset.asset_id)
        self.assertEqual(record.state, "exported")
        self.assertEqual(record.destination_path, result.destination_path)
        # No local managed materialization appeared anywhere.
        self.assertFalse(Path(asset.managed_path).exists())

    async def test_remote_without_resolver_errors_without_record(self):
        payload = _png_bytes(color=(5, 5, 5))
        asset = self._adopt_remote(payload)
        result = await self.service.export_asset(
            asset.asset_id, self._options(), self._naming()
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, REASON_REMOTE_RESOLVER_UNAVAILABLE)
        self.assertIsNone(self.repo.get_export_record(asset.asset_id))
        self.assertEqual(self._written_images(), [])

    async def test_remote_resolver_failure_is_truthful_failed_attempt(self):
        payload = _png_bytes(color=(5, 5, 5))
        asset = self._adopt_remote(payload)
        resolver = FakeRemoteResolver(error=RuntimeError("modal unavailable"))
        service = HistoryV2ExportService(self.repo, byte_resolver=resolver)
        result = await service.export_asset(
            asset.asset_id, self._options(), self._naming()
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, REASON_SOURCE_UNREADABLE)
        self.assertEqual(result.state, "failed")
        record = self.repo.get_export_record(asset.asset_id)
        self.assertIsNotNone(record)
        self.assertEqual(record.state, "failed")
        self.assertFalse(record.destination_path)
        self.assertEqual(self._written_images(), [])

    async def test_remote_hash_mismatch_fails_without_output(self):
        real_payload = _png_bytes(color=(200, 10, 10))
        wrong_payload = _png_bytes(color=(10, 10, 200))
        asset = self._adopt_remote(real_payload)
        resolver = FakeRemoteResolver(payloads={"remote_out.png": wrong_payload})
        service = HistoryV2ExportService(self.repo, byte_resolver=resolver)
        result = await service.export_asset(
            asset.asset_id, self._options(), self._naming()
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, REASON_HASH_MISMATCH)
        record = self.repo.get_export_record(asset.asset_id)
        self.assertEqual(record.state, "failed")
        self.assertEqual(self._written_images(), [])


# ── 4. Hash mismatch (local) ──────────────────────────────────────────────

class LocalHashMismatchTests(ExportServiceTestBase):
    async def test_local_corrupted_source_fails_truthfully(self):
        asset, payload = self._attach_local(asset_type="original")
        Path(asset.managed_path).write_bytes(_png_bytes(color=(99, 99, 99)))
        result = await self.service.export_asset(
            asset.asset_id, self._options(), self._naming()
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, REASON_HASH_MISMATCH)
        self.assertEqual(result.state, "failed")
        record = self.repo.get_export_record(asset.asset_id)
        self.assertEqual(record.state, "failed")
        self.assertEqual(self._written_images(), [])
        # Managed source itself was left as-is (never rewritten).
        self.assertNotEqual(Path(asset.managed_path).read_bytes(), payload)


# ── 5+14. Preview / Original independence ─────────────────────────────────

class VariantIndependenceTests(ExportServiceTestBase):
    LOGICAL_KEY = "node:9:slot:images:item:0"

    async def test_preview_and_original_export_independently(self):
        preview, _ = self._attach_local("preview", color=(0, 0, 255), key=self.LOGICAL_KEY)
        original, _ = self._attach_local("original", color=(255, 0, 0), key=self.LOGICAL_KEY)

        p_res = await self.service.export_asset(
            preview.asset_id, self._options(), self._naming(output_index=0)
        )
        self.assertTrue(p_res.ok)
        self.assertEqual(
            self.service.get_export_state(original.asset_id).state,
            "not_exported",
        )

        o_res = await self.service.export_asset(
            original.asset_id, self._options(), self._naming(output_index=0)
        )
        self.assertTrue(o_res.ok)
        self.assertNotEqual(p_res.destination_path, o_res.destination_path)

        p_view = self.service.get_export_state(preview.asset_id)
        o_view = self.service.get_export_state(original.asset_id)
        self.assertEqual(p_view.state, "exported")
        self.assertEqual(o_view.state, "exported")
        self.assertEqual(len(self._written_images()), 2)

    async def test_deleting_preview_copy_leaves_original_exported(self):
        preview, _ = self._attach_local("preview", color=(0, 0, 255), key=self.LOGICAL_KEY)
        original, _ = self._attach_local("original", color=(255, 0, 0), key=self.LOGICAL_KEY)
        await self.service.export_asset(preview.asset_id, self._options(), self._naming())
        await self.service.export_asset(original.asset_id, self._options(), self._naming())

        preview_dest = self.repo.get_export_record(preview.asset_id).destination_path
        os.unlink(preview_dest)

        p_view = self.service.get_export_state(preview.asset_id)
        o_view = self.service.get_export_state(original.asset_id)
        self.assertEqual(p_view.state, "missing")
        self.assertEqual(o_view.state, "exported")


# ── 6+7. Duplicate reuse / missing recovery ───────────────────────────────

class DuplicateAndMissingTests(ExportServiceTestBase):
    async def test_duplicate_export_reuses_existing_copy(self):
        asset, _ = self._attach_local(asset_type="original")
        first = await self.service.export_asset(asset.asset_id, self._options(), self._naming())
        second = await self.service.export_asset(asset.asset_id, self._options(), self._naming())

        self.assertTrue(first.saved and not first.already_exported)
        self.assertTrue(second.saved)
        self.assertTrue(second.already_exported)
        self.assertEqual(second.destination_path, first.destination_path)
        self.assertEqual(second.exported_at, first.exported_at)
        self.assertEqual(len(self._written_images()), 1)

    async def test_deleted_destination_classified_missing_then_reexports(self):
        asset, _ = self._attach_local(asset_type="original")
        first = await self.service.export_asset(asset.asset_id, self._options(), self._naming())
        os.unlink(first.destination_path)

        view = self.service.get_export_state(asset.asset_id)
        self.assertEqual(view.state, "missing")
        self.assertFalse(view.destination_exists)
        persisted = self.repo.get_export_record(asset.asset_id)
        self.assertEqual(persisted.state, "missing")

        again = await self.service.export_asset(asset.asset_id, self._options(), self._naming())
        self.assertTrue(again.ok)
        self.assertFalse(again.already_exported)
        self.assertEqual(again.destination_path, first.destination_path)
        self.assertEqual(
            self.repo.get_export_record(asset.asset_id).state, "exported"
        )
        self.assertEqual(len(self._written_images()), 1)

    async def test_folder_change_is_explicit_export_not_false_hit(self):
        asset, _ = self._attach_local(asset_type="original")
        folder_a = self.tmp / "folder_a"
        folder_b = self.tmp / "folder_b"
        r1 = await self.service.export_asset(
            asset.asset_id, self._options(save_folder=str(folder_a)), self._naming()
        )
        self.assertTrue(r1.ok)
        r2 = await self.service.export_asset(
            asset.asset_id, self._options(save_folder=str(folder_b)), self._naming()
        )
        self.assertTrue(r2.ok)
        self.assertFalse(r2.already_exported)
        self.assertTrue(str(r2.destination_path).startswith(str(folder_b)))
        self.assertTrue(os.path.isfile(r1.destination_path), "old copy untouched")
        record = self.repo.get_export_record(asset.asset_id)
        self.assertEqual(record.destination_path, r2.destination_path)

    @unittest.skipUnless(HAS_PIL, "Pillow required")
    async def test_format_change_is_explicit_export_not_false_hit(self):
        asset, _ = self._attach_local(asset_type="original")
        r1 = await self.service.export_asset(
            asset.asset_id, self._options(output_format="original"), self._naming()
        )
        r2 = await self.service.export_asset(
            asset.asset_id,
            self._options(output_format="webp_lossless"),
            self._naming(),
        )
        self.assertTrue(r1.ok and r2.ok)
        self.assertFalse(r2.already_exported)
        self.assertTrue(r2.destination_path.endswith(".webp"))
        self.assertEqual(len(self._written_images()), 2)


# ── 8+9+10. Failure atomicity ─────────────────────────────────────────────

class FailureAtomicityTests(ExportServiceTestBase):
    async def test_converter_exception_marks_failed_no_file_no_lie(self):
        asset, _ = self._attach_local(asset_type="original")

        def _boom(*args, **kwargs):
            raise RuntimeError("encoder exploded")

        service = HistoryV2ExportService(self.repo, converter=_boom)
        result = await service.export_asset(
            asset.asset_id,
            self._options(output_format="webp_lossy"),
            self._naming(),
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, REASON_CONVERSION_FAILED)
        self.assertEqual(result.state, "failed")
        record = self.repo.get_export_record(asset.asset_id)
        self.assertEqual(record.state, "failed")
        self.assertEqual(self._written_images(), [])

    async def test_converter_silent_png_fallback_is_rejected(self):
        asset, _ = self._attach_local(asset_type="original")
        sneaky = {
            "bytes": b"png-bytes",
            "mime_type": "image/png",
            "file_ext": ".png",
            "fallback": True,
            "error": "webp encode failed",
        }
        service = HistoryV2ExportService(
            self.repo, converter=lambda *a, **k: dict(sneaky)
        )
        result = await service.export_asset(
            asset.asset_id,
            self._options(output_format="webp_lossy"),
            self._naming(),
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, REASON_CONVERSION_FAILED)
        self.assertEqual(self._written_images(), [])

    async def test_write_failure_marks_failed_and_writes_nothing(self):
        asset, _ = self._attach_local(asset_type="original")
        with mock.patch.object(
            HistoryV2ExportService,
            "_atomic_write",
            side_effect=OSError("disk full"),
        ):
            result = await self.service.export_asset(
                asset.asset_id, self._options(), self._naming()
            )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, REASON_WRITE_FAILED)
        record = self.repo.get_export_record(asset.asset_id)
        self.assertEqual(record.state, "failed")
        self.assertEqual(self._written_images(), [])

    async def test_record_persist_failure_after_write_cleans_up_partial(self):
        asset, _ = self._attach_local(asset_type="original")
        with mock.patch.object(
            self.repo,
            "upsert_export_record",
            side_effect=RuntimeError("db locked"),
        ):
            result = await self.service.export_asset(
                asset.asset_id, self._options(), self._naming()
            )
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, REASON_RECORD_PERSIST_FAILED)
        self.assertTrue(result.partial)
        self.assertTrue(result.destination_path, "partial report names the path")
        self.assertEqual(result.orphan_path, "", "cleanup removed the copies")
        self.assertFalse(os.path.isfile(result.destination_path))
        self.assertEqual(self._written_images(), [])
        self.assertIsNone(self.repo.get_export_record(asset.asset_id))


# ── 11. Real output index in filenames ────────────────────────────────────

class FilenameIdentityTests(ExportServiceTestBase):
    async def test_real_output_index_encoded_in_filename(self):
        asset0, _ = self._attach_local("preview", color=(1, 2, 3), key="node:9:slot:images:item:0")
        asset2, _ = self._attach_local("preview", color=(4, 5, 6), key="node:9:slot:images:item:2")

        r0 = await self.service.export_asset(asset0.asset_id, self._options(), self._naming(output_index=0))
        r2 = await self.service.export_asset(asset2.asset_id, self._options(), self._naming(output_index=2))

        self.assertTrue(r0.ok and r2.ok)
        self.assertTrue(Path(r0.destination_path).name.endswith("_0.png"))
        self.assertTrue(Path(r2.destination_path).name.endswith("_2.png"))
        self.assertNotEqual(r0.destination_path, r2.destination_path)

    def test_naming_context_rejects_bad_index(self):
        with self.assertRaises(ValueError):
            ExportNamingContext(output_index=True)
        with self.assertRaises(ValueError):
            ExportNamingContext(output_index=-1)


# ── 12. Path-safety containment ───────────────────────────────────────────

class PathSafetyTests(ExportServiceTestBase):
    async def _export_with_name(self, workflow_name: str, seed="42"):
        asset, _ = self._attach_local("preview", color=(7, 8, 9))
        return await self.service.export_asset(
            asset.asset_id,
            self._options(),
            self._naming(workflow_name=workflow_name, seed=seed),
        )

    async def test_traversal_like_names_stay_inside_images_dir(self):
        result = await self._export_with_name("../../../../evil")
        self.assertTrue(result.ok, result.message)
        images_dir = os.path.normcase(os.path.abspath(str(self._images_dir())))
        actual_dir = os.path.normcase(os.path.abspath(os.path.dirname(result.destination_path)))
        self.assertEqual(actual_dir, images_dir)
        name = Path(result.destination_path).name
        # Canonical sanitizer turns separators into underscores; the
        # security invariant is containment + zero path separators.
        self.assertNotIn("/", name)
        self.assertNotIn("\\", name)
        self.assertEqual(Path(name).parts, (name,))

    async def test_invalid_windows_chars_unicode_and_long_names_contained(self):
        hostile_names = [
            'a<b>:c|d?e*f"g',
            "héllo🎉wörld",
            "x" * 5000,
            "con\trol\x01chars",
        ]
        images_dir = os.path.normcase(os.path.abspath(str(self._images_dir())))
        for name in hostile_names:
            result = await self._export_with_name(name)
            self.assertTrue(result.ok, f"{name[:20]}: {result.message}")
            actual_dir = os.path.normcase(
                os.path.abspath(os.path.dirname(result.destination_path))
            )
            self.assertEqual(actual_dir, images_dir, name[:20])
            self.assertLess(len(result.destination_path), 260)
            stem = Path(result.destination_path).stem
            for ch in '<>:"/\\|?*':
                self.assertNotIn(ch, stem)

    async def test_different_assets_never_overwrite_each_other(self):
        asset_a, _ = self._attach_local("preview", color=(11, 11, 11), key="node:1:slot:images:item:0")
        asset_b, _ = self._attach_local("preview", color=(22, 22, 22), key="node:2:slot:images:item:0")
        naming = self._naming(workflow_name="Same Name", output_index=0)
        ra = await self.service.export_asset(asset_a.asset_id, self._options(), naming)
        rb = await self.service.export_asset(asset_b.asset_id, self._options(), naming)
        self.assertTrue(ra.ok and rb.ok)
        self.assertNotEqual(ra.destination_path, rb.destination_path)
        self.assertEqual(len(self._written_images()), 2)
        self.assertEqual(
            Path(ra.destination_path).read_bytes(),
            Path(asset_a.managed_path).read_bytes(),
        )


# ── 13+14. Metadata sidecar ───────────────────────────────────────────────

class SidecarTests(ExportServiceTestBase):
    async def _export(self, sidecar: bool):
        asset, _ = self._attach_local("original", color=(30, 30, 144))
        result = await self.service.export_asset(
            asset.asset_id,
            self._options(save_metadata_sidecar=sidecar),
            self._naming(output_index=3),
        )
        return asset, result

    async def test_sidecar_on_carries_history_identity(self):
        asset, result = await self._export(sidecar=True)
        self.assertTrue(result.ok)
        self.assertTrue(result.metadata_path)
        self.assertTrue(os.path.isfile(result.metadata_path))
        meta = json.loads(Path(result.metadata_path).read_text(encoding="utf-8"))
        self.assertEqual(meta["generation_id"], asset.generation_id)
        self.assertEqual(meta["run_id"], asset.run_id)
        self.assertEqual(meta["asset_id"], asset.asset_id)
        self.assertEqual(meta["variant"], "original")
        self.assertEqual(meta["logical_output_key"], asset.logical_output_key)
        self.assertEqual(meta["output_index"], 3)
        self.assertEqual(meta["preset_id"], "preset_x")
        self.assertEqual(meta["preset_name"], "Preset X")
        self.assertEqual(meta["workflow_hash"], "wh_test_123456")
        self.assertEqual(meta["seed"], "42")
        self.assertEqual(meta["exported_via"], "history_v2_export")
        blob = json.dumps(meta).lower()
        for forbidden in ("token", "secret", "password", "api_key"):
            self.assertNotIn(forbidden, blob)

    async def test_sidecar_off_writes_no_metadata(self):
        asset, result = await self._export(sidecar=False)
        self.assertTrue(result.ok)
        self.assertEqual(result.metadata_path, "")
        metadata_dir = self.save_root / "metadata"
        if metadata_dir.is_dir():
            self.assertEqual(list(metadata_dir.iterdir()), [])


# ── 15+16. Rerender semantics ─────────────────────────────────────────────

class RerenderTests(ExportServiceTestBase):
    KEY = "node:9:slot:images:item:0"

    async def test_new_original_after_rerender_starts_not_exported(self):
        old, old_payload = self._attach_local("original", color=(1, 1, 1), key=self.KEY)
        r_old = await self.service.export_asset(old.asset_id, self._options(), self._naming())
        self.assertTrue(r_old.ok)

        new_payload = _png_bytes(color=(2, 2, 2))
        new = self.repo.attach_asset(
            self.gen.generation_id,
            run_id=self.attempt.run_id,
            asset_type="original",
            data=new_payload,
            filename="o2.png",
            fmt="png",
            logical_output_key=self.KEY,
        )
        view = self.service.get_export_state(new.asset_id)
        self.assertEqual(view.state, "not_exported")
        self.assertIsNone(view.record)
        self.assertEqual(
            self.service.get_export_state(old.asset_id).state, "exported",
            "old export record remains historical truth",
        )

        r_new = await self.service.export_asset(new.asset_id, self._options(), self._naming())
        self.assertTrue(r_new.ok)
        self.assertNotEqual(r_new.destination_path, r_old.destination_path)

    async def test_identical_content_new_asset_is_not_transferred(self):
        payload = _png_bytes(color=(3, 3, 3))
        old = self.repo.attach_asset(
            self.gen.generation_id, asset_type="original", data=payload,
            filename="a.png", fmt="png", logical_output_key=self.KEY,
        )
        await self.service.export_asset(old.asset_id, self._options(), self._naming())
        twin = self.repo.attach_asset(
            self.gen.generation_id, asset_type="original", data=payload,
            filename="b.png", fmt="png", logical_output_key=self.KEY,
        )
        self.assertEqual(twin.sha256, old.sha256)
        self.assertNotEqual(twin.asset_id, old.asset_id)
        self.assertEqual(
            self.service.get_export_state(twin.asset_id).state,
            "not_exported",
            "identical bytes under a NEW asset_id never inherit export state",
        )


# ── 13 (lazy classification) + state query surface ────────────────────────

class StateQueryTests(ExportServiceTestBase):
    async def test_never_exported_asset_reports_not_exported(self):
        asset, _ = self._attach_local("preview")
        view = self.service.get_export_state(asset.asset_id)
        self.assertEqual(view.state, "not_exported")
        self.assertIsNone(view.record)
        self.assertIsNone(view.destination_exists)

    async def test_missing_persistence_can_be_read_only(self):
        asset, _ = self._attach_local("original")
        result = await self.service.export_asset(asset.asset_id, self._options(), self._naming())
        os.unlink(result.destination_path)
        view = self.service.get_export_state(asset.asset_id, persist_missing=False)
        self.assertEqual(view.state, "missing")
        self.assertEqual(
            self.repo.get_export_record(asset.asset_id).state, "exported",
            "read-only query must not mutate the record",
        )


# ── 18. No legacy run-history dependency ──────────────────────────────────

class NoLegacyDependencyTests(unittest.TestCase):
    ALLOWED_IMPORTS = {
        "__future__",
        "hashlib",
        "inspect",
        "os",
        "json",
        "datetime",
        "dataclasses",
        "pathlib",
        "typing",
        "history_v2_models",
        "output_saver",
        "output_converter",
    }

    def test_module_imports_are_legacy_free(self):
        source = (ROOT / "history_v2_export.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
        unexpected = imported - self.ALLOWED_IMPORTS
        self.assertEqual(unexpected, set(), f"unexpected imports: {unexpected}")

    def test_module_imports_cleanly_standalone(self):
        import history_v2_export

        self.assertTrue(hasattr(history_v2_export, "HistoryV2ExportService"))


if __name__ == "__main__":
    unittest.main()
