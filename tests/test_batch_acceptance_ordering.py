"""Focused tests for the Batch A/B/C host-side acceptance raise-ordering fix.

The RUN-1 acceptance blocks in ``tools/benchmark_v2_direct.main()`` always
print every enabled layer's validation block, but raise from the authoritative
(strictest) enabled layer only:

  - Batch-A raises iff A fails AND neither Batch-B nor Batch-C is enabled
    (``_batch_a_raise_authorized``): Batch-B preserves Batch-A's gates and
    Batch-C wraps Batch-B, so an A-only failure must not abort before the
    stricter layer has run.
  - Batch-B raises iff B fails AND Batch-C is disabled
    (``_batch_b_raise_authorized``): Batch-C wraps Batch-B (never duplicates
    it) and fails unconditionally when Batch-B fails, so the raise belongs to
    Batch-C whenever it is enabled.
  - Batch-C's raise is unchanged: Batch-C is authoritative whenever it is
    enabled, including the automatic enable produced in ``__main__`` by
    COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH=1.

These tests exercise the raise-authority matrix on the pure predicates and run
the full RUN-1 block sequence (validate -> render -> conditional raise) with
the real validators/renderers over offline artifacts.  No Modal, no network,
no sleeps, no asyncio.

Runnable from the repo root via:
    python -m unittest tests.test_batch_acceptance_ordering -v
"""

from __future__ import annotations

import copy
import os
import unittest
from typing import Any
from unittest import mock

from tools.batch_a_acceptance import render_acceptance_block, validate_batch_a
from tools.batch_b_acceptance import render_batch_b_block, validate_batch_b
from tools.batch_c_acceptance import (
    batch_c_config_from_env,
    render_batch_c_block,
    validate_batch_c,
)
from tools.benchmark_v2_direct import (
    _batch_a_raise_authorized,
    _batch_b_raise_authorized,
)

from tests.test_batch_c_acceptance import (
    _artifact,               # deep copy of the all-pass Batch-A/B artifact
    _fast_path_artifact,     # deep copy of the healthy fast-path artifact
    _make_healthy_fast_path_artifact,
)

# ── Config helpers (mirror the per-block configs built in main()) ─────────

_BATCH_B_CFG_DEFAULTS: dict[str, Any] = {
    "expect_runtime_state_skip": True,
    "snapshot_hygiene_enabled": True,
    "snapshot_manifest_enabled": True,
    "expect_stage13": False,
    "expect_slow_h2d_forensic": False,
}

_BATCH_C_CFG_DEFAULTS: dict[str, Any] = {
    "expect_plan_fast_path": True,
    **_BATCH_B_CFG_DEFAULTS,
}


def _batch_b_cfg(**overrides: Any) -> dict[str, Any]:
    cfg = dict(_BATCH_B_CFG_DEFAULTS)
    cfg.update(overrides)
    return cfg


def _batch_c_cfg(**overrides: Any) -> dict[str, Any]:
    cfg = dict(_BATCH_C_CFG_DEFAULTS)
    cfg.update(overrides)
    return cfg


# ── Artifact mutation helpers (same shapes as the Batch-B test fixtures) ──

def _set_h2d_ms(art: dict[str, Any], ms: float) -> None:
    """Point the real fast-disk H2D evidence at a specific duration."""
    for e in art["result"]["trace"]["events"]:
        if e["name"] == "unet_fast_disk_complete":
            e["metadata"]["to_wall_ms"] = ms
            e["metadata"]["to_device_ms"] = ms - 5.0


def _add_forensic_event(art: dict[str, Any], probe_wall_ms: float = 3.0) -> None:
    """Add the Tier-B slow-H2D forensic trigger event (Batch-A fails on it;
    Batch-B accepts it on a genuinely slow H2D)."""
    art["result"]["trace"]["events"].append(
        {"name": "host_forensic_slow_h2d", "wall_unix_ns": 0,
         "monotonic_ns": 3200,
         "metadata": {"probe_wall_ms": probe_wall_ms}},
    )


def _make_slow_h2d_forensic_artifact() -> dict[str, Any]:
    """The motivating scenario: a genuinely slow H2D (>= SLOW_H2D_THRESHOLD_MS)
    WITH the Tier-B forensic trigger present and the healthy fast-path events.

    - Batch-A FAILS strictly (its ``host_slow_forensic`` gate is
      ``not triggered`` unconditionally).
    - Batch-B PASSES with ``expect_slow_h2d_forensic=True`` (forensic event is
      consistent with the slow H2D; Tier-A overhead stays under the cap).
    - Batch-C PASSES with ``expect_plan_fast_path=True`` (fast-path healthy,
      Batch-B preserved).
    """
    art = _fast_path_artifact()
    _set_h2d_ms(art, 4100.0)
    _add_forensic_event(art)
    return art


def _make_unfresh_artifact() -> dict[str, Any]:
    """Structural failure: not-fresh identity (restore_count=2).  Fails every
    layer: Batch-A (fresh gate), Batch-B (batch_a_preserved gate), Batch-C
    (wraps Batch-B)."""
    art = _artifact()
    art["identity"]["restore_count"] = 2
    return art


def _make_b_only_failure_artifact() -> dict[str, Any]:
    """A Batch-B-specific structural failure (missing snapshot hygiene record)
    that still satisfies every Batch-A gate."""
    art = _artifact()
    art["result"].pop("snapshot_capture_hygiene", None)
    return art


# ── RUN-1 sequence harness (mirror of benchmark_v2_direct.main()) ─────────

def _run_acceptance_blocks(
    artifact: dict[str, Any],
    batch_a: bool,
    batch_b: bool,
    batch_c: bool,
    b_cfg: dict[str, Any] | None = None,
    c_cfg: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Mirror the RUN-1 acceptance block sequence in
    ``benchmark_v2_direct.main()``: for every enabled layer run the real
    validator, render the block, then raise only from the authoritative layer
    (via the real predicates).

    Returns ``(raised, blocks)`` where ``raised`` is the ordered list of
    layers that would raise (mirrors the first ``RuntimeError`` in main()) and
    ``blocks`` maps each rendered layer label to its block text.
    """
    raised: list[str] = []
    blocks: dict[str, str] = {}
    if batch_a:
        _res = validate_batch_a(artifact)
        blocks["A"] = render_acceptance_block(_res)
        if not _res.passed and _batch_a_raise_authorized(batch_b, batch_c):
            raised.append("A")
    if batch_b:
        _res = validate_batch_b(
            artifact, **(_batch_b_cfg() if b_cfg is None else b_cfg),
        )
        blocks["B"] = render_batch_b_block(_res)
        if not _res.passed and _batch_b_raise_authorized(batch_c):
            raised.append("B")
    if batch_c:
        _res = validate_batch_c(
            artifact, **(_batch_c_cfg() if c_cfg is None else c_cfg),
        )
        blocks["C"] = render_batch_c_block(_res)
        if not _res.passed:
            raised.append("C")
    return raised, blocks


# ═════════════════════════════════════════════════════════════════════════
# Raise-authority matrix (pure predicates)
# ═════════════════════════════════════════════════════════════════════════

class TestRaiseAuthorityMatrix(unittest.TestCase):
    """Which layer is authoritative for a given enabled-layer combination,
    independent of the validation results."""

    def test_a_only_authoritative(self):
        # A-only: A raises on failure, B raises on failure (C disabled).
        self.assertTrue(_batch_a_raise_authorized(False, False))
        self.assertTrue(_batch_b_raise_authorized(False))

    def test_ab_defers_a(self):
        # A+B (C disabled): A is deferred, B is authoritative.
        self.assertFalse(_batch_a_raise_authorized(True, False))
        self.assertTrue(_batch_b_raise_authorized(False))

    def test_ac_defers_a(self):
        # A+C (B disabled): A is deferred.
        self.assertFalse(_batch_a_raise_authorized(False, True))

    def test_bc_defers_b(self):
        # B+C: A is deferred (C enabled) and B is deferred (C enabled).
        self.assertFalse(_batch_a_raise_authorized(False, True))
        self.assertFalse(_batch_b_raise_authorized(True))

    def test_abc_only_c_authoritative(self):
        # A+B+C: neither A nor B is authoritative.
        self.assertFalse(_batch_a_raise_authorized(True, True))
        self.assertFalse(_batch_b_raise_authorized(True))

    def test_resolved_c_auto_enable_defers_a_and_b(self):
        # The C-enabled state resolved from COMFYMODAL_V2_BATCH_C_EXPECT_
        # PLAN_FAST_PATH=1 (env auto-enable in __main__) defers both A and B.
        with mock.patch.dict(os.environ, {
            "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "1",
        }, clear=False):
            cfg = batch_c_config_from_env()
        self.assertIs(cfg["expect_plan_fast_path"], True)
        # Same boolean semantic as __main__'s resolved _batch_c_acceptance.
        resolved_c = True
        self.assertFalse(_batch_a_raise_authorized(False, resolved_c))
        self.assertFalse(_batch_b_raise_authorized(resolved_c))


# ═════════════════════════════════════════════════════════════════════════
# Full RUN-1 ordering behavior (real validators + renderers + predicates)
# ═════════════════════════════════════════════════════════════════════════

class TestAcceptanceOrdering(unittest.TestCase):
    def test_a_only_failure_raises_a(self):
        raised, blocks = _run_acceptance_blocks(
            _make_unfresh_artifact(), batch_a=True, batch_b=False, batch_c=False,
        )
        self.assertEqual(raised, ["A"])
        self.assertIn("BATCH A ACCEPTANCE", blocks["A"])
        self.assertIn("OVERALL: FAIL", blocks["A"])

    def test_a_only_all_pass_success(self):
        raised, blocks = _run_acceptance_blocks(
            _artifact(), batch_a=True, batch_b=False, batch_c=False,
        )
        self.assertEqual(raised, [])
        self.assertIn("OVERALL: PASS", blocks["A"])

    def test_ab_defers_a_and_a_failure_is_reported_not_fatal(self):
        # A fails strictly (slow-H2D forensic), B passes: with A+B enabled the
        # A failure is deferred and the run succeeds.  The A block still
        # rendered (enabled layers always render).
        raised, blocks = _run_acceptance_blocks(
            _make_slow_h2d_forensic_artifact(),
            batch_a=True, batch_b=True, batch_c=False,
        )
        self.assertEqual(raised, [])
        self.assertIn("BATCH A ACCEPTANCE", blocks["A"])
        self.assertIn("Slow forensic trigger: YES", blocks["A"])
        self.assertIn("BATCH B ACCEPTANCE", blocks["B"])

    def test_ab_both_fail_raises_b(self):
        # A+B where both fail: A defers to B and B is authoritative (C off).
        raised, blocks = _run_acceptance_blocks(
            _make_unfresh_artifact(),
            batch_a=True, batch_b=True, batch_c=False,
        )
        self.assertEqual(raised, ["B"])
        self.assertIn("BATCH A ACCEPTANCE", blocks["A"])
        self.assertIn("BATCH B ACCEPTANCE", blocks["B"])

    def test_ac_defers_a(self):
        # A fails, C passes: A is deferred and C (authoritative) passes.
        raised, blocks = _run_acceptance_blocks(
            _make_slow_h2d_forensic_artifact(),
            batch_a=True, batch_b=False, batch_c=True,
            c_cfg=_batch_c_cfg(expect_slow_h2d_forensic=True),
        )
        self.assertEqual(raised, [])
        self.assertIn("BATCH A ACCEPTANCE", blocks["A"])
        self.assertIn("BATCH C ACCEPTANCE", blocks["C"])
        self.assertIn("OVERALL: PASS", blocks["C"])

    def test_bc_defers_b(self):
        # B fails structurally, C wraps B and fails: B is deferred, C raises.
        raised, blocks = _run_acceptance_blocks(
            _make_b_only_failure_artifact(),
            batch_a=False, batch_b=True, batch_c=True,
        )
        self.assertEqual(raised, ["C"])
        self.assertIn("BATCH B ACCEPTANCE", blocks["B"])
        self.assertIn("BATCH C ACCEPTANCE", blocks["C"])
        self.assertIn("OVERALL: FAIL", blocks["C"])

    def test_abc_all_pass_success(self):
        raised, blocks = _run_acceptance_blocks(
            _make_healthy_fast_path_artifact(),
            batch_a=True, batch_b=True, batch_c=True,
        )
        self.assertEqual(raised, [])
        for label in ("A", "B", "C"):
            self.assertIn(f"BATCH {label} ACCEPTANCE", blocks[label])

    def test_abc_only_c_authoritative_on_all_fail(self):
        # Structural failure that fails A, B and C: only C is authoritative.
        raised, blocks = _run_acceptance_blocks(
            _make_unfresh_artifact(),
            batch_a=True, batch_b=True, batch_c=True,
        )
        self.assertEqual(raised, ["C"])
        # Every enabled layer still rendered.
        self.assertIn("BATCH A ACCEPTANCE", blocks["A"])
        self.assertIn("OVERALL: FAIL", blocks["A"])
        self.assertIn("BATCH B ACCEPTANCE", blocks["B"])
        self.assertIn("BATCH C ACCEPTANCE", blocks["C"])
        self.assertIn("OVERALL: FAIL", blocks["C"])

    def test_slow_h2d_forensic_final_success(self):
        # Headline scenario: strict A FAIL (forensic trigger), corrected
        # B PASS (expect_slow_h2d_forensic=True), C PASS (fast-path healthy).
        # With A+B+C enabled the run ends in success, not an A abort.
        raised, blocks = _run_acceptance_blocks(
            _make_slow_h2d_forensic_artifact(),
            batch_a=True, batch_b=True, batch_c=True,
            b_cfg=_batch_b_cfg(expect_slow_h2d_forensic=True),
            c_cfg=_batch_c_cfg(expect_slow_h2d_forensic=True),
        )
        self.assertEqual(raised, [])
        # A block is reported FAIL but rendered.
        self.assertIn("OVERALL: FAIL", blocks["A"])
        self.assertIn("Slow forensic trigger: YES", blocks["A"])
        self.assertIn("OVERALL: PASS", blocks["B"])
        self.assertIn("OVERALL: PASS", blocks["C"])

    def test_resolved_c_auto_enable_defers_a_and_b_end_to_end(self):
        # Resolved C flag (True, as auto-enabled by the env) defers A/B even
        # when A fails; C's verdict is final.
        art = _make_unfresh_artifact()
        with mock.patch.dict(os.environ, {
            "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "1",
        }, clear=False):
            cfg = batch_c_config_from_env()
        raised, blocks = _run_acceptance_blocks(
            art,
            batch_a=True, batch_b=True, batch_c=True,
            c_cfg=cfg,  # expect_plan_fast_path=True (auto-enable semantics)
        )
        self.assertEqual(raised, ["C"])
        self.assertIn("BATCH C ACCEPTANCE", blocks["C"])

    def test_total_wall_remains_informational(self):
        # 60 s TOTAL WALL must never gate: the all-pass artifact passes every
        # enabled layer and the blocks keep calling it informational.
        raised, blocks = _run_acceptance_blocks(
            _make_healthy_fast_path_artifact(),
            batch_a=True, batch_b=True, batch_c=True,
        )
        self.assertEqual(raised, [])
        self.assertIn("TOTAL WALL NOT AN ACCEPTANCE GATE", blocks["C"])
        self.assertIn("TOTAL WALL: 60000.0 (informational only)", blocks["C"])


if __name__ == "__main__":
    unittest.main()
