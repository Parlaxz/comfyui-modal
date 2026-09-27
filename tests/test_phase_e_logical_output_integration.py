"""E1C deterministic production proof for logical-output grouping.

Closes the E5C "featured/variant-grouping production coverage" gap by proving
the LANDED E1B behavior against REAL production seams (not hand-constructed
route-only asset lists):

* repository writes through ``HistoryV2Repository`` (assets, attempts,
  featured pointer, modern matrix cells);
* producer adoption through ``HistoryV2ProductionWriter`` with the
  LeaseRegistry resolver seam, including the E2C primary+derivative
  descriptor handoff;
* the E3B2 Generate Original result finalization shape
  (``_META_PASSTHROUGH_KEYS`` -> ``attach_result_assets``);
* route projection exactly as the production routes build it
  (``_generation_feed_item`` / ``_cell_generation_payload`` / ``_detail_cell``
  fed from ``repo.get_generation`` / batch loaders).

Authoritative logical-output key:

    node:<node_id>:slot:<output_key>:item:<output_index>

Expected semantics under test: Preview/Thumbnail/Original variants with the
same key are ONE logical output; retry Attempts never create new logical
outputs; ``output_count`` counts logical groups; featured derivative assets
resolve through group membership; the newest usable successful Original wins;
a later failed Original retry cannot hide an earlier success.

No Modal, no deployment, no live generation, no GPU spend.
"""
from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from history_v2_models import Asset
from history_v2_repository import HistoryV2Repository
from history_v2_routes import (
    _build_generation_items,
    _cell_generation_payload,
    _detail_cell,
    _generation_feed_item,
)
from history_v2_store import HistoryV2Store
from history_v2_writer import (
    HistoryV2ProductionWriter,
    _gen_id,
    reset_writer_config,
    set_asset_resolver,
)

KEY_X = "node:9:slot:images:item:0"
KEY_ITEM0 = "node:A:slot:images:item:0"
KEY_ITEM1 = "node:A:slot:images:item:1"
KEY_NODE_B = "node:B:slot:images:item:0"


def _past(seconds_ago: float) -> str:
    """Deterministic ISO timestamp strictly before any natural-now write."""
    moment = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return moment.isoformat(timespec="milliseconds")


def _errors_like_detail_route(attempts) -> list[dict[str, str]]:
    """Mirror the production detail-route errors projection."""
    return [
        {"code": "attempt_failed", "message": a.error}
        for a in attempts
        if a.error
    ]


class _ProductionCase(unittest.TestCase):
    """Temp-store harness over the real store/repository/writer seams."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.db_path = self.root / ".studio_history_v2" / "history_v2.db"
        self.repo = HistoryV2Repository(HistoryV2Store(self.db_path))
        self.writer = HistoryV2ProductionWriter(self.root)
        self.addCleanup(reset_writer_config)

    # ── production seams ────────────────────────────────────────────────

    def _producer_file(self, name: str, payload: bytes | None = None) -> str:
        path = self.root / name
        # Unique bytes per filename so producer content hashes never collide.
        path.write_bytes(payload if payload is not None else name.encode())
        return str(path)

    def _producer_record(
        self,
        asset_id: str,
        path: str,
        *,
        variant: str,
        mime_type: str = "image/png",
        key: str | None = KEY_X,
        node_id: str = "9",
        output_key: str = "images",
        output_index: int = 0,
        parent_asset_id: str = "",
    ) -> dict:
        record: dict = {
            "asset_id": asset_id,
            "path": path,
            "mime_type": mime_type,
            "content_hash": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "width": 64,
            "height": 32,
            "byte_size": Path(path).stat().st_size,
            "variant": variant,
            "node_id": node_id,
            "output_key": output_key,
            "output_index": output_index,
        }
        if key:
            record["logical_output_key"] = key
        if parent_asset_id:
            record["parent_asset_id"] = parent_asset_id
        return record

    def _resolver(self, *records: dict) -> None:
        # Accumulate: production flows adopt assets across several writer
        # calls, so every registered producer id stays resolvable.
        table = getattr(self, "_resolver_table", None)
        if table is None:
            table = {}
            self._resolver_table = table
        for record in records:
            table[record["asset_id"]] = record
        set_asset_resolver(lambda asset_id: table.get(asset_id))

    def _attempt(
        self,
        generation_id: str,
        run_id: str,
        mode: str,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        """Create a real Attempt row and drive it to a terminal status."""
        self.repo.add_attempt(generation_id, run_id=run_id, mode=mode)
        if status in ("completed", "failed"):
            self.repo.update_attempt_terminal(
                run_id, status=status, error=error
            )

    def _seed_asset(
        self,
        generation_id: str,
        run_id: str,
        mode: str,
        asset_type: str,
        *,
        key: str,
        created_at: str,
        data: bytes = b"seed-bytes",
        attempt_status: str = "completed",
        error: str | None = None,
        metadata: dict | None = None,
    ) -> Asset:
        """Attempt + keyed asset through the production repository write."""
        if self.repo.get_attempt(run_id) is None:
            self.repo.add_attempt(generation_id, run_id=run_id, mode=mode)
        if attempt_status in ("completed", "failed"):
            self.repo.update_attempt_terminal(
                run_id, status=attempt_status, error=error
            )
        return self.repo.attach_asset(
            generation_id,
            run_id=run_id,
            asset_type=asset_type,
            data=data,
            filename=f"{run_id}_{asset_type}.png",
            fmt="png",
            created_at=created_at,
            logical_output_key=key,
            metadata=dict(metadata or {}),
        )

    def _project(self, generation_id: str) -> dict:
        """Mirror the production generation-detail route projection."""
        detail = self.repo.get_generation(generation_id)
        assert detail is not None
        return _generation_feed_item(
            detail.generation.to_dict(),
            detail.assets,
            detail.attempts,
            snapshot=detail.request_snapshot,
        )

    def _project_feed(self, generation_ids: list[str]) -> list[dict]:
        """Mirror the production mixed-feed batch enrichment."""
        gen_dicts = [
            {
                "generation_id": gid,
                "status": "completed",
                "created_at": _past(1),
            }
            for gid in generation_ids
        ]
        return _build_generation_items(self.repo, gen_dicts)

    # ── shared production flows ─────────────────────────────────────────

    def _run_preview_with_thumbnail(self, run_id: str, key: str) -> str:
        """Preview Attempt + Preview asset + Thumbnail derivative via the
        production single-run writer flow (E2C adoption shape)."""
        preview_file = self._producer_file(f"{run_id}_preview.webp")
        thumb_file = self._producer_file(f"{run_id}_thumb.webp")
        self._resolver(
            self._producer_record(
                f"{run_id}_prev", preview_file, variant="preview",
                mime_type="image/webp", key=key,
            ),
            self._producer_record(
                f"{run_id}_thumb", thumb_file, variant="thumbnail",
                mime_type="image/webp", key=key,
                parent_asset_id=f"{run_id}_prev",
            ),
        )
        meta = {
            "output_mode": "preview",
            "primary_asset_id": f"{run_id}_prev",
            "derivative_asset_ids": [f"{run_id}_thumb"],
            "logical_output_key": key,
        }
        self.writer.record_run(
            run_id=run_id, kind="studio_run", status="running",
            prompt_id="p", workflow_hash="w", meta=dict(meta),
        )
        self.writer.update_run(run_id, status="completed", meta=dict(meta))
        return _gen_id(run_id)

    def _adopt_original(
        self, generation_id: str, run_id: str, asset_id: str, key: str
    ) -> bool:
        """Later Original Attempt on an existing Generation via the E3B2
        finalization sequence (add_attempt -> attach -> terminal)."""
        self.repo.add_attempt(generation_id, run_id=run_id, mode="original")
        ok = self.writer.attach_result_assets(
            generation_id,
            run_id,
            primary_asset_id=asset_id,
            meta={"logical_output_key": key},
        )
        self.repo.update_attempt_terminal(run_id, status="completed")
        return ok


# ── 1+2: producer-variant grouping and retry grouping ────────────────────


class ProducerVariantGroupingTests(_ProductionCase):
    def test_preview_thumbnail_original_are_one_logical_output(self):
        original_file = self._producer_file("variant_original.png")
        self._resolver(
            self._producer_record("ast_var_orig", original_file, variant="main"),
        )
        gen = self._run_preview_with_thumbnail("run_e1c_variants", KEY_X)

        self.assertTrue(
            self._adopt_original(gen, "run_e1c_orig", "ast_var_orig", KEY_X)
        )

        detail = self.repo.get_generation(gen)
        assert detail is not None
        self.assertEqual(len(detail.attempts), 2)
        by_type = {a.type: a for a in detail.assets}
        self.assertEqual(sorted(by_type), ["original", "preview", "thumbnail"])
        for asset in detail.assets:
            self.assertEqual(asset.logical_output_key, KEY_X)

        item = self._project(gen)
        self.assertEqual(item["output_count"], 1)
        self.assertEqual(len(item["outputs"]), 1)
        output = item["outputs"][0]
        self.assertTrue(output["thumb_url"].endswith("/run_e1c_variants_thumb"))
        self.assertTrue(output["preview_url"].endswith("/run_e1c_variants_prev"))
        self.assertTrue(output["original_url"].endswith("/ast_var_orig"))
        self.assertFalse(output["original_failed"])

    def test_retry_grouping_failed_then_successful_original(self):
        gen = self._run_preview_with_thumbnail("run_e1c_retry", KEY_X)

        # Failed Original Attempt: retained, produces no asset.
        self._attempt(gen, "run_e1c_fail", "original", "failed", error="OOM")

        mid = self._project(gen)
        self.assertEqual(mid["output_count"], 1)
        self.assertTrue(mid["outputs"][0]["original_url"] == "")
        self.assertTrue(mid["outputs"][0]["original_failed"])
        self.assertNotEqual(mid["outputs"][0]["preview_url"], "")

        # Successful Original retry on the SAME Generation.
        retry_file = self._producer_file("retry_original.png")
        self._resolver(
            self._producer_record("ast_retry_orig", retry_file, variant="main"),
        )
        self.assertTrue(
            self._adopt_original(gen, "run_e1c_retry_ok", "ast_retry_orig", KEY_X)
        )

        detail = self.repo.get_generation(gen)
        assert detail is not None
        self.assertEqual(len(detail.attempts), 3)
        self.assertEqual(
            {a.generation_id for a in detail.attempts}, {gen},
            "all three Attempts belong to one Generation",
        )
        modes = sorted(a.mode for a in detail.attempts)
        self.assertEqual(modes, ["original", "original", "preview"])

        item = self._project(gen)
        self.assertEqual(item["output_count"], 1)
        self.assertEqual(len(item["outputs"]), 1)
        output = item["outputs"][0]
        self.assertTrue(
            output["original_url"].endswith("/ast_retry_orig"),
            "retry Original becomes the preferred Original",
        )
        self.assertFalse(output["original_failed"])
        self.assertNotEqual(output["preview_url"], "")
        self.assertNotEqual(output["thumb_url"], "")

    def test_later_failed_rerender_retains_earlier_winner(self):
        original_file = self._producer_file("first_original.png")
        self._resolver(
            self._producer_record("ast_first_orig", original_file, variant="main"),
        )
        gen = self._run_preview_with_thumbnail("run_e1c_rerender", KEY_X)
        self.assertTrue(
            self._adopt_original(gen, "run_e1c_orig1", "ast_first_orig", KEY_X)
        )

        # Later failed rerender/retry Attempt appends no asset.
        self._attempt(
            gen, "run_e1c_rerender_fail", "original", "failed",
            error="rerender exploded",
        )

        item = self._project(gen)
        self.assertEqual(item["output_count"], 1)
        self.assertEqual(len(item["outputs"]), 1)
        output = item["outputs"][0]
        self.assertTrue(
            output["original_url"].endswith("/ast_first_orig"),
            "prior usable Original remains available",
        )
        self.assertFalse(
            output["original_failed"],
            "failure must not hide the retained usable Original",
        )

        detail = self.repo.get_generation(gen)
        assert detail is not None
        failed = [a for a in detail.attempts if a.status == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].error, "rerender exploded")
        self.assertIn(
            {"code": "attempt_failed", "message": "rerender exploded"},
            _errors_like_detail_route(detail.attempts),
        )

    def test_two_successful_originals_newest_wins_via_writer(self):
        first_file = self._producer_file("winner_old.png")
        second_file = self._producer_file("winner_new.png")
        self._resolver(
            self._producer_record("ast_win_old", first_file, variant="main"),
            self._producer_record("ast_win_new", second_file, variant="main"),
        )
        gen = self._run_preview_with_thumbnail("run_e1c_winner", KEY_X)
        self.assertTrue(
            self._adopt_original(gen, "run_e1c_w1", "ast_win_old", KEY_X)
        )
        self.assertTrue(
            self._adopt_original(gen, "run_e1c_w2", "ast_win_new", KEY_X)
        )

        item = self._project(gen)
        self.assertEqual(item["output_count"], 1)
        self.assertTrue(item["outputs"][0]["original_url"].endswith("/ast_win_new"))
        self.assertFalse(item["outputs"][0]["original_failed"])


# ── 5: E2C multi-asset descriptor handoff ────────────────────────────────


class E2CDescriptorHandoffTests(_ProductionCase):
    def test_primary_plus_derivative_descriptors_become_one_group(self):
        """The repo.record_result forwarding shape: derivatives ride inside
        asset_descriptors; the writer consumes them into Preview + Thumbnail
        Assets sharing ONE logical key and ONE projected output group."""
        primary_file = self._producer_file("handoff_primary.webp")
        thumb_file = self._producer_file("handoff_thumb.webp")
        self._resolver(
            self._producer_record(
                "ast_ho_p", primary_file, variant="preview",
                mime_type="image/webp", key=KEY_X,
            ),
            self._producer_record(
                "ast_ho_t", thumb_file, variant="thumbnail",
                mime_type="image/webp", key=KEY_X,
                parent_asset_id="ast_ho_p",
            ),
        )
        gen = "gen_e1c_handoff"
        self.repo.create_generation(generation_id=gen)
        self._attempt(gen, "run_e1c_ho", "preview", "completed")

        ok = self.writer.attach_result_assets(
            gen,
            "run_e1c_ho",
            primary_asset_id="ast_ho_p",
            meta={
                "output_mode": "preview",
                "asset_descriptors": [
                    {
                        "asset_id": "ast_ho_p", "variant": "preview",
                        "logical_output_key": KEY_X,
                        "node_id": "9", "output_key": "images",
                        "output_index": 0,
                    },
                    {
                        "asset_id": "ast_ho_t", "variant": "thumbnail",
                        "logical_output_key": KEY_X,
                        "node_id": "9", "output_key": "images",
                        "output_index": 0,
                        "parent_identity": "sha256:abc",
                    },
                ],
            },
        )
        self.assertTrue(ok)

        detail = self.repo.get_generation(gen)
        assert detail is not None
        by_type = {a.type: a for a in detail.assets}
        self.assertEqual(sorted(by_type), ["preview", "thumbnail"])
        self.assertEqual(by_type["preview"].logical_output_key, KEY_X)
        self.assertEqual(by_type["thumbnail"].logical_output_key, KEY_X)

        item = self._project(gen)
        self.assertEqual(item["output_count"], 1)
        self.assertEqual(len(item["outputs"]), 1)
        self.assertTrue(item["outputs"][0]["preview_url"].endswith("/ast_ho_p"))
        self.assertTrue(item["outputs"][0]["thumb_url"].endswith("/ast_ho_t"))


# ── 6: E3B2-shaped Generate Original result ──────────────────────────────


class E3B2OriginalResultTests(_ProductionCase):
    def test_e3b2_shaped_original_joins_existing_logical_output(self):
        from history_v2_replay import _META_PASSTHROUGH_KEYS

        gen = self._run_preview_with_thumbnail("run_e1c_e3b2", KEY_X)

        # Older successful Original (earlier Attempt, deterministic past time).
        older_file = self._producer_file("e3b2_older.png")
        self._resolver(
            self._producer_record("ast_e3b2_old", older_file, variant="main"),
        )
        self.assertTrue(
            self._adopt_original(gen, "run_e1c_e3b2_old", "ast_e3b2_old", KEY_X)
        )
        before = self._project(gen)
        self.assertEqual(before["output_count"], 1)
        self.assertTrue(before["outputs"][0]["original_url"].endswith("/ast_e3b2_old"))

        # Newer Original generated by a LATER Attempt using the exact E3B2
        # result shape (descriptor result -> passthrough meta -> writer).
        newer_file = self._producer_file("e3b2_newer.png")
        self._resolver(
            self._producer_record("ast_e3b2_new", newer_file, variant="main"),
        )
        attempt_id = "run_e1c_e3b2_new"
        self.repo.add_attempt(gen, run_id=attempt_id, mode="original")
        self.repo.claim_attempt(attempt_id)
        result = {
            "status": "ok",
            "primary_asset_id": "ast_e3b2_new",
            "logical_output_key": KEY_X,
            "asset_descriptors": [
                {
                    "asset_id": "ast_e3b2_new",
                    "variant": "main",
                    "path": newer_file,
                    "mime_type": "image/png",
                    "content_hash": hashlib.sha256(
                        Path(newer_file).read_bytes()
                    ).hexdigest(),
                    "node_id": "9",
                    "output_key": "images",
                    "output_index": 0,
                    "logical_output_key": KEY_X,
                },
            ],
        }
        meta = {
            key: result[key] for key in _META_PASSTHROUGH_KEYS if key in result
        }
        attached = self.writer.attach_result_assets(
            gen, attempt_id,
            primary_asset_id=result["primary_asset_id"], meta=meta,
        )
        self.assertTrue(attached)
        self.repo.update_attempt_terminal(attempt_id, status="completed")

        detail = self.repo.get_generation(gen)
        assert detail is not None
        self.assertEqual(len(detail.attempts), 3)

        item = self._project(gen)
        self.assertEqual(
            item["output_count"], 1,
            "later generated Original joins the existing Preview logical output",
        )
        self.assertEqual(len(item["outputs"]), 1)
        self.assertTrue(item["outputs"][0]["original_url"].endswith("/ast_e3b2_new"))
        self.assertFalse(item["outputs"][0]["original_failed"])
        self.assertNotEqual(item["outputs"][0]["preview_url"], "")


# ── 3: featured derivative membership ────────────────────────────────────


class FeaturedDerivativeMembershipTests(_ProductionCase):
    def _seed_two_groups(self) -> tuple[str, Asset, Asset, Asset, Asset]:
        """Group A (item:0): original+thumbnail+preview. Group B (item:1):
        original only. Group A sorts first by earliest asset creation."""
        gen = "gen_e1c_featured"
        self.repo.create_generation(generation_id=gen)
        orig_a = self._seed_asset(
            gen, "run_fa_o", "original", "original",
            key=KEY_ITEM0, created_at=_past(50),
        )
        thumb_a = self._seed_asset(
            gen, "run_fa_t", "preview", "thumbnail",
            key=KEY_ITEM0, created_at=_past(49),
        )
        prev_a = self._seed_asset(
            gen, "run_fa_p", "preview", "preview",
            key=KEY_ITEM0, created_at=_past(48),
        )
        orig_b = self._seed_asset(
            gen, "run_fb_o", "original", "original",
            key=KEY_ITEM1, created_at=_past(40),
        )
        return gen, orig_a, thumb_a, prev_a, orig_b

    def test_featured_thumbnail_resolves_to_its_logical_group(self):
        gen, orig_a, thumb_a, prev_a, orig_b = self._seed_two_groups()
        self.repo.set_featured_asset(gen, thumb_a.asset_id)

        item = self._project(gen)
        self.assertEqual(item["output_count"], 2)
        self.assertEqual(
            item["featured_output_index"], 0,
            "featured Thumbnail maps to its own logical group",
        )
        self.assertEqual(item["outputs"][0]["asset_id"], orig_a.asset_id)

    def test_featured_preview_resolves_to_its_logical_group(self):
        gen, orig_a, thumb_a, prev_a, orig_b = self._seed_two_groups()
        self.repo.set_featured_asset(gen, prev_a.asset_id)

        item = self._project(gen)
        self.assertEqual(
            item["featured_output_index"], 0,
            "featured Preview maps to its own logical group",
        )

    def test_featured_older_original_resolves_and_stays_stable(self):
        gen, orig_a, thumb_a, prev_a, orig_b = self._seed_two_groups()

        self.repo.set_featured_asset(gen, orig_b.asset_id)
        self.assertEqual(
            self._project(gen)["featured_output_index"], 1,
            "featured older Original of group B resolves to index 1",
        )

        self.repo.set_featured_asset(gen, orig_a.asset_id)
        self.assertEqual(self._project(gen)["featured_output_index"], 0)

        # Attach a NEWER successful Original to group A's logical output.
        newer_a = self._seed_asset(
            gen, "run_fa_o2", "original", "original",
            key=KEY_ITEM0, created_at=_past(10),
        )

        item = self._project(gen)
        self.assertEqual(
            item["featured_output_index"], 0,
            "featured logical-output identity stays stable when a newer "
            "Original becomes the winner",
        )
        self.assertEqual(item["outputs"][0]["asset_id"], newer_a.asset_id)
        self.assertTrue(item["outputs"][0]["original_url"].endswith(f"/{newer_a.asset_id}"))
        self.assertEqual(item["output_count"], 2)


# ── 4: multiple outputs ──────────────────────────────────────────────────


class MultipleOutputsTests(_ProductionCase):
    def test_item_indexes_and_nodes_form_distinct_ordered_groups(self):
        gen = "gen_e1c_multi"
        self.repo.create_generation(generation_id=gen)
        o_item0 = self._seed_asset(
            gen, "run_m_i0", "original", "original",
            key=KEY_ITEM0, created_at=_past(60),
        )
        o_item1 = self._seed_asset(
            gen, "run_m_i1", "original", "original",
            key=KEY_ITEM1, created_at=_past(50),
        )
        # Second node case: key derived from stable descriptor METADATA
        # fields at persistence time (no explicit key passed).
        o_node_b = self._seed_asset(
            gen, "run_m_nb", "original", "original",
            key="", created_at=_past(40),
            metadata={"node_id": "B", "output_key": "images", "output_index": 0},
        )
        self.assertIsNotNone(o_node_b.logical_output_key)
        self.assertEqual(o_node_b.logical_output_key, KEY_NODE_B)

        # A Thumbnail variant must NOT inflate the group count.
        thumb_item0 = self._seed_asset(
            gen, "run_m_t0", "preview", "thumbnail",
            key=KEY_ITEM0, created_at=_past(59),
        )

        item = self._project(gen)
        self.assertEqual(
            item["output_count"], 3,
            "two item indexes plus a second node produce exactly three groups",
        )
        self.assertEqual(len(item["outputs"]), 3)
        self.assertEqual(
            [o["asset_id"] for o in item["outputs"]],
            [o_item0.asset_id, o_item1.asset_id, o_node_b.asset_id],
            "group ordering follows earliest-asset creation deterministically",
        )

        # Featured selects the intended group across the multiple outputs.
        self.repo.set_featured_asset(gen, thumb_item0.asset_id)
        self.assertEqual(self._project(gen)["featured_output_index"], 0)
        self.repo.set_featured_asset(gen, o_node_b.asset_id)
        self.assertEqual(self._project(gen)["featured_output_index"], 2)

        # The same grouping holds through the production feed batch path.
        feed_items = self._project_feed([gen])
        self.assertEqual(len(feed_items), 1)
        self.assertEqual(feed_items[0]["output_count"], 3)


# ── 7: Experiment parity ─────────────────────────────────────────────────


def _cell_spec(cell_id: str) -> dict:
    return {
        "cell_id": cell_id,
        "mode": "preview",
        "axis_values": {"seed": 1},
        "controls": {"seed": 1},
        "merged_values": {"seed": 1},
        "axis_to_control": {"seed": "seed"},
        "workflow_id": f"wf_{cell_id}",
        "workflow_version_id": "v_frozen",
        "preset_id": "p_frozen",
        "preset_name": "Preset",
        "workflow_name": f"Workflow {cell_id}",
        "plan_hash": f"h_{cell_id}",
        "workflow_hash": f"wh_{cell_id}",
        "execution_plan": {
            "workflow": {"name": f"Workflow {cell_id}"},
            "workflow_hash": f"wh_{cell_id}",
            "workflow_version_id": "v_frozen",
            "deployment_identity": {"gpu": "RTX6000"},
        },
    }


class ExperimentParityTests(_ProductionCase):
    def _matrix(self, *cell_ids: str) -> tuple:
        specs = [_cell_spec(cid) for cid in cell_ids]
        definition = {"version": 2, "contract": "modern_v2", "cells": specs}
        detail = self.repo.create_modern_matrix(
            experiment_id="exp_e1c_parity",
            name="E1C parity",
            definition=definition,
            cells=specs,
        )
        return detail, specs

    def _record_cell_result(
        self, cell, attempt_id: str, *, primary: dict, derivative: dict | None,
        key: str,
    ) -> bool:
        # Register producer identities on the LeaseRegistry resolver seam
        # exactly as a real result handoff would expose them.
        self._resolver(primary)
        if derivative is not None:
            self._resolver(derivative)
        descriptors = [dict(primary)]
        if derivative is not None:
            descriptors.append(dict(derivative))
        result = {
            "primary_asset_id": primary["asset_id"],
            "logical_output_key": key,
            "asset_descriptors": descriptors,
            "_history_output_required": True,
        }
        return self.repo.record_result(attempt_id, cell.cell_id, result)

    def _experiment_projection(self, exp_id: str):
        """Mirror the production experiment-detail route projection."""
        detail = self.repo.get_experiment(exp_id)
        assert detail is not None
        cells = detail.cells
        gen_ids = [c.generation_id for c in cells if c.generation_id]
        assets_by_gen: dict[str, list[Asset]] = {}
        for asset in self.repo.get_assets_for_generations(gen_ids):
            assets_by_gen.setdefault(asset.generation_id, []).append(asset)
        attempts_by_cell = {}
        for attempt in self.repo.get_attempts_for_cells(
            [c.cell_id for c in cells]
        ):
            if attempt.cell_id is not None:
                attempts_by_cell.setdefault(attempt.cell_id, []).append(attempt)
        gen_detail_by_id = {}
        for gid in set(gen_ids):
            gdetail = self.repo.get_generation(gid)
            if gdetail is not None:
                gen_detail_by_id[gid] = gdetail
        fav_by_gen = {
            gid: bool(gd.generation.favorite)
            for gid, gd in gen_detail_by_id.items()
        }
        return [
            _detail_cell(
                cell,
                assets_by_gen,
                attempts_by_cell,
                fav_by_gen,
                None,
                generation_payload=(
                    _cell_generation_payload(gen_detail_by_id[cell.generation_id])
                    if cell.generation_id in gen_detail_by_id
                    else None
                ),
            )
            for cell in cells
        ]

    def test_experiment_cell_matches_generation_projection(self):
        detail, _specs = self._matrix("ok_cell")
        cell = detail.cells[0]
        gen = cell.generation_id
        assert gen is not None
        run_id = cell.attempt_ids[0]

        claimed = self.repo.claim_attempt(run_id)
        self.assertEqual(claimed.outcome, "claimed")

        preview_file = self._producer_file("cell_preview.webp")
        thumb_file = self._producer_file("cell_thumb.webp")
        original_file = self._producer_file("cell_original.png")
        self.assertTrue(self._record_cell_result(
            cell, run_id,
            primary=self._producer_record(
                "ast_cell_prev", preview_file, variant="preview",
                mime_type="image/webp", key=KEY_X,
            ),
            derivative=self._producer_record(
                "ast_cell_thumb", thumb_file, variant="thumbnail",
                mime_type="image/webp", key=KEY_X,
                parent_asset_id="ast_cell_prev",
            ),
            key=KEY_X,
        ))
        self.assertTrue(self.repo.record_terminal(run_id, cell.cell_id, "completed"))

        # Generate Original on the SAME cell Generation (the real E3B2
        # transactional decision: preview-only -> new queued Original
        # Attempt appended to the cell).
        outcome = self.repo.claim_or_reuse_original_attempt(gen)
        assert outcome is not None and outcome.attempt is not None
        self.assertEqual(outcome.outcome, "created")
        retry_run = outcome.attempt.run_id
        claimed = self.repo.claim_attempt(retry_run)
        self.assertEqual(claimed.outcome, "claimed")
        self.assertTrue(self._record_cell_result(
            cell, retry_run,
            primary=self._producer_record(
                "ast_cell_orig", original_file, variant="main", key=KEY_X,
            ),
            derivative=None,
            key=KEY_X,
        ))
        self.assertTrue(self.repo.record_terminal(retry_run, cell.cell_id, "completed"))

        gdetail = self.repo.get_generation(gen)
        assert gdetail is not None
        self.assertEqual(
            len(gdetail.attempts), 2,
            "initial Preview Attempt + generated Original Attempt",
        )

        gen_item = self._project(gen)
        self.assertEqual(gen_item["output_count"], 1)
        self.assertEqual(len(gen_item["outputs"]), 1)
        gen_out = gen_item["outputs"][0]
        self.assertTrue(gen_out["original_url"].endswith("/ast_cell_orig"))
        self.assertFalse(gen_out["original_failed"])

        (cell_detail,) = self._experiment_projection("exp_e1c_parity")
        self.assertEqual(cell_detail["generation_id"], gen)
        self.assertEqual(
            cell_detail["thumb_url"], gen_out["thumb_url"],
            "Experiment cell agrees with Generation projection on Thumbnail",
        )
        self.assertEqual(
            cell_detail["preview_url"], gen_out["preview_url"],
            "Experiment cell agrees with Generation projection on Preview",
        )
        self.assertEqual(
            cell_detail["original_url"], gen_out["original_url"],
            "Experiment cell agrees with Generation projection on Original",
        )
        self.assertEqual(
            cell_detail["original_failed"], gen_out["original_failed"],
        )

        payload = cell_detail["generation"]
        assert payload is not None
        self.assertEqual(payload["outputs"], gen_item["outputs"])
        self.assertEqual(
            payload["featured_output_index"],
            gen_item["featured_output_index"],
        )
        self.assertEqual(len(payload["attempts"]), 2)

    def test_experiment_failure_parity_preview_retained(self):
        detail, _specs = self._matrix("fail_cell")
        cell = detail.cells[0]
        gen = cell.generation_id
        assert gen is not None
        run_id = cell.attempt_ids[0]

        self.repo.claim_attempt(run_id)
        preview_file = self._producer_file("failcell_preview.webp")
        self.assertTrue(self._record_cell_result(
            cell, run_id,
            primary=self._producer_record(
                "ast_fail_prev", preview_file, variant="preview",
                mime_type="image/webp", key=KEY_X,
            ),
            derivative=None,
            key=KEY_X,
        ))
        self.assertTrue(self.repo.record_terminal(run_id, cell.cell_id, "completed"))

        # Generate Original on the same cell Generation, then fail.
        outcome = self.repo.claim_or_reuse_original_attempt(gen)
        assert outcome is not None and outcome.attempt is not None
        self.assertEqual(outcome.outcome, "created")
        retry_run = outcome.attempt.run_id
        self.repo.claim_attempt(retry_run)
        self.assertTrue(
            self.repo.record_terminal(
                retry_run, cell.cell_id, "failed", error="GPU OOM on retry",
            )
        )

        gen_item = self._project(gen)
        self.assertEqual(gen_item["output_count"], 1)
        gen_out = gen_item["outputs"][0]
        self.assertEqual(gen_out["original_url"], "")
        self.assertTrue(gen_out["original_failed"])
        self.assertNotEqual(gen_out["preview_url"], "")

        (cell_detail,) = self._experiment_projection("exp_e1c_parity")
        self.assertEqual(cell_detail["original_url"], "")
        self.assertTrue(cell_detail["original_failed"])
        self.assertEqual(cell_detail["preview_url"], gen_out["preview_url"])
        payload = cell_detail["generation"]
        assert payload is not None
        self.assertEqual(payload["outputs"], gen_item["outputs"])
        self.assertIn(
            {"code": "attempt_failed", "message": "GPU OOM on retry"},
            payload["errors"],
        )


# ── 8: remote modal:// keyed Original ────────────────────────────────────


class RemoteKeyedOriginalTests(_ProductionCase):
    REMOTE_REF = "modal://ws_e1c||output_assets/remote_original.png"

    def _remote_asset(self, gen, run_id, *, created_at: str) -> Asset:
        # assets.run_id carries a real FK to run_attempts, so the producing
        # Attempt row must exist before adoption (production order).
        self._attempt(gen, run_id, "original", "completed")
        asset = self.repo.adopt_asset(
            gen,
            run_id=run_id,
            reference=self.REMOTE_REF,
            sha256="e" * 64,
            fmt="png",
            width=128,
            height=256,
            created_at=created_at,
            logical_output_key=KEY_X,
        )
        assert asset is not None
        return asset

    def test_remote_keyed_original_groups_and_wins_when_newest(self):
        gen = "gen_e1c_remote_new"
        self.repo.create_generation(generation_id=gen)
        local = self._seed_asset(
            gen, "run_rem_local", "original", "original",
            key=KEY_X, created_at=_past(30),
        )
        remote = self._remote_asset(gen, "run_rem_remote", created_at=_past(20))

        stored = self.repo.get_asset(remote.asset_id)
        assert stored is not None
        self.assertEqual(stored.managed_path, self.REMOTE_REF)
        self.assertEqual(stored.logical_output_key, KEY_X)

        item = self._project(gen)
        self.assertEqual(item["output_count"], 1)
        self.assertEqual(len(item["outputs"]), 1)
        self.assertTrue(item["outputs"][0]["original_url"].endswith(f"/{remote.asset_id}"))
        self.assertFalse(
            item["outputs"][0]["original_failed"],
            "persisted modal:// reference is structurally usable without a fetch",
        )

    def test_remote_keyed_original_loses_to_newer_local(self):
        gen = "gen_e1c_remote_old"
        self.repo.create_generation(generation_id=gen)
        remote = self._remote_asset(gen, "run_rem_old", created_at=_past(30))
        local = self._seed_asset(
            gen, "run_rem_new", "original", "original",
            key=KEY_X, created_at=_past(20),
        )

        item = self._project(gen)
        self.assertEqual(item["output_count"], 1)
        self.assertTrue(item["outputs"][0]["original_url"].endswith(f"/{local.asset_id}"))
        self.assertFalse(item["outputs"][0]["original_failed"])
        # Both provenance rows remain retained underneath the one group.
        detail = self.repo.get_generation(gen)
        assert detail is not None
        self.assertEqual(len(detail.assets), 2)


# ── 9: legacy compatibility ──────────────────────────────────────────────


class LegacyCompatibilityTests(_ProductionCase):
    def test_unkeyed_legacy_row_remains_readable_and_projectable(self):
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
            ("ast_legacy", "gen_legacy", "run_legacy", "original",
             str(self._producer_file("legacy.png")), "legacy.png",
             None, None, "png", None, "{}", _past(100)),
        )
        conn.commit()
        conn.close()

        store = HistoryV2Store(legacy_path)
        store.initialize()
        store.initialize()  # idempotent migration
        self.assertEqual(store.execute("PRAGMA user_version")[0][0], 2)

        # v1-era databases carry a generations row for every asset; add one
        # through the migrated schema so the full detail route is exercisable.
        with store.transaction() as conn:
            conn.execute(
                """INSERT INTO generations (
                    generation_id, created_at, workflow_id, workflow_version_id,
                    preset_id, preset_name, request_snapshot_id, experiment_id,
                    featured_asset_id, favorite, note, status, prompt_text,
                    negative_prompt_text, model_stack_json, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("gen_legacy", _past(100), None, None, None, None, None, None,
                 None, 0, "", "completed", "", "", "[]", _past(100)),
            )
            conn.execute(
                """INSERT INTO run_attempts (
                    run_id, generation_id, experiment_id, cell_id, mode, status,
                    started_at, finished_at, error, timing_json, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                ("run_legacy", "gen_legacy", None, None, "original",
                 "completed", _past(100), _past(100), None, "{}", _past(100)),
            )

        repo = HistoryV2Repository(store)
        assets = repo.get_generation_assets("gen_legacy")
        self.assertEqual(len(assets), 1)
        self.assertIsNone(assets[0].logical_output_key)

        detail = repo.get_generation("gen_legacy")
        assert detail is not None
        item = _generation_feed_item(
            detail.generation.to_dict(), detail.assets, detail.attempts,
        )
        self.assertEqual(item["output_count"], 1)
        self.assertTrue(
            item["outputs"][0]["original_url"].endswith("/ast_legacy")
        )

    def test_keyed_assets_never_fabricate_legacy_identities(self):
        gen = "gen_e1c_mixed"
        self.repo.create_generation(generation_id=gen)
        # Legacy unkeyed pair sharing one run: groups by run provenance only.
        legacy_orig = self._seed_asset(
            gen, "run_legacy_pair", "original", "original",
            key="", created_at=_past(80),
        )
        self.assertIsNone(legacy_orig.logical_output_key)
        legacy_thumb = self._seed_asset(
            gen, "run_legacy_pair", "preview", "thumbnail",
            key="", created_at=_past(79),
        )
        self.assertIsNone(legacy_thumb.logical_output_key)
        # Modern keyed pair on another run.
        keyed_orig = self._seed_asset(
            gen, "run_modern", "original", "original",
            key=KEY_X, created_at=_past(70),
        )
        keyed_thumb = self._seed_asset(
            gen, "run_modern", "preview", "thumbnail",
            key=KEY_X, created_at=_past(69),
        )

        item = self._project(gen)
        self.assertEqual(
            item["output_count"], 2,
            "keyed and unkeyed rows stay independently proven groups",
        )
        self.assertEqual(len(item["outputs"]), 2)
        grouped = {o["asset_id"] for o in item["outputs"]}
        self.assertEqual(
            grouped, {legacy_orig.asset_id, keyed_orig.asset_id},
        )

        # Re-reading through the repository never assigns keys to legacy rows.
        rows = {a.asset_id: a for a in self.repo.get_generation_assets(gen)}
        self.assertIsNone(rows[legacy_orig.asset_id].logical_output_key)
        self.assertIsNone(rows[legacy_thumb.asset_id].logical_output_key)
        self.assertEqual(rows[keyed_orig.asset_id].logical_output_key, KEY_X)
        self.assertEqual(rows[keyed_thumb.asset_id].logical_output_key, KEY_X)


if __name__ == "__main__":
    unittest.main()
