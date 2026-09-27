from __future__ import annotations

from types import SimpleNamespace

import pytest

from comfymodal_runtime.modal_app import production_snapshot_invariant


def _models(clip=True, unet=True):
    return SimpleNamespace(
        clip=object() if clip else None,
        unet=object() if unet else None,
        model_key=SimpleNamespace(
            clip_identity="qwen_3_4b.safetensors" if clip else "",
            unet_identity="z_image_turbo_bf16.safetensors" if unet else "",
        ),
    )


def test_production_snapshot_requires_both_models(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_V2_ENV_PROFILE", "production")
    result = production_snapshot_invariant(_models(), phase="test")
    assert result["status"] == "pass"
    assert result["actual_clip"] == 1
    assert result["actual_unet"] == 1

    with pytest.raises(RuntimeError, match="invariant failed"):
        production_snapshot_invariant(_models(clip=False), phase="test")


def test_diagnostic_snapshot_profiles_can_be_partial(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_V2_ENV_PROFILE", "diagnostic")
    result = production_snapshot_invariant(_models(unet=False), phase="test")
    assert result["status"] == "pass"
    assert result["actual_clip"] == 1
    assert result["actual_unet"] == 0
