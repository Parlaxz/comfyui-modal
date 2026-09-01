"""Focused CPU contracts for RX3 CLIP forward decomposition."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import torch
from torch import nn

from comfymodal_runtime import golden_serial as golden


class _FakeBlock(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.input_layernorm = nn.LayerNorm(4)
        self.self_attn = nn.Linear(4, 4, bias=False)
        self.post_attention_layernorm = nn.LayerNorm(4)
        self.mlp = nn.Linear(4, 4, bias=False)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        value = self.self_attn(self.input_layernorm(value))
        return self.mlp(self.post_attention_layernorm(value))


class _FakeQwenTransformer(nn.Module):
    def __init__(self, blocks: int = 2) -> None:
        super().__init__()
        self.embed_tokens = nn.Embedding(8, 4)
        self.layers = nn.ModuleList([_FakeBlock() for _ in range(blocks)])
        self.output_projection = nn.Linear(4, 4, bias=False)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        value = self.embed_tokens(tokens)
        for layer in self.layers:
            value = layer(value)
        return self.output_projection(value)


def test_disabled_decomposition_is_a_true_noop(monkeypatch):
    class NoInspection:
        def __getattribute__(self, name):
            if name == "named_modules":
                raise AssertionError("disabled path inspected module structure")
            return object.__getattribute__(self, name)

    timing = golden._ClipTiming(enabled=False)
    with golden._clip_forward_decomposition_hooks(NoInspection(), timing, enabled=False):
        pass
    assert not hasattr(timing, "forward_decomposition")
    assert timing.finish() == {"enabled": False}


def test_module_classification_and_first_steady_grouping():
    scope = _FakeQwenTransformer()
    assert golden._clip_classify_module("model.layers.0.self_attn", scope.layers[0].self_attn)["category"] == "attention"
    assert golden._clip_classify_module("model.layers.0", scope.layers[0])["layer_group"] == "first_layer"
    assert golden._clip_classify_module("model.layers.1", scope.layers[1])["layer_group"] == "steady_state_layers"

    timing = golden._ClipTiming()
    with golden._clip_forward_decomposition_hooks(scope, timing):
        scope(torch.tensor([[1, 2]], dtype=torch.long))
    payload = timing.forward_decomposition.payload(authoritative_total_wall_ns=1_000_000)
    assert payload["hook_status"] == "installed"
    assert payload["module_host_durations_ns"]["attention"] >= 0
    assert payload["first_vs_steady_layers"]["first_layer"]["record_count"] >= 1
    assert payload["first_vs_steady_layers"]["steady_state_layers"]["record_count"] >= 1
    json.dumps(payload)


def test_phase_durations_keep_original_names_and_are_explicitly_inclusive():
    timing = golden._ClipTiming()
    with timing.span("clip_graph_node_wrapper"):
        pass
    with timing.span("clip_qwen_transformer_encode"):
        pass
    payload = golden._ClipForwardDecomposition(timing, None, enabled=True).payload(
        authoritative_total_wall_ns=1_000_000
    )
    phase_durations = payload["phase_host_inclusive_durations_ns"]
    assert "clip_graph_node_wrapper" in phase_durations
    assert "clip_qwen_transformer_encode" in phase_durations
    assert "conditioning_token_preparation" not in phase_durations
    assert payload["phase_host_duration_semantics"]["boundary_kind"] == "host_observed_inclusive"
    json.dumps(payload)


def test_decomposition_records_are_bounded(monkeypatch):
    monkeypatch.setattr(golden, "_CLIP_DECOMPOSITION_RECORD_LIMIT", 3)
    monkeypatch.setattr(golden, "_CLIP_DECOMPOSITION_MODULE_LIMIT", 3)
    scope = _FakeQwenTransformer()
    timing = golden._ClipTiming()
    with golden._clip_forward_decomposition_hooks(scope, timing):
        scope(torch.tensor([[1, 2]], dtype=torch.long))
    decomposition = timing.forward_decomposition
    assert len(decomposition.module_catalog) <= 3
    assert len(decomposition.module_records) <= 3
    assert decomposition.records_truncated or decomposition.catalog_truncated


def test_exception_cleanup_removes_every_diagnostic_hook():
    class ExplodingBlock(_FakeBlock):
        def forward(self, value):
            raise RuntimeError("synthetic forward failure")

    scope = _FakeQwenTransformer(blocks=1)
    scope.layers[0] = ExplodingBlock()
    timing = golden._ClipTiming()
    with pytest.raises(RuntimeError, match="synthetic forward failure"):
        with golden._clip_forward_decomposition_hooks(scope, timing):
            scope(torch.tensor([[1, 2]], dtype=torch.long))
    assert all(not module._forward_pre_hooks and not module._forward_hooks for module in scope.modules())


def test_reconciliation_is_explicitly_non_additive_and_preserves_unproven_cuda():
    scope = _FakeQwenTransformer(blocks=1)
    timing = golden._ClipTiming()
    with timing.span("authoritative_parent"):
        with golden._clip_forward_decomposition_hooks(scope, timing):
            scope(torch.tensor([[1, 2]], dtype=torch.long))
    payload = timing.forward_decomposition.payload(authoritative_total_wall_ns=10_000_000)
    reconciliation = payload["reconciliation"]
    assert reconciliation["status"] == "PARTIAL"
    assert reconciliation["authoritative_total_wall_ns"] == 10_000_000
    assert reconciliation["unaccounted_after_parent_spans_ns"] is not None
    assert reconciliation["inner_spans_additive"] is False
    assert reconciliation["inner_spans_status"] == "PARTIAL"
    assert payload["cuda_completion"]["status"] == "UNPROVEN"


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_attachment_uses_real_closed_recorder_interval_and_is_json_safe(outcome):
    recorder = golden.GoldenTelemetryRecorder()
    recorder.begin_stage("golden_clip_forward")
    if outcome == "success":
        recorder.end_stage("golden_clip_forward", ready=True)
    else:
        recorder.fail_stage("golden_clip_forward", RuntimeError("synthetic failure"))
    timing = golden._ClipTiming()
    timing.forward_decomposition = golden._ClipForwardDecomposition(timing, None, enabled=True)
    session = SimpleNamespace(clip_forward_timing={})

    payload = golden._clip_attach_forward_decomposition(
        recorder, session, timing, None, outcome=outcome
    )

    assert payload is not None
    assert payload["stage_outcome"] == outcome
    assert session.clip_forward_timing["decomposition"] == payload
    assert "clip_forward_decomposition" in recorder.intervals["golden_clip_forward"].details
    json.dumps(recorder.to_json_dict())


def test_attachment_diagnostic_failure_and_disabled_path_never_raise():
    recorder = golden.GoldenTelemetryRecorder()
    recorder.begin_stage("golden_clip_forward")
    recorder.end_stage("golden_clip_forward")
    timing = golden._ClipTiming()

    class BrokenDecomposition:
        def payload(self, **_kwargs):
            raise RuntimeError("malformed diagnostic state")

    timing.forward_decomposition = BrokenDecomposition()
    assert golden._clip_attach_forward_decomposition(
        recorder, object(), timing, None, outcome="success"
    ) is None

    disabled_timing = golden._ClipTiming(enabled=False)
    assert golden._clip_attach_forward_decomposition(
        object(), object(), disabled_timing, None, outcome="success"
    ) is None
