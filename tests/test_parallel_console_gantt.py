"""FAST_UNIT: Golden Parallel console Gantt is pure, readable, overlap-preserving."""

from __future__ import annotations

import pytest

from comfymodal_runtime.golden_human_report import render_parallel_console_gantt


pytestmark = pytest.mark.fast_unit

_MS = 1_000_000


def _stages():
    # Mirrors a real parallel run: unet_load inside clip_forward,
    # vae_load inside sampling. teardown intentionally omitted.
    return {
        "golden_restore": (0, int(5.2 * _MS)),
        "golden_request_setup": (int(5.2 * _MS), int(6.4 * _MS)),
        "golden_clip_load": (int(6.4 * _MS), int(1780.6 * _MS)),
        "golden_unet_load": (int(1782.9 * _MS), int(4056.0 * _MS)),
        "golden_clip_forward": (int(1783.2 * _MS), int(4911.5 * _MS)),
        "golden_sampler_prepare": (int(4912.9 * _MS), int(5182.4 * _MS)),
        "golden_sampling": (int(5182.7 * _MS), int(8905.2 * _MS)),
        "golden_vae_load": (int(5183.4 * _MS), int(5393.3 * _MS)),
        "golden_sampler_tail": (int(8906.4 * _MS), int(8906.4 * _MS)),
        "golden_vae_decode": (int(8906.5 * _MS), int(9581.1 * _MS)),
        "golden_output": (int(9581.2 * _MS), int(9791.0 * _MS)),
    }


def _transports():
    return [
        {
            "path": "qwen_3_4b.safetensors",
            "source_wall_ms": 1692.4,
            "total_load_ms": 1748.2,
            "source_engine": "m2_exact_window",
            "c0_arena_bytes": 536870912,
        },
        {
            "path": "z_image_turbo_bf16.safetensors",
            "source_wall_ms": 2214.9,
            "total_load_ms": 2237.0,
            "source_engine": "m2_exact_window",
            "c0_arena_bytes": 536870912,
        },
    ]


def test_gantt_shows_stages_transport_detail_and_overlap():
    text = render_parallel_console_gantt(
        _stages(), transports=_transports(), arch="c0_parallel/m2_exact_window"
    )
    assert "[GOLDEN GANTT] mode=parallel arch=c0_parallel/m2_exact_window" in text
    assert "arena=512MiB" in text
    assert "CLIP load" in text
    assert "UNET load" in text
    assert "CLIP forward" in text
    assert "src=1692.4ms full=1748.2ms" in text
    assert "qwen_3_4b.safetensors" in text
    assert "z_image_turbo_bf16.safetensors" in text
    assert "unet_load inside clip_forward" in text
    assert "vae_load inside sampling" in text
    text.encode("ascii")


def test_gantt_tolerates_missing_stages_and_transports():
    text = render_parallel_console_gantt({"golden_clip_load": (0, 1000)})
    assert "CLIP load" in text
    assert "OVERLAP: none measured" in text
    text.encode("ascii")


def test_gantt_empty_without_closed_intervals():
    assert "no closed stage intervals" in render_parallel_console_gantt({})
    assert "no closed stage intervals" in render_parallel_console_gantt(
        {"golden_clip_load": (2000, 1000)}
    )
