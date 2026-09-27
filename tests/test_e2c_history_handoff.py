"""E2C deterministic coverage: History handoff, multi-asset producer results,
and Thumbnail derivatives.

Covers the E2C seam:
  runtime/result metadata -> History writer -> correct Attempt mode
  -> correct Preview/Original asset type -> optional Thumbnail derivative
  under the SAME logical output key -> required association gate.

No Modal, no deployment, no live generation, no GPU spend.
"""
from __future__ import annotations

import base64
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfymodal_runtime.contracts import build_logical_output_key
from comfymodal_runtime.output_delivery import (
    Attempt,
    ConversionMeta,
    OutputItem,
    attempt_to_descriptor_result,
)
from history_v2_models import Asset, RunAttempt
from history_v2_repository import HistoryV2Repository
from history_v2_store import HistoryV2Store
from history_v2_writer import (
    _gen_id,
    _run_id,
    get_writer,
    reset_writer_config,
    semantic_output_mode,
    set_asset_resolver,
)

_LATER = "2026-01-01T10:05:00.000+00:00"


def _png_bytes() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )


def _webp_bytes() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buffer, format="WEBP", quality=75)
    return buffer.getvalue()


def _thumb_webp_bytes() -> bytes:
    """Distinct WebP payload so thumbnail content hashes differ from primaries."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (3, 5), (200, 100, 50)).save(buffer, format="WEBP", quality=60)
    return buffer.getvalue()


class _WriterCase(unittest.TestCase):
    """Shared temp-store writer harness (mirrors the C14 test conventions)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_root = Path(self._tmp.name)
        self.addCleanup(reset_writer_config)
        self.writer = get_writer(self.tmp_root)
        self.db_path = self.tmp_root / ".studio_history_v2" / "history_v2.db"
        self.repo = HistoryV2Repository(HistoryV2Store(self.db_path))

    def _producer_file(self, name: str, payload: bytes | None = None) -> str:
        path = self.tmp_root / name
        path.write_bytes(payload if payload is not None else _png_bytes())
        return str(path)

    def _record(
        self,
        asset_id: str,
        path: str,
        *,
        variant: str,
        mime_type: str = "image/png",
        node_id: str = "6",
        output_key: str = "images",
        output_index: int = 0,
        logical_output_key: str | None = None,
        width: int = 1024,
        height: int = 512,
        parent_asset_id: str = "",
    ) -> dict:
        record = {
            "asset_id": asset_id,
            "path": path,
            "mime_type": mime_type,
            "content_hash": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "width": width,
            "height": height,
            "byte_size": Path(path).stat().st_size,
            "variant": variant,
            "node_id": node_id,
            "output_key": output_key,
            "output_index": output_index,
        }
        if logical_output_key:
            record["logical_output_key"] = logical_output_key
        if parent_asset_id:
            record["parent_asset_id"] = parent_asset_id
        return record

    def _resolver(self, *records: dict) -> None:
        table = {r["asset_id"]: r for r in records}

        def resolve(asset_id):
            return table.get(asset_id)

        set_asset_resolver(resolve)


# â”€â”€ 1-3: Attempt mode â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class AttemptModeHandoffTests(_WriterCase):
    def test_preview_request_creates_preview_mode_attempt(self):
        self.writer.record_run(
            run_id="r_e2c_prev", kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w",
            meta={"output_mode": "preview"},
        )
        attempt = self.repo.get_attempt(_run_id("r_e2c_prev"))
        self.assertEqual(attempt.mode, "preview")

    def test_original_request_creates_original_mode_attempt(self):
        self.writer.record_run(
            run_id="r_e2c_orig", kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w",
            meta={"output_mode": "original"},
        )
        attempt = self.repo.get_attempt(_run_id("r_e2c_orig"))
        self.assertEqual(attempt.mode, "original")

    def test_legacy_missing_semantic_mode_defaults_safely(self):
        self.writer.record_run(
            run_id="r_e2c_legacy", kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w", meta={"workflow_id": "wf"},
        )
        attempt = self.repo.get_attempt(_run_id("r_e2c_legacy"))
        self.assertEqual(attempt.mode, "original")
        self.assertEqual(semantic_output_mode(None), "original")
        self.assertEqual(semantic_output_mode({"output_mode": "webp"}), "original")

    def test_update_run_fallback_attempt_uses_semantic_mode(self):
        # update_run's fallback add_attempt fires when the generation exists
        # but the attempt row does not (e.g. a lost record_run attempt insert).
        generation_id = _gen_id("r_e2c_fb")
        self.repo.create_generation(generation_id=generation_id)
        self.writer.update_run(
            "r_e2c_fb", status="running",
            meta={"output_mode": "preview"},
        )
        attempt = self.repo.get_attempt(_run_id("r_e2c_fb"))
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.mode, "preview")

    def test_experiment_cell_attempt_uses_semantic_mode(self):
        result = self.writer.mirror_cell_terminal(
            "exp_e2c", cell_key="cell_a", attempt_id="att_e2c_1",
            status="completed", meta={"output_mode": "preview"},
        )
        detail = self.repo.get_generation(result["generation_id"])
        self.assertEqual(len(detail.attempts), 1)
        self.assertEqual(detail.attempts[0].mode, "preview")


# â”€â”€ 4-8: Asset type + logical key handoff â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class AssetTypeHandoffTests(_WriterCase):
    def _descriptor_success(self, run_id: str, meta: dict) -> dict:
        self.writer.record_run(
            run_id=run_id, kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w", meta=dict(meta),
        )
        self.writer.update_run(
            run_id, status="completed", completed_at=_LATER, meta=dict(meta),
        )
        return self.repo.get_generation(_gen_id(run_id))

    def test_preview_producer_result_creates_preview_asset(self):
        file = self._producer_file("preview_src.webp", _webp_bytes())
        record = self._record(
            "ast_e2c_preview", file, variant="preview", mime_type="image/webp",
        )
        self._resolver(record)
        detail = self._descriptor_success("r_e2c_p1", {
            "output_mode": "preview",
            "primary_asset_id": "ast_e2c_preview",
        })
        previews = [a for a in detail.assets if a.type == "preview"]
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertEqual(len(previews), 1)
        self.assertEqual(originals, [])
        self.assertEqual(previews[0].asset_id, "ast_e2c_preview")
        self.assertEqual(previews[0].format, "webp")
        self.assertEqual(detail.generation.featured_asset_id, previews[0].asset_id)

    def test_original_producer_result_creates_original_asset(self):
        file = self._producer_file("orig_src.png")
        record = self._record("ast_e2c_orig1", file, variant="original")
        self._resolver(record)
        detail = self._descriptor_success("r_e2c_o1", {
            "output_mode": "original",
            "primary_asset_id": "ast_e2c_orig1",
        })
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertEqual(len(originals), 1)
        self.assertEqual([a for a in detail.assets if a.type == "preview"], [])

    def test_webp_original_remains_original(self):
        # An explicitly Original WebP must never be classified as Preview:
        # extension/codec/MIME never select the History asset type.
        file = self._producer_file("explicit_orig.webp", _webp_bytes())
        record = self._record(
            "ast_e2c_worig", file, variant="original", mime_type="image/webp",
        )
        self._resolver(record)
        detail = self._descriptor_success("r_e2c_wo", {
            "output_mode": "original",
            "primary_asset_id": "ast_e2c_worig",
        })
        originals = [a for a in detail.assets if a.type == "original"]
        self.assertEqual(len(originals), 1)
        self.assertEqual(originals[0].format, "webp")
        self.assertEqual([a for a in detail.assets if a.type == "preview"], [])

    def test_unknown_variant_stays_backward_compatible_original(self):
        file = self._producer_file("main_src.png")
        record = self._record("ast_e2c_main", file, variant="main")
        self._resolver(record)
        detail = self._descriptor_success("r_e2c_main", {
            "primary_asset_id": "ast_e2c_main",
        })
        self.assertEqual(len(
            [a for a in detail.assets if a.type == "original"]
        ), 1)

    def test_logical_output_key_persists_unchanged(self):
        file = self._producer_file("keyed.png")
        explicit = "node:9:slot:b_images:item:3"
        record = self._record(
            "ast_e2c_keyed", file, variant="preview",
            logical_output_key=explicit,
        )
        self._resolver(record)
        detail = self._descriptor_success("r_e2c_key", {
            "output_mode": "preview",
            "primary_asset_id": "ast_e2c_keyed",
        })
        self.assertEqual(detail.assets[0].logical_output_key, explicit)

    def test_component_metadata_derives_exact_e1b_key(self):
        file = self._producer_file("components.png")
        record = self._record(
            "ast_e2c_comp", file, variant="preview",
            node_id="6", output_key="images", output_index=2,
        )
        self.assertNotIn("logical_output_key", record)
        self._resolver(record)
        detail = self._descriptor_success("r_e2c_comp", {
            "output_mode": "preview",
            "primary_asset_id": "ast_e2c_comp",
        })
        expected = build_logical_output_key("6", "images", 2)
        self.assertEqual(expected, "node:6:slot:images:item:2")
        self.assertEqual(detail.assets[0].logical_output_key, expected)

    def test_path_attached_preview_run_attaches_preview_not_original(self):
        file = self._producer_file("materialized.webp", _webp_bytes())
        detail = self._descriptor_success("r_e2c_path", {
            "output_mode": "preview",
            "output_paths": [file],
        })
        previews = [a for a in detail.assets if a.type == "preview"]
        self.assertEqual(len(previews), 1)
        self.assertEqual([a for a in detail.assets if a.type == "original"], [])
        # Local thumbnail derivative still generated alongside the preview.
        thumbs = [a for a in detail.assets if a.type == "thumbnail"]
        self.assertEqual(len(thumbs), 1)
        self.assertEqual(thumbs[0].logical_output_key, previews[0].logical_output_key)


# â”€â”€ 9-13, 17-19: Multi-asset producer handoff â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class MultiAssetHandoffTests(_WriterCase):
    def _run_preview_plus_thumbnail(
        self, run_id: str, *, mode: str, primary_variant: str,
    ) -> tuple[dict, dict]:
        primary_file = self._producer_file(
            f"{run_id}_primary.webp" if mode == "preview" else f"{run_id}_primary.png",
            _webp_bytes() if mode == "preview" else None,
        )
        thumb_file = self._producer_file(f"{run_id}_thumb.webp", _thumb_webp_bytes())
        key = "node:6:slot:images:item:0"
        primary = self._record(
            f"ast_{run_id}_p", primary_file, variant=primary_variant,
            mime_type="image/webp" if mode == "preview" else "image/png",
            logical_output_key=key,
        )
        thumb = self._record(
            f"ast_{run_id}_t", thumb_file, variant="thumbnail",
            mime_type="image/webp", logical_output_key=key,
            node_id="6", output_key="images", output_index=0,
            parent_asset_id=f"ast_{run_id}_p",
        )
        self._resolver(primary, thumb)
        meta = {
            "output_mode": mode,
            "primary_asset_id": primary["asset_id"],
            "derivative_asset_ids": [thumb["asset_id"]],
        }
        self.writer.record_run(
            run_id=run_id, kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w", meta=dict(meta),
        )
        self.writer.update_run(
            run_id, status="completed", completed_at=_LATER, meta=dict(meta),
        )
        return self.repo.get_generation(_gen_id(run_id)), {"key": key}

    def test_preview_and_thumbnail_share_one_logical_key(self):
        detail, ctx = self._run_preview_plus_thumbnail(
            "r_e2c_pt", mode="preview", primary_variant="preview",
        )
        previews = [a for a in detail.assets if a.type == "preview"]
        thumbs = [a for a in detail.assets if a.type == "thumbnail"]
        self.assertEqual(len(previews), 1)
        self.assertEqual(len(thumbs), 1)
        self.assertEqual(previews[0].logical_output_key, ctx["key"])
        self.assertEqual(thumbs[0].logical_output_key, previews[0].logical_output_key)

    def test_original_and_thumbnail_share_one_logical_key(self):
        detail, ctx = self._run_preview_plus_thumbnail(
            "r_e2c_ot", mode="original", primary_variant="original",
        )
        originals = [a for a in detail.assets if a.type == "original"]
        thumbs = [a for a in detail.assets if a.type == "thumbnail"]
        self.assertEqual(len(originals), 1)
        self.assertEqual(len(thumbs), 1)
        self.assertEqual(originals[0].logical_output_key, ctx["key"])
        self.assertEqual(thumbs[0].logical_output_key, originals[0].logical_output_key)

    def test_thumbnail_is_thumbnail_asset_type(self):
        detail, _ = self._run_preview_plus_thumbnail(
            "r_e2c_tt", mode="preview", primary_variant="preview",
        )
        thumbs = [a for a in detail.assets if a.type == "thumbnail"]
        self.assertEqual(len(thumbs), 1)
        self.assertEqual(thumbs[0].metadata.get("variant"), "thumbnail")
        self.assertEqual(
            thumbs[0].metadata.get("parent_asset_id"), "ast_r_e2c_tt_p"
        )

    def test_featured_is_required_primary_not_derivative(self):
        detail, _ = self._run_preview_plus_thumbnail(
            "r_e2c_feat", mode="preview", primary_variant="preview",
        )
        self.assertEqual(
            detail.generation.featured_asset_id,
            [a for a in detail.assets if a.type == "preview"][0].asset_id,
        )

    def test_descriptor_variant_thumbnail_in_meta_is_adopted(self):
        # Experiment forwarding shape: repo.record_result forwards only
        # whitelisted keys, so derivatives ride inside asset_descriptors.
        primary_file = self._producer_file("exp_primary.webp", _webp_bytes())
        thumb_file = self._producer_file("exp_thumb.webp", _thumb_webp_bytes())
        key = "node:7:slot:images:item:0"
        primary = self._record(
            "ast_exp_p", primary_file, variant="preview",
            mime_type="image/webp", logical_output_key=key,
        )
        thumb = self._record(
            "ast_exp_t", thumb_file, variant="thumbnail",
            mime_type="image/webp", logical_output_key=key,
            parent_asset_id="ast_exp_p",
        )
        self._resolver(primary, thumb)
        gen = _gen_id("gen_exp_e2c")
        self.repo.create_generation(generation_id=gen)
        self.repo.add_attempt(gen, run_id="run_exp_e2c", mode="preview")
        ok = self.writer.attach_result_assets(
            gen,
            "run_exp_e2c",
            primary_asset_id="ast_exp_p",
            meta={
                "output_mode": "preview",
                "asset_descriptors": [
                    {
                        "asset_id": "ast_exp_p", "variant": "preview",
                        "logical_output_key": key, "codec": "webp",
                        "quality": 70, "output_codec_ms": 12.5,
                        "node_id": "7", "output_key": "images",
                        "output_index": 0,
                    },
                    {
                        "asset_id": "ast_exp_t", "variant": "thumbnail",
                        "logical_output_key": key, "codec": "webp",
                        "quality": 75, "output_codec_ms": 2.0,
                        "node_id": "7", "output_key": "images",
                        "output_index": 0,
                        "parent_identity": "sha256:abc",
                    },
                ],
            },
        )
        self.assertTrue(ok)
        detail = self.repo.get_generation(gen)
        by_type = {a.type: a for a in detail.assets}
        self.assertEqual(sorted(by_type), ["preview", "thumbnail"])
        self.assertEqual(by_type["thumbnail"].logical_output_key, key)
        self.assertEqual(by_type["preview"].logical_output_key, key)
        # Descriptor codec diagnostics retained through the handoff (req 8).
        self.assertEqual(by_type["preview"].metadata.get("codec"), "webp")
        self.assertEqual(by_type["preview"].metadata.get("quality"), 70)
        self.assertEqual(
            by_type["preview"].metadata.get("output_codec_ms"), 12.5
        )
        self.assertEqual(
            by_type["thumbnail"].metadata.get("parent_asset_id"), "ast_exp_p"
        )

    def test_attach_result_assets_primary_plus_derivative(self):
        primary_file = self._producer_file("cell_primary.webp", _webp_bytes())
        thumb_file = self._producer_file("cell_thumb.webp", _thumb_webp_bytes())
        key = "node:7:slot:images:item:0"
        primary = self._record(
            "ast_cell_p", primary_file, variant="preview",
            mime_type="image/webp", logical_output_key=key,
        )
        thumb = self._record(
            "ast_cell_t", thumb_file, variant="thumbnail",
            mime_type="image/webp", logical_output_key=key,
            parent_asset_id="ast_cell_p",
        )
        self._resolver(primary, thumb)
        gen = _gen_id("gen_cell_e2c")
        self.repo.create_generation(generation_id=gen)
        self.repo.add_attempt(gen, run_id="run_cell_e2c", mode="preview")
        ok = self.writer.attach_result_assets(
            gen,
            "run_cell_e2c",
            primary_asset_id="ast_cell_p",
            meta={
                "output_mode": "preview",
                "derivative_asset_ids": ["ast_cell_t"],
                "logical_output_key": key,
            },
        )
        self.assertTrue(ok)
        detail = self.repo.get_generation(gen)
        types = sorted(a.type for a in detail.assets)
        self.assertEqual(types, ["preview", "thumbnail"])
        by_type = {a.type: a for a in detail.assets}
        self.assertEqual(by_type["thumbnail"].logical_output_key, key)
        self.assertEqual(by_type["preview"].logical_output_key, key)

    def test_old_single_descriptor_result_still_works(self):
        file = self._producer_file("legacy_single.png")
        record = self._record("ast_legacy_single", file, variant="main")
        self._resolver(record)
        meta = {"primary_asset_id": "ast_legacy_single"}
        self.writer.record_run(
            run_id="r_e2c_legacy_single", kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w", meta=dict(meta),
        )
        self.writer.update_run(
            "r_e2c_legacy_single", status="completed", completed_at=_LATER,
            meta=dict(meta),
        )
        detail = self.repo.get_generation(_gen_id("r_e2c_legacy_single"))
        self.assertEqual(len(detail.assets), 1)
        self.assertEqual(detail.assets[0].type, "original")
        # E1B safe derivation from complete producer descriptor fields.
        self.assertEqual(
            detail.assets[0].logical_output_key,
            build_logical_output_key("6", "images", 0),
        )
        self.assertEqual(
            detail.generation.featured_asset_id, detail.assets[0].asset_id
        )

    def test_remote_modal_reference_derivative_remains_valid(self):
        key = "node:6:slot:images:item:0"
        thumb_record = {
            "asset_id": "ast_modal_thumb",
            "path": "modal://ws_e2c||output_assets/thumbdigest.webp",
            "mime_type": "image/webp",
            "content_hash": "a" * 64,
            "width": 128,
            "height": 256,
            "byte_size": 900,
            "variant": "thumbnail",
            "node_id": "6",
            "output_key": "images",
            "output_index": 0,
            "parent_asset_id": "ast_modal_primary",
        }
        self._resolver(thumb_record)
        gen = _gen_id("gen_modal_thumb")
        self.repo.create_generation(generation_id=gen)
        self.repo.add_attempt(gen, run_id="run_modal_thumb", mode="preview")
        attached = self.writer.attach_result_assets(
            gen,
            "run_modal_thumb",
            meta={
                "output_mode": "preview",
                "derivative_asset_ids": ["ast_modal_thumb"],
                "logical_output_key": key,
            },
        )
        # Derivative alone is NOT a required association (graceful policy).
        self.assertFalse(attached)
        detail = self.repo.get_generation(gen)
        thumbs = [a for a in detail.assets if a.type == "thumbnail"]
        self.assertEqual(len(thumbs), 1)
        self.assertEqual(
            thumbs[0].managed_path,
            "modal://ws_e2c||output_assets/thumbdigest.webp",
        )
        self.assertEqual(thumbs[0].sha256, "a" * 64)
        self.assertEqual(thumbs[0].logical_output_key, key)

    def test_derivative_adoption_failure_is_non_fatal(self):
        primary_file = self._producer_file("nonfatal_primary.webp", _webp_bytes())
        primary = self._record(
            "ast_nonfatal_p", primary_file, variant="preview",
            logical_output_key="node:6:slot:images:item:0",
        )
        self._resolver(primary)  # derivative id intentionally unresolvable
        meta = {
            "output_mode": "preview",
            "primary_asset_id": "ast_nonfatal_p",
            "derivative_asset_ids": ["ast_missing_thumb"],
        }
        self.writer.record_run(
            run_id="r_e2c_nonfatal", kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w", meta=dict(meta),
        )
        self.writer.update_run(
            "r_e2c_nonfatal", status="completed", completed_at=_LATER,
            meta=dict(meta),
        )
        detail = self.repo.get_generation(_gen_id("r_e2c_nonfatal"))
        self.assertEqual(detail.generation.status, "completed")
        self.assertEqual(len(
            [a for a in detail.assets if a.type == "preview"]
        ), 1)
        self.assertEqual(
            [a for a in detail.assets if a.type == "thumbnail"], []
        )


# â”€â”€ 14-17: Retention + ordering gates â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class OrderingAndRetentionTests(_WriterCase):
    def test_preview_only_execution_does_not_attach_managed_original(self):
        primary_file = self._producer_file("retention_primary.webp", _webp_bytes())
        thumb_file = self._producer_file("retention_thumb.webp", _thumb_webp_bytes())
        key = "node:6:slot:images:item:0"
        primary = self._record(
            "ast_ret_p", primary_file, variant="preview",
            mime_type="image/webp", logical_output_key=key,
        )
        thumb = self._record(
            "ast_ret_t", thumb_file, variant="thumbnail",
            mime_type="image/webp", logical_output_key=key,
        )
        self._resolver(primary, thumb)
        meta = {
            "output_mode": "preview",
            "primary_asset_id": "ast_ret_p",
            "derivative_asset_ids": ["ast_ret_t"],
        }
        self.writer.record_run(
            run_id="r_e2c_ret", kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w", meta=dict(meta),
        )
        self.writer.update_run(
            "r_e2c_ret", status="completed", completed_at=_LATER, meta=dict(meta),
        )
        detail = self.repo.get_generation(_gen_id("r_e2c_ret"))
        self.assertEqual(
            [a.type for a in detail.assets], ["preview", "thumbnail"]
        )
        self.assertEqual(
            [a for a in detail.assets if a.type == "original"], [],
            "Preview-only execution must not retain a managed Original",
        )

    def test_required_preview_association_precedes_completed(self):
        primary_file = self._producer_file("gate_preview.webp", _webp_bytes())
        primary = self._record(
            "ast_gate_p", primary_file, variant="preview",
            mime_type="image/webp",
            logical_output_key="node:6:slot:images:item:0",
        )
        self._resolver(primary)
        meta = {
            "output_mode": "preview",
            "primary_asset_id": "ast_gate_p",
        }
        self.writer.record_run(
            run_id="r_e2c_gatep", kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w", meta=dict(meta),
        )
        # The nonterminal running record already carries the REQUIRED asset.
        self.assertTrue(self.writer.generation_has_output_association("r_e2c_gatep"))
        self.writer.update_run(
            "r_e2c_gatep", status="completed", completed_at=_LATER, meta=dict(meta),
        )
        attempt = self.repo.get_attempt(_run_id("r_e2c_gatep"))
        self.assertEqual(attempt.status, "completed")
        self.assertEqual(attempt.mode, "preview")

    def test_required_original_association_precedes_completed(self):
        file = self._producer_file("gate_original.png")
        meta = {"output_paths": [file]}
        self.writer.record_run(
            run_id="r_e2c_gateo", kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w", meta=dict(meta),
        )
        self.assertTrue(self.writer.generation_has_output_association("r_e2c_gateo"))
        self.writer.update_run(
            "r_e2c_gateo", status="completed", completed_at=_LATER, meta=dict(meta),
        )
        attempt = self.repo.get_attempt(_run_id("r_e2c_gateo"))
        self.assertEqual(attempt.status, "completed")

    def test_thumbnail_failure_does_not_substitute_for_required_asset(self):
        # A Thumbnail-only association must NOT satisfy the required-output
        # gate: completed can never be justified by a derivative alone.
        thumb_file = self._producer_file("only_thumb.webp", _thumb_webp_bytes())
        thumb = self._record(
            "ast_only_t", thumb_file, variant="thumbnail",
            mime_type="image/webp",
            logical_output_key="node:6:slot:images:item:0",
        )
        self._resolver(thumb)
        meta = {"derivative_asset_ids": ["ast_only_t"]}
        self.writer.record_run(
            run_id="r_e2c_onlyt", kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w", meta=dict(meta),
        )
        self.assertFalse(
            self.writer.generation_has_output_association("r_e2c_onlyt"),
            "Thumbnail alone must never satisfy the required-output gate",
        )

    def test_zero_output_generation_fails_the_gate(self):
        self.writer.record_run(
            run_id="r_e2c_zero", kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w", meta={},
        )
        self.assertFalse(self.writer.generation_has_output_association("r_e2c_zero"))


# â”€â”€ Descriptor contract (primary + derivative list) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class DescriptorContractTests(unittest.TestCase):
    def _attempt_with_thumbnail(self) -> Attempt:
        item = OutputItem(
            node_id="6",
            output_key="images",
            filename="production_abc_6_0.webp",
            raw_bytes=b"primary-bytes",
            content_sha256="primdigest",
            mime_type="image/webp",
            file_ext=".webp",
            width=1088,
            height=1920,
            output_index=0,
            format="webp_lossy",
            conversion_meta=ConversionMeta(
                format="webp_lossy",
                mime_type="image/webp",
                file_ext=".webp",
                raw_bytes=13,
                hash_of_raw="primdigest",
                codec="webp",
                quality=70,
                output_codec_ms=42.0,
                encoded_bytes=13,
                source_bytes=24,
            ),
            thumbnail_bytes=b"thumb-bytes",
            thumbnail_mime_type="image/webp",
            thumbnail_file_ext=".webp",
            thumbnail_width=144,
            thumbnail_height=256,
            thumbnail_codec_ms=1.75,
            thumbnail_quality=75,
            thumbnail_path="output_assets/thumbdigest.webp",
        )
        return Attempt(strategy="direct_output_sink", success=True, items=(item,))

    def test_result_exposes_primary_plus_derivative_descriptors(self):
        result = attempt_to_descriptor_result(
            self._attempt_with_thumbnail(),
            output_mode="preview",
            variant="preview",
        )
        primaries = [
            d for d in result["asset_descriptors"] if d["variant"] == "preview"
        ]
        derivatives = result["derivative_descriptors"]
        self.assertEqual(len(primaries), 1)
        self.assertEqual(len(derivatives), 1)
        self.assertEqual(len(result["images"]), 1, "thumbnail is not an output image")
        thumb = derivatives[0]
        self.assertEqual(thumb["variant"], "thumbnail")
        self.assertEqual(thumb["output_mode"], "preview")
        self.assertEqual(
            thumb["logical_output_key"],
            primaries[0]["logical_output_key"],
        )
        self.assertEqual(thumb["logical_output_key"], "node:6:slot:images:item:0")
        self.assertEqual(thumb["parent_asset_id"], "primdigest")
        self.assertEqual(thumb["parent_identity"], "sha256:primdigest")
        self.assertEqual(thumb["codec"], "webp")
        self.assertEqual(thumb["quality"], 75)
        self.assertEqual(thumb["output_codec_ms"], 1.75)
        self.assertEqual(thumb["width"], 144)
        self.assertEqual(thumb["height"], 256)
        self.assertEqual(thumb["byte_count"], len(b"thumb-bytes"))
        self.assertEqual(thumb["backend_path"], "output_assets/thumbdigest.webp")
        self.assertTrue(thumb["filename"].endswith("_thumb.webp"))
        # Derivatives ride in asset_descriptors so existing lease-registration
        # and Experiment result-forwarding seams transport them unchanged.
        self.assertIn(thumb, result["asset_descriptors"])

    def test_result_without_thumbnail_keeps_single_descriptor_shape(self):
        item = OutputItem(
            node_id="6",
            output_key="images",
            filename="plain.png",
            raw_bytes=b"bytes",
            mime_type="image/png",
            file_ext=".png",
            output_index=0,
        )
        result = attempt_to_descriptor_result(
            Attempt(strategy="direct_output_sink", success=True, items=(item,)),
            output_mode="original",
        )
        self.assertEqual(result["derivative_descriptors"], [])
        self.assertEqual(len(result["asset_descriptors"]), 1)
        self.assertEqual(len(result["images"]), 1)


# â”€â”€ Producer-side Thumbnail encoding (comfyapp; torch-gated) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class ProducerThumbnailEncodingTests(unittest.TestCase):
    def test_encode_thumbnail_batch_aspect_and_decodability(self):
        pytest = __import__("pytest")
        comfyapp = pytest.importorskip("comfyapp")
        torch = pytest.importorskip("torch")
        from PIL import Image

        images = torch.randint(0, 255, (2, 512, 256, 3), dtype=torch.uint8)
        thumbnails = comfyapp.encode_thumbnail_batch(images)
        self.assertEqual(len(thumbnails), 2)
        for index, thumb in enumerate(thumbnails):
            self.assertIsNotNone(thumb)
            self.assertEqual(thumb["mime_type"], "image/webp")
            self.assertEqual(thumb["file_ext"], ".webp")
            self.assertLessEqual(max(thumb["width"], thumb["height"]), 256)
            # Aspect preserved: source H:W is 2:1.
            self.assertAlmostEqual(
                thumb["height"] / thumb["width"], 2.0, places=5
            )
            with Image.open(io.BytesIO(thumb["bytes"])) as image:
                self.assertEqual(image.format, "WEBP")
                self.assertEqual(image.size, (thumb["width"], thumb["height"]))
            self.assertGreaterEqual(thumb["output_codec_ms"], 0.0)
            self.assertEqual(thumb["quality"], 75)

    def test_encode_thumbnail_batch_failure_is_graceful_per_item(self):
        pytest = __import__("pytest")
        comfyapp = pytest.importorskip("comfyapp")
        torch = pytest.importorskip("torch")
        # A non-image-shaped slice fails per item and encodes as None.
        bad = torch.zeros((1, 8), dtype=torch.uint8)
        thumbnails = comfyapp.encode_thumbnail_batch(bad)
        self.assertEqual(len(thumbnails), 1)
        self.assertIsNone(thumbnails[0])

    def test_sink_entry_attachment_helper(self):
        pytest = __import__("pytest")
        comfyapp = pytest.importorskip("comfyapp")
        entry = {"filename": "x.webp"}
        comfyapp._attach_thumbnail_to_entry(entry, None)
        self.assertNotIn("thumbnail", entry)
        comfyapp._attach_thumbnail_to_entry(entry, {"bytes": b"t"})
        self.assertEqual(entry["thumbnail"]["bytes"], b"t")


# â”€â”€ E4B regression: missing local Preview URL projection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class E4BMissingPreviewUrlRegressionTests(unittest.TestCase):
    def test_failed_original_preserves_preview_url_for_missing_local_preview(self):
        # Reproduces the E4B-reported backend failure: a structurally present
        # Preview whose local managed path does not exist must still project
        # its preview_url when a later Original attempt failed.
        from history_v2_routes import _build_outputs

        preview = Asset(
            asset_id="ast_missing_preview",
            generation_id="gen_e4b",
            type="preview",
            managed_path="/missing/e2c_preview.webp",
            filename="e2c_preview.webp",
            created_at="2026-08-17T10:00:00.000+00:00",
            run_id="run_preview",
            format="webp",
        )
        attempts = [
            RunAttempt(
                run_id="run_preview",
                generation_id="gen_e4b",
                mode="preview",
                status="completed",
                created_at="2026-08-17T10:00:00.000+00:00",
            ),
            RunAttempt(
                run_id="run_original",
                generation_id="gen_e4b",
                mode="original",
                status="failed",
                created_at="2026-08-17T10:01:00.000+00:00",
                error="OOM",
            ),
        ]
        output = _build_outputs([preview], attempts=attempts)[0]
        self.assertEqual(
            output["preview_url"],
            "/comfymodal/history-v2/assets/ast_missing_preview",
        )
        self.assertEqual(output["original_url"], "")
        self.assertTrue(output["original_failed"])


if __name__ == "__main__":
    unittest.main()
