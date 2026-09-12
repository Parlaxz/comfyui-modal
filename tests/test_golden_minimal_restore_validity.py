"""Focused validity-contract tests for Golden Minimal Restore + attention backend.

Covers the two Phase 1 corrections:
1. Minimal Restore must still supply a genuine snapshot/quiescence proof (the
   classifier requirement is unchanged and fail-closed).
2. The ``sage_runtime_mode_resolved`` validity rule is backend-aware: required
   when ``attention_backend_resolved == "sage"``, not required for a non-Sage
   backend (e.g. ``comfy_kitchen``), while a missing/unknown resolved backend
   still fails closed.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "tools" / "benchmark_v2_direct.py"
MODAL = ROOT / "comfymodal_runtime" / "modal_app.py"


def _bench_src() -> str:
    return BENCH.read_text(encoding="utf-8", errors="replace")


def _modal_src() -> str:
    return MODAL.read_text(encoding="utf-8", errors="replace")


def test_snapshot_proof_requirement_unchanged_and_fail_closed():
    """The classifier still demands a complete, proven snapshot proof."""
    src = _bench_src()
    start = src.index("def _golden_p1_snapshot_proof_present")
    body = src[start : start + 2600]
    for needle in (
        "GOLDEN_P1_SNAPSHOT_PROOF_SCHEMA",
        'proof.get("passive") is not True',
        'proof.get("proven") is not True',
        "surface_count",
        "snapshot_size_bytes",
        "snapshot_size_limit_bytes",
    ):
        assert needle in body, f"snapshot proof requirement lost: {needle}"
    assert 'if not _golden_p1_snapshot_proof_present(scan["snapshot_proof"]):' in src
    assert "snapshot proof absent, unproven, malformed, or contaminated" in src


def test_sage_validity_rule_is_backend_aware():
    """Sage mode is required only when the resolved backend is Sage."""
    src = _bench_src()
    assert 'rec.get("attention_backend_resolved") == "sage"' in src
    # Both Sage failure modes are still produced under that gate.
    assert "sage_runtime_mode_resolved_missing" in src
    assert "sage_resolved_is_auto_invalid" in src


def test_missing_or_unknown_attention_backend_fails_closed():
    """An unresolved attention backend must not silently pass."""
    src = _bench_src()
    assert 'rec.get("attention_backend_resolved") in {"missing", "mixed"}' in src
    assert "attention_backend_resolved_missing" in src


def test_minimal_restore_projects_existing_snapshot_proof_only():
    """Minimal restore projects the snapshotted proof; never fabricates one."""
    src = _modal_src()
    start = src.index("def _golden_minimal_restore(")
    end = src.index("def restore(self)", start)
    body = src[start:end]
    assert "_preserved_snapshot_proof" in body
    assert (
        'telemetry["golden_snapshot_content_proof"] = dict(_preserved_snapshot_proof)'
        in body
    )
    # The proof is copied from prior snapshotted timing, not recomputed.
    assert 'getattr(self, "_restore_timing", None)' in body
    assert "golden_snapshot_content_proof" in body


def test_minimal_restore_does_not_fabricate_sage_resolution():
    """Minimal restore must not emit false Sage runtime metadata."""
    src = _modal_src()
    start = src.index("def _golden_minimal_restore(")
    end = src.index("def restore(self)", start)
    body = src[start:end]
    assert "sage_runtime_mode_resolved" not in body
    assert "baked_cuda" not in body
