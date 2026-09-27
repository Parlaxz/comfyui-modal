"""FAST_UNIT: deploy-time Modal class env forwards C0 scheduling selectors."""

from __future__ import annotations

import pytest

from comfymodal_runtime import modal_app


pytestmark = pytest.mark.fast_unit


def test_c0_transport_geometry_crosses_modal_class_env(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY", "qd4_64_h2d128")

    env = modal_app._runtime_env(None)

    assert env["COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY"] == "qd4_64_h2d128"


def test_c0_transport_geometry_defaults_to_qd4_64(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY", raising=False)

    env = modal_app._runtime_env(None)

    assert env["COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY"] == "qd4_64"


def test_c0_window_trace_crosses_modal_class_env(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_GOLDEN_C0_WINDOW_TRACE", "1")

    env = modal_app._runtime_env(None)

    assert env["COMFYMODAL_GOLDEN_C0_WINDOW_TRACE"] == "1"
