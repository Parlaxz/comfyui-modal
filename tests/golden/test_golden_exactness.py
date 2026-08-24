"""Exactness gate wiring + integration seam surface."""

from __future__ import annotations

import pytest

from comfymodal_runtime.golden.contracts import EXACT_OUTPUT_SHA


def test_canonical_output_sha_constant():
    assert EXACT_OUTPUT_SHA == "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260"


def test_profile_expected_sha_matches_constant():
    profile = (
        (__import__("pathlib").Path(__file__).resolve().parents[2] / "config" / "v2" / "profiles" / "e37-clean-lane-qd4.toml")
        .read_text(encoding="utf-8")
    )
    assert EXACT_OUTPUT_SHA in profile


def test_golden_pipeline_enabled_env_gate(monkeypatch):
    from comfymodal_runtime.golden.integration import golden_pipeline_enabled

    monkeypatch.delenv("COMFYMODAL_GOLDEN_PIPELINE", raising=False)
    assert golden_pipeline_enabled() is False
    monkeypatch.setenv("COMFYMODAL_GOLDEN_PIPELINE", "1")
    assert golden_pipeline_enabled() is True
    monkeypatch.setenv("COMFYMODAL_GOLDEN_PIPELINE", "0")
    assert golden_pipeline_enabled() is False


def test_install_golden_seams_surface():
    from comfymodal_runtime.golden.integration import install_golden_seams
    from comfymodal_runtime.golden.pipeline import GoldenPipeline
    from comfymodal_runtime.golden.resource_scheduler import GoldenResourceScheduler

    seams = install_golden_seams(GoldenPipeline(GoldenResourceScheduler()))
    for name in [
        "clip_golden_load",
        "unet_golden_prepare",
        "unet_golden_commit",
        "unet_demand_join",
        "vae_golden_qd",
        "vae_demand_join",
    ]:
        assert callable(seams[name]), f"seam {name} missing/not callable"
