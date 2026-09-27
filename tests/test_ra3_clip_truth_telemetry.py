"""Offline contracts for the RA3 CLIP truth and timing helpers."""

from __future__ import annotations

import json
import io
import time
import types

import torch
from torch import nn

from comfymodal_runtime import golden_serial as golden


def test_compute_scope_readiness_ignores_bounded_outer_cpu_extra():
    root = nn.Module()
    root.scope = nn.Linear(2, 2, bias=False)
    root.logit_scale = nn.Parameter(torch.tensor(1.0))
    view = next(root.scope.parameters())

    adoption = golden.select_and_validate_qd_adoption_scope(
        "ra3", root, {"weight": view}, device_prefix="cpu"
    )
    identity = golden._clip_compute_identity(root.scope, adoption)

    assert identity["compute_ready"] is True
    assert identity["compute_scope_device"] == "cpu"
    assert adoption["outer_extra_count"] == 1
    assert adoption["outer_extra_devices"] == ["cpu"]


def test_clip_timing_has_json_safe_shape_and_nonoverlapping_parent_spans():
    timing = golden._ClipTiming()
    with timing.span("first"):
        time.sleep(0)
    with timing.span("second"):
        time.sleep(0)
    timing.unproven("h2d_device_span", parent="source_open_read")
    payload = timing.finish()

    json.dumps(payload)
    assert payload["schema"] == "golden_clip_timing_v1"
    assert all({"name", "start_ns", "end_ns", "duration_ns", "boundary_kind"} <= set(item)
               for item in payload["phases"])
    parents = [item for item in payload["phases"] if item["level"] == "parent" and item["start_ns"]]
    assert parents[0]["end_ns"] <= parents[1]["start_ns"]
    assert payload["parent_reconciliation"]["overlap_ns"] == 0


def test_clip_forward_wrappers_classify_and_restore_methods():
    calls = []

    class FakeClip:
        def tokenize(self, text):
            calls.append(("tokenize", text))
            return [text]

        def encode_from_tokens_scheduled(self, tokens):
            calls.append(("encode", tokens))
            return "conditioning"

    clip = FakeClip()
    original_tokenize = clip.tokenize
    original_encode = clip.encode_from_tokens_scheduled
    timing = golden._ClipTiming()
    with golden._clip_forward_wrappers(
        clip, timing, lambda: {"status": "unproven", "reason": "offline"}
    ):
        assert clip.tokenize("hello") == ["hello"]
        assert clip.encode_from_tokens_scheduled(["hello"]) == "conditioning"

    assert clip.tokenize == original_tokenize
    assert clip.encode_from_tokens_scheduled == original_encode
    assert calls == [("tokenize", "hello"), ("encode", ["hello"])]
    assert [item["name"] for item in timing.phases] == [
        "clip_tokenization_input_prep", "clip_qwen_transformer_encode"
    ]


def test_clip_page_fault_snapshot_shape_and_unavailable(monkeypatch):
    usage = types.SimpleNamespace(ru_minflt=11, ru_majflt=3)
    resource = types.SimpleNamespace(
        RUSAGE_SELF=0, getrusage=lambda _kind: usage
    )
    monkeypatch.setattr(golden.importlib, "import_module", lambda _name: resource)
    measured = golden._clip_page_fault_snapshot()
    assert measured == {
        "available": True,
        "source": "resource.getrusage(RUSAGE_SELF)",
        "minor_faults": 11,
        "major_faults": 3,
    }

    monkeypatch.setattr(golden.importlib, "import_module", lambda _name: (_ for _ in ()).throw(ImportError()))
    monkeypatch.setattr(golden.sys, "platform", "win32")
    unavailable = golden._clip_page_fault_snapshot()
    assert unavailable["available"] is False
    assert unavailable["source"] is None
    assert unavailable["minor_faults"] is None
    assert unavailable["major_faults"] is None


def test_page_fault_reader_linux_proc_fallback_and_clip_adapter(monkeypatch):
    stat = "123 (worker with spaces) S 1 2 3 4 5 6 77 8 99 10"
    monkeypatch.setattr(golden.importlib, "import_module", lambda _name: (_ for _ in ()).throw(ImportError()))
    monkeypatch.setattr(golden.sys, "platform", "linux")
    monkeypatch.setattr(golden, "open", lambda *_args, **_kwargs: io.StringIO(stat), raising=False)

    raw = golden._process_page_faults()
    assert raw["available"] is True
    assert raw["source"] == "/proc/self/stat"
    assert raw["minor_faults"] == raw["minor_page_faults"] == 77
    assert raw["major_faults"] == raw["major_page_faults"] == 99
    assert golden._clip_page_fault_snapshot() == {
        "available": True,
        "source": "/proc/self/stat",
        "minor_faults": 77,
        "major_faults": 99,
    }


def test_stage_diagnostics_selector_is_default_off_and_explicitly_enabled(monkeypatch):
    monkeypatch.delenv(golden.GOLDEN_STAGE_DIAGNOSTICS_ENV, raising=False)
    assert golden.stage_diagnostics_enabled() is False
    assert golden._stage_diagnostics_enabled() is False
    monkeypatch.setenv(golden.GOLDEN_STAGE_DIAGNOSTICS_ENV, "true")
    assert golden.stage_diagnostics_enabled() is True
    monkeypatch.setenv(golden.GOLDEN_STAGE_DIAGNOSTICS_ENV, "off")
    assert golden.stage_diagnostics_enabled() is False


def test_clip_diagnostics_off_path_installs_no_temporary_wrappers_or_hooks():
    class FailingClip:
        def __getattribute__(self, name):
            if name in {"tokenize", "encode_from_tokens_scheduled"}:
                raise AssertionError("off path touched temporary wrapper surface")
            return object.__getattribute__(self, name)

    timing = golden._ClipTiming(enabled=False)
    snapshots = []
    with golden._clip_forward_wrappers(
        FailingClip(), timing, lambda: snapshots.append(True), enabled=False
    ):
        pass
    assert snapshots == []
    assert timing.finish() == {"enabled": False}


def test_clip_page_fault_delta_and_summary_keep_missing_dimensions():
    start = {"available": True, "source": "test", "minor_faults": 10, "major_faults": 4}
    end = {"available": True, "source": "test", "minor_faults": 17, "major_faults": 5}
    assert golden._clip_page_fault_delta(start, end) == {
        "available": True,
        "source": "test",
        "minor_fault_delta": 7,
        "major_fault_delta": 1,
    }
    summary = golden._clip_page_faults_summary("golden_clip_forward", start, end)
    assert summary["stage"] == "golden_clip_forward"
    assert summary["start_counters"]["minor_faults"] == 10
    assert summary["end"]["major_faults"] == 5
    assert summary["minor_fault_delta"] == 7


def test_clip_qwen_hooks_capture_first_checkpoint_and_restore(monkeypatch):
    scope = nn.Linear(2, 2, bias=False)
    timing = golden._ClipTiming()
    faults = iter((
        {"available": True, "source": "test", "minor_faults": 20, "major_faults": 1},
        {"available": True, "source": "test", "minor_faults": 24, "major_faults": 2},
    ))
    monkeypatch.setattr(golden, "_clip_page_fault_snapshot", lambda: next(faults))

    with golden._clip_qwen_forward_hooks(
        scope, timing, lambda: {"status": "proven", "entries": []}
    ):
        scope(torch.ones(1, 2))

    record = timing.qwen_forwards[0]
    assert record["phase"] == "first_qwen_compute"
    assert record["duration_ns"] >= 0
    assert record["page_faults"]["minor_fault_delta"] == 4
    assert record["page_faults"]["major_fault_delta"] == 1
    json.dumps(record)
    assert len(scope._forward_pre_hooks) == 0
    assert len(scope._forward_hooks) == 0
    assert [item["name"] for item in timing.phases] == ["clip_qwen_transformer_forward"]
