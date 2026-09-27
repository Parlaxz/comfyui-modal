"""Focused tests for the Phase B synchronous native page-readiness candidate.

The candidate is a synchronous libc ``madvise(MADV_WILLNEED)`` advisory over
the deduplicated retained CPU tensor-storage ranges, run immediately before
the CLIP prefill encode loop and immediately before the first request-scoped
graph UNET activation.  Covers, without requiring Linux/GPU (libc/helper are
mocked where needed):
  - ``COMFYMODAL_V2_PAGE_READINESS_MODE`` mode gate (off by default;
    ``willneed`` enables the candidate)
  - fake-registry helper behavior: ``advise_storage_pages_willneed`` truthful
    ok / unsupported / error / partial / empty statuses, per-range records
    (ret/errno per range), honest ``advised_*`` counts (never ``populated_*``),
    native fault counters, and registry-build error handling
  - ``status=ok`` reports the ADVISORY was accepted, not that physical pages
    are resident
  - CLIP execution-prefill integration: helper called exactly once after the
    readiness wait and before the encode loop; structured start/end markers
    with stage=clip_prefill; no duplicate encode/future; reconciliation
    attributes the duration as an explicit ``page_readiness`` stage
  - graph UNET activation integration in ``_make_gpu_loader_wrapper``: called
    once per request for the first request-scoped activation only, never for
    restore-time background lanes or non-UNET calls, and never twice for the
    same request; the request guard is cleaned up
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import torch
import torch.nn as nn

import comfymodal_runtime.model_preload as mp
from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
from comfymodal_runtime.cpu_snapshot_models import (
    StorageRange,
    StorageRegistry,
    build_unique_storage_registry,
    page_readiness_mode,
    advise_storage_pages_willneed,
    _PAGE_READINESS_ENV_KEY,
    _PAGE_READINESS_MODE_WILLNEED,
    _MADV_WILLNEED,
)
from comfymodal_runtime.trace import RuntimeTrace
from comfymodal_runtime.unet_forward_probe import register_unet_forward_probe


# ── Helpers ────────────────────────────────────────────────────────────────


def _set_mode(mode: str) -> None:
    """Set the page-readiness env mode (``"off"`` removes it entirely)."""
    if mode == "off":
        os.environ.pop(_PAGE_READINESS_ENV_KEY, None)
    else:
        os.environ[_PAGE_READINESS_ENV_KEY] = mode


def _fake_registry(*ranges: StorageRange) -> StorageRegistry:
    return StorageRegistry(
        ranges=tuple(ranges),
        total_bytes=sum(r.length for r in ranges),
    )


def _fake_ok_result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "ok",
        "mode": _PAGE_READINESS_MODE_WILLNEED,
        "storage_count": 1,
        "range_count": 1,
        "total_bytes": 4096,
        "total_pages": 1,
        "advised_pages": 1,
        "advised_bytes": 4096,
        "advised_percent": 100.0,
        "major_faults": 0,
        "minor_faults": 1,
        "duration_ms": 1.0,
        "error_reason": "",
        "ranges": [],
    }
    result.update(overrides)
    return result


def _build_bridge(
    *,
    clip_loader: Any = None,
    invoke_original: Any = None,
    max_workers: int = 3,
) -> mp.V2LoaderBridge:
    """Build a V2LoaderBridge with mocked internals (attribution-test pattern)."""
    bridge = mp.V2LoaderBridge(max_workers=max_workers)

    def _fake_install(
        nodes_module: Any | None = None, *, trace: RuntimeTrace | None = None,
    ) -> bool:
        return True

    bridge.install = _fake_install  # type: ignore[assignment]
    bridge._request_list = lambda bucket: [{"clip_name": "clip_l.safetensors"}]
    bridge._model_spec = {
        "loaders": {
            "unet": [{"unet_name": "unet.safetensors"}],
            "clip": [{"clip_name": "clip_l.safetensors"}],
        }
    }
    bridge.coordinator.clip_loader = clip_loader or (
        lambda key: SimpleNamespace(patcher=SimpleNamespace())
    )
    bridge.coordinator.unet_loader = lambda key: "unet-done"
    bridge._invoke_original = invoke_original or (
        lambda class_name, kwargs: (f"conditioning:{kwargs['text']}",)
    )
    return bridge


def _make_plan(
    unet_identity: str = "unet.safetensors",
    clip_identity: str = "clip_l.safetensors",
    text: str = "a happy cat",
    role: str = "positive",
) -> RestorePlan:
    model_key = ModelRestoreKey(
        unet_identity=unet_identity,
        clip_identity=clip_identity,
        clip_type="stable_diffusion",
    )
    prefill_key = PrefillKey(
        model_key=model_key,
        prompt_bundle_hash="hash-attr",
        encode_options={
            "eligible": True,
            "encodes": [
                {"node_id": "6", "text": text, "role": role},
            ],
        },
    )
    return RestorePlan(model_key=model_key, prefill_key=prefill_key)


def _event_meta(trace: RuntimeTrace, name: str) -> list[dict[str, Any]]:
    return [dict(e.metadata) for e in trace.events if e.name == name]


def _event_names(trace: RuntimeTrace) -> set[str]:
    return {e.name for e in trace.events}


class _FakeDiffusionModel:
    def forward(self, *args, **kwargs):
        return None

    def register_forward_pre_hook(self, hook, **kwargs):
        return hook


class _FakeModel:
    def __init__(self) -> None:
        self.diffusion_model = _FakeDiffusionModel()


class _FakeUNETPatcher:
    def __init__(self) -> None:
        self.model = _FakeModel()
        self.load_device = "cpu"
        self.offload_device = "cpu"


def _registered_unet_patcher() -> _FakeUNETPatcher:
    """Build a fake UNET patcher and register it in the weak probe registry."""
    patcher = _FakeUNETPatcher()
    register_unet_forward_probe(patcher, source="cpu_snapshot")
    return patcher


# ── Mode gate ──────────────────────────────────────────────────────────────


class TestPageReadinessMode:
    def teardown_method(self) -> None:
        _set_mode("off")

    def test_off_by_default(self) -> None:
        _set_mode("off")
        assert page_readiness_mode() == "off"

    def test_willneed_enabled(self) -> None:
        _set_mode("willneed")
        assert page_readiness_mode() == _PAGE_READINESS_MODE_WILLNEED

    def test_case_insensitive(self) -> None:
        os.environ[_PAGE_READINESS_ENV_KEY] = "WILLNEED"
        assert page_readiness_mode() == _PAGE_READINESS_MODE_WILLNEED

    def test_rejected_populate_read_mode_is_off(self) -> None:
        # The rejected MADV_POPULATE_READ candidate must NOT be accepted:
        # there is exactly one runtime mechanism (willneed), off by default.
        os.environ[_PAGE_READINESS_ENV_KEY] = "populate_read"
        assert page_readiness_mode() == "off"

    def test_invalid_value_is_off(self) -> None:
        os.environ[_PAGE_READINESS_ENV_KEY] = "bogus"
        assert page_readiness_mode() == "off"

    def test_blank_value_is_off(self) -> None:
        os.environ[_PAGE_READINESS_ENV_KEY] = "   "
        assert page_readiness_mode() == "off"


# ── Helper behavior (fake registry, mocked libc) ───────────────────────────


class TestAdviseStoragePagesWillneed:
    def test_ok_advises_all_pages(self) -> None:
        reg = _fake_registry(StorageRange(address=4096, length=8192))
        calls: list[tuple[int, int]] = []

        def fake_madvise(address: int, length: int) -> tuple[int, int | None]:
            calls.append((address, length))
            return (0, None)

        with patch(
            "comfymodal_runtime.cpu_snapshot_models._libc_madvise_willneed",
            return_value=fake_madvise,
        ), patch("comfymodal_runtime.cpu_snapshot_models._page_size", return_value=4096):
            result = advise_storage_pages_willneed(reg)

        assert result["status"] == "ok"
        assert result["mode"] == _PAGE_READINESS_MODE_WILLNEED
        assert result["storage_count"] == 1
        assert result["range_count"] == 1
        assert result["total_bytes"] == 8192
        assert result["total_pages"] == 2
        assert result["advised_pages"] == 2
        assert result["advised_bytes"] == 8192
        assert result["advised_percent"] == 100.0
        assert result["error_reason"] == ""
        assert calls == [(4096, 8192)], calls

    def test_aligned_page_bytes_may_exceed_raw_total_bytes(self) -> None:
        """total_pages/advised_pages count PAGE-ALIGNED ranges: each range
        start is aligned down and end aligned up to the page size, so the
        aligned byte coverage can exceed the raw storage total_bytes."""
        # 5000-byte range starting mid-page (address 4100): the aligned
        # window is [4096, 12288) = 8192 bytes = 2 pages > 5000 raw bytes.
        reg = _fake_registry(StorageRange(address=4100, length=5000))

        def ok_madvise(address: int, length: int) -> tuple[int, int | None]:
            return (0, None)

        with patch(
            "comfymodal_runtime.cpu_snapshot_models._libc_madvise_willneed",
            return_value=ok_madvise,
        ), patch("comfymodal_runtime.cpu_snapshot_models._page_size", return_value=4096):
            result = advise_storage_pages_willneed(reg)

        assert result["status"] == "ok"
        assert result["total_bytes"] == 5000
        assert result["total_pages"] == 2
        assert result["advised_pages"] == 2
        assert result["advised_bytes"] == 8192
        # Aligned coverage (pages * page_size) exceeds raw storage bytes.
        assert result["total_pages"] * 4096 > result["total_bytes"]
        assert result["advised_pages"] * 4096 > result["total_bytes"]

    def test_ok_means_advisory_accepted_not_resident(self) -> None:
        """status=ok must be documented/measured as ADVISED, never populated."""
        reg = _fake_registry(StorageRange(address=4096, length=4096))

        def ok_madvise(address: int, length: int) -> tuple[int, int | None]:
            return (0, None)

        with patch(
            "comfymodal_runtime.cpu_snapshot_models._libc_madvise_willneed",
            return_value=ok_madvise,
        ), patch("comfymodal_runtime.cpu_snapshot_models._page_size", return_value=4096):
            result = advise_storage_pages_willneed(reg)
        # Honest field names: advised_*, never populated_*.
        assert "populated_pages" not in result
        assert "populated_bytes" not in result
        assert "populated_percent" not in result
        assert result["advised_pages"] == 1
        assert result["advised_bytes"] == 4096
        assert result["advised_percent"] == 100.0

    def test_unsupported_when_syscall_unavailable(self) -> None:
        reg = _fake_registry(StorageRange(address=4096, length=4096))
        with patch(
            "comfymodal_runtime.cpu_snapshot_models._libc_madvise_willneed",
            return_value=None,
        ):
            result = advise_storage_pages_willneed(reg)
        # Never invent success: unsupported stays unsupported with no counts.
        assert result["status"] == "unsupported"
        assert result["total_pages"] is None
        assert result["advised_pages"] is None
        assert result["error_reason"] == ""

    def test_error_when_all_ranges_fail(self) -> None:
        reg = _fake_registry(
            StorageRange(address=4096, length=4096),
            StorageRange(address=8192, length=4096),
        )

        def fail_madvise(address: int, length: int) -> tuple[int, int | None]:
            return (-1, 22)  # EINVAL

        with patch(
            "comfymodal_runtime.cpu_snapshot_models._libc_madvise_willneed",
            return_value=fail_madvise,
        ), patch("comfymodal_runtime.cpu_snapshot_models._page_size", return_value=4096):
            result = advise_storage_pages_willneed(reg)

        assert result["status"] == "error"
        assert result["advised_pages"] == 0
        assert result["total_pages"] == 2
        assert "errno=22" in result["error_reason"]
        assert "MADV_WILLNEED" in result["error_reason"]
        assert len(result["ranges"]) == 2
        for record in result["ranges"]:
            assert record["status"] == "error"
            assert record["ret"] == -1
            assert record["errno"] == 22

    def test_partial_when_some_ranges_fail(self) -> None:
        reg = _fake_registry(
            StorageRange(address=4096, length=4096),
            StorageRange(address=16384, length=4096),
        )

        def partial_madvise(address: int, length: int) -> tuple[int, int | None]:
            if address == 4096:
                return (0, None)
            return (-1, 22)

        with patch(
            "comfymodal_runtime.cpu_snapshot_models._libc_madvise_willneed",
            return_value=partial_madvise,
        ), patch("comfymodal_runtime.cpu_snapshot_models._page_size", return_value=4096):
            result = advise_storage_pages_willneed(reg)

        assert result["status"] == "partial"
        assert result["total_pages"] == 2
        assert result["advised_pages"] == 1
        assert result["advised_percent"] == 50.0
        assert result["ranges"][0]["status"] == "ok"
        assert result["ranges"][1]["status"] == "error"

    def test_empty_registry_is_empty(self) -> None:
        result = advise_storage_pages_willneed(_fake_registry())
        assert result["status"] == "empty"
        assert result["range_count"] == 0
        assert result["total_bytes"] == 0

    def test_registry_build_error_is_truthful(self) -> None:
        class _Boom:
            pass

        with patch(
            "comfymodal_runtime.cpu_snapshot_models.build_unique_storage_registry",
            side_effect=RuntimeError("boom"),
        ):
            result = advise_storage_pages_willneed(_Boom())
        assert result["status"] == "error"
        assert "boom" in result["error_reason"]
        assert result["storage_count"] is None

    def test_accepts_existing_registry_directly(self) -> None:
        reg = _fake_registry(StorageRange(address=4096, length=4096))

        def ok_madvise(address: int, length: int) -> tuple[int, int | None]:
            return (0, None)

        with patch(
            "comfymodal_runtime.cpu_snapshot_models._libc_madvise_willneed",
            return_value=ok_madvise,
        ), patch("comfymodal_runtime.cpu_snapshot_models._page_size", return_value=4096):
            result = advise_storage_pages_willneed(reg)
        assert result["status"] == "ok"
        assert result["total_pages"] == 1

    def test_uses_madv_willneed_flag_value(self) -> None:
        # The sole syscall flag used by the helper is MADV_WILLNEED (3) —
        # the rejected MADV_POPULATE_READ (22) must not be referenced.
        assert _MADV_WILLNEED == 3

    def test_never_touches_cuda_or_copies(self) -> None:
        """The helper path (mocked libc) must not call torch or CUDA APIs."""
        import torch

        reg = _fake_registry(StorageRange(address=4096, length=4096))

        def ok_madvise(address: int, length: int) -> tuple[int, int | None]:
            return (0, None)

        with patch(
            "comfymodal_runtime.cpu_snapshot_models._libc_madvise_willneed",
            return_value=ok_madvise,
        ), patch("comfymodal_runtime.cpu_snapshot_models._page_size", return_value=4096), \
            patch.object(torch.cuda, "synchronize",
                         side_effect=AssertionError("must not synchronize CUDA")):
            result = advise_storage_pages_willneed(reg)
        assert result["status"] == "ok"


# ── CLIP wrapper storage-registry resolution (realistic comfy.sd.CLIP) ──
# The retained CLIP object (comfy.sd.CLIP) is NOT an nn.Module: its weights
# live in ``cond_stage_model`` (and ``clip_l``/``clip_g`` leaves) or
# ``patcher.model``.  These tests prove build_unique_storage_registry /
# advise_storage_pages_willneed resolve the exact CPU modules and deduplicate
# ranges across them, with no CUDA moves, copies, tensor element loops, or
# model mutation.  No GPU/Linux required; the libc madvise syscall is mocked.


class _ClipLeaf(nn.Module):
    """Lightweight leaf CLIP encoder: one parameter + one buffer on CPU."""

    def __init__(self, dim: int) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.randn(dim, dim))
        self.register_buffer("bias", torch.zeros(dim))


class _CondStageModel(nn.Module):
    """SDXL-style ``cond_stage_model`` with ``clip_l`` and ``clip_g`` leaves."""

    def __init__(self) -> None:
        super().__init__()
        self.clip_l = _ClipLeaf(4)
        self.clip_g = _ClipLeaf(8)


def _clip_storage_bytes(csm: _CondStageModel) -> int:
    return sum(t.numel() * t.element_size() for t in csm.state_dict().values())


def _make_clip_wrapper() -> SimpleNamespace:
    """Realistic comfy.sd.CLIP wrapper shape: cond_stage_model + patcher."""
    csm = _CondStageModel()
    patcher = SimpleNamespace(model=csm, load_device="cpu", offload_device="cpu")
    return SimpleNamespace(
        cond_stage_model=csm, patcher=patcher, tokenizer=SimpleNamespace()
    )


class TestClipWrapperStorageRegistry:
    """The CPU storage registry must target the exact retained CLIP CPU
    modules (wrapper -> cond_stage_model -> clip_l/clip_g; patcher ->
    patcher.model; direct cond_stage_model) and deduplicate ranges across
    them."""

    def test_wrapper_resolves_cond_stage_modules_and_deduplicates(self) -> None:
        clip = _make_clip_wrapper()
        reg = build_unique_storage_registry(clip)
        assert isinstance(reg, StorageRegistry)
        # 4 unique CPU storages: clip_l.weight, clip_l.bias, clip_g.weight,
        # clip_g.bias — clip_l/clip_g are reached both through cond_stage_model
        # and directly, so identical storages/ranges must be deduplicated.
        assert len(reg.ranges) == 4, reg.ranges
        assert reg.total_bytes == _clip_storage_bytes(clip.cond_stage_model)

    def test_patcher_shape_resolves_to_cond_stage_model(self) -> None:
        clip = _make_clip_wrapper()
        reg = build_unique_storage_registry(clip.patcher)
        assert len(reg.ranges) == 4, reg.ranges
        assert reg.total_bytes == _clip_storage_bytes(clip.cond_stage_model)

    def test_cond_stage_model_shape_resolves_directly(self) -> None:
        clip = _make_clip_wrapper()
        reg = build_unique_storage_registry(clip.cond_stage_model)
        assert len(reg.ranges) == 4, reg.ranges
        assert reg.total_bytes == _clip_storage_bytes(clip.cond_stage_model)

    def test_advise_storage_pages_willneed_targets_clip_wrapper(self) -> None:
        clip = _make_clip_wrapper()
        calls: list[tuple[int, int]] = []

        def ok_madvise(address: int, length: int) -> tuple[int, int | None]:
            calls.append((address, length))
            return (0, None)

        with patch(
            "comfymodal_runtime.cpu_snapshot_models._libc_madvise_willneed",
            return_value=ok_madvise,
        ), patch("comfymodal_runtime.cpu_snapshot_models._page_size", return_value=4096):
            result = advise_storage_pages_willneed(clip)

        assert result["status"] == "ok"
        assert result["storage_count"] == 4
        assert result["range_count"] == 4
        assert result["total_bytes"] == _clip_storage_bytes(clip.cond_stage_model)
        assert calls, "page-readiness must target the retained CLIP storage ranges"

    def test_meta_tensors_never_scanned(self) -> None:
        """Meta tensors are skipped; only retained CPU storage is registered."""

        class _MetaLeaf(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.weight = nn.Parameter(torch.empty(4, 4, device="meta"))
                self.extra = nn.Parameter(torch.randn(2, 2))  # CPU, retained

        reg = build_unique_storage_registry(_MetaLeaf())
        assert len(reg.ranges) == 1
        assert reg.total_bytes == 2 * 2 * 4


# ── CLIP execution-prefill integration ─────────────────────────────────────


class TestClipPrefillPageReadiness:
    def teardown_method(self) -> None:
        _set_mode("off")

    def test_off_is_noop(self) -> None:
        _set_mode("off")
        clip_obj = SimpleNamespace(patcher=SimpleNamespace())
        encode_calls: list[str] = []

        def tracking_encode(class_name: str, kwargs: dict[str, Any]) -> tuple[str, ...]:
            encode_calls.append(kwargs.get("text", ""))
            return (f"conditioning:{kwargs['text']}",)

        bridge = _build_bridge(
            clip_loader=lambda key: clip_obj,
            invoke_original=tracking_encode,
            max_workers=2,
        )
        trace = RuntimeTrace(request_id="pr-off", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)
        prep = bridge._preparation
        assert prep is not None

        with patch(
            "comfymodal_runtime.model_preload.advise_storage_pages_willneed",
            side_effect=AssertionError("must not be called when mode is off"),
        ):
            assert bridge.schedule_execution_prefill(trace=trace) is True
            fut = prep.prefill_future
            assert fut is not None
            results = fut.result(timeout=5)

        assert results is not None and len(results) == 1
        assert encode_calls == ["a happy cat"]
        # Graph consumption triggers the single reconciliation record.
        consumed = bridge._consume_prefill((), {"clip": clip_obj, "text": "a happy cat"})
        assert consumed is not mp._LOADER_MISS
        names = _event_names(trace)
        assert mp._EVENT_PAGE_READINESS_START not in names
        assert mp._EVENT_PAGE_READINESS_END not in names
        # Reconciliation remains complete with the stage truthfully absent.
        records = _event_meta(trace, mp._EVENT_RECONCILIATION)
        assert len(records) == 1
        record = records[0]
        assert record["page_readiness_applied"] is False
        assert record["page_readiness_ms"] is None
        assert record["page_readiness"] == {}
        assert record["reconciliation_status"] == "complete"
        bridge.coordinator.close()

    def test_willneed_calls_once_and_emits_markers(self) -> None:
        _set_mode("willneed")
        clip_obj = SimpleNamespace(patcher=SimpleNamespace())
        calls: list[Any] = []
        encode_calls: list[str] = []

        def fake_advise(model: Any) -> dict[str, Any]:
            calls.append(model)
            return _fake_ok_result(storage_count=3, total_bytes=12288, total_pages=3)

        def tracking_encode(class_name: str, kwargs: dict[str, Any]) -> tuple[str, ...]:
            encode_calls.append(kwargs.get("text", ""))
            return (f"conditioning:{kwargs['text']}",)

        bridge = _build_bridge(
            clip_loader=lambda key: clip_obj,
            invoke_original=tracking_encode,
            max_workers=2,
        )
        trace = RuntimeTrace(request_id="pr-on", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)
        prep = bridge._preparation
        assert prep is not None

        with patch(
            "comfymodal_runtime.model_preload.advise_storage_pages_willneed",
            side_effect=fake_advise,
        ):
            assert bridge.schedule_execution_prefill(trace=trace) is True
            fut = prep.prefill_future
            assert fut is not None
            results = fut.result(timeout=5)

        # Called exactly once for the exact retained CLIP object; encode once.
        assert len(calls) == 1, f"expected one helper call, got {len(calls)}"
        assert calls[0] is clip_obj
        assert encode_calls == ["a happy cat"], "must not duplicate the encode"

        consumed = bridge._consume_prefill((), {"clip": clip_obj, "text": "a happy cat"})
        assert consumed is not mp._LOADER_MISS

        names = _event_names(trace)
        assert mp._EVENT_PAGE_READINESS_START in names
        assert mp._EVENT_PAGE_READINESS_END in names
        end_meta = _event_meta(trace, mp._EVENT_PAGE_READINESS_END)[0]
        assert end_meta["stage"] == "clip_prefill"
        assert end_meta["mode"] == _PAGE_READINESS_MODE_WILLNEED
        assert end_meta["status"] == "ok"
        assert end_meta["storage_count"] == 3
        assert end_meta["total_pages"] == 3
        assert end_meta["major_faults"] is not None
        assert end_meta["minor_faults"] is not None
        assert end_meta["error_reason"] == ""

        # Reconciliation attributes an explicit page_readiness stage.
        records = _event_meta(trace, mp._EVENT_RECONCILIATION)
        assert len(records) == 1
        record = records[0]
        assert record["page_readiness_applied"] is True
        assert isinstance(record["page_readiness_ms"], (int, float))
        assert record["page_readiness"]["status"] == "ok"
        assert record["reconciliation_status"] == "complete"
        children = (
            record["queue_ms"] + record["readiness_ms"]
            + record["page_readiness_ms"] + record["encode_ms"]
            + record["completion_ms"]
        )
        assert abs(children - record["measured_children_ms"]) < 0.01
        bridge.coordinator.close()

    def test_unsupported_status_is_reported_truthfully(self) -> None:
        _set_mode("willneed")
        clip_obj = SimpleNamespace(patcher=SimpleNamespace())

        def fake_advise(model: Any) -> dict[str, Any]:
            return _fake_ok_result(status="unsupported", total_pages=None, advised_pages=None)

        bridge = _build_bridge(clip_loader=lambda key: clip_obj, max_workers=2)
        trace = RuntimeTrace(request_id="pr-unsupported", process="remote")
        plan = _make_plan()
        bridge.prepare(plan, trace=trace)
        prep = bridge._preparation
        assert prep is not None

        with patch(
            "comfymodal_runtime.model_preload.advise_storage_pages_willneed",
            side_effect=fake_advise,
        ):
            bridge.schedule_execution_prefill(trace=trace)
            fut = prep.prefill_future
            assert fut is not None
            fut.result(timeout=5)

        bridge._consume_prefill((), {"clip": clip_obj, "text": "a happy cat"})

        end_meta = _event_meta(trace, mp._EVENT_PAGE_READINESS_END)[0]
        assert end_meta["status"] == "unsupported"
        assert end_meta["total_pages"] is None
        # The stage still exists and is attributed; unsupported is truthful.
        records = _event_meta(trace, mp._EVENT_RECONCILIATION)
        record = records[0]
        assert record["page_readiness_applied"] is True
        assert record["page_readiness"]["status"] == "unsupported"
        bridge.coordinator.close()


# ── Graph UNET activation integration (load_models_gpu wrapper) ────────────


class TestUnetActivationPageReadiness:
    """The load_models_gpu wrapper invokes the readiness helper (via the real
    gate + marker path) exactly once for the first request-scoped graph UNET
    activation.  ``advise_storage_pages_willneed`` is mocked so no Linux/GPU or
    tensor registry is required; the mode gate, per-request guard, marker
    emission, and lane filtering are exercised for real."""

    def teardown_method(self) -> None:
        _set_mode("off")

    def test_first_graph_activation_calls_once_per_request(self) -> None:
        _set_mode("willneed")
        patcher = _registered_unet_patcher()
        calls: list[Any] = []

        def fake_advise(model: Any) -> dict[str, Any]:
            calls.append(model)
            return _fake_ok_result()

        def fake_original(models, **kwargs):
            return None

        trace = RuntimeTrace(request_id="gpu-once", process="remote")
        wrapper = mp._make_gpu_loader_wrapper(fake_original)
        with patch(
            "comfymodal_runtime.model_preload.advise_storage_pages_willneed",
            side_effect=fake_advise,
        ):
            with mp.request_execution_trace_scope(trace):
                wrapper([patcher], memory_required=0)
                wrapper([patcher], memory_required=0)  # second activation — same request

        assert len(calls) == 1, (
            f"a request must not invoke readiness twice for the same UNET "
            f"activation; got {len(calls)} calls"
        )
        assert calls[0] is patcher

        # Exactly one marker emitted with stage=unet_activation.
        markers = _event_meta(trace, mp._EVENT_UNET_PAGE_READINESS)
        assert len(markers) == 1
        assert markers[0]["stage"] == "unet_activation"
        assert markers[0]["mode"] == _PAGE_READINESS_MODE_WILLNEED
        assert markers[0]["status"] == "ok"
        assert markers[0]["request_id"] == "gpu-once"

    def test_second_request_activates_again_after_cleanup(self) -> None:
        _set_mode("willneed")
        patcher = _registered_unet_patcher()
        advise_calls: list[Any] = []

        def fake_advise(model: Any) -> dict[str, Any]:
            advise_calls.append(model)
            return _fake_ok_result()

        def fake_original(models, **kwargs):
            return None

        wrapper = mp._make_gpu_loader_wrapper(fake_original)

        # Request A: first activation claims the guard.
        trace_a = RuntimeTrace(request_id="req-a", process="remote")
        with patch(
            "comfymodal_runtime.model_preload.advise_storage_pages_willneed",
            side_effect=fake_advise,
        ):
            with mp.request_execution_trace_scope(trace_a):
                wrapper([patcher], memory_required=0)
        assert len(advise_calls) == 1
        assert len(_event_meta(trace_a, mp._EVENT_UNET_PAGE_READINESS)) == 1

        # Cleanup: the existing request finally-block clears the guard.
        mp._unet_page_readiness_clear("req-a")

        # Request B with the same id activates again.
        trace_b = RuntimeTrace(request_id="req-a", process="remote")
        with patch(
            "comfymodal_runtime.model_preload.advise_storage_pages_willneed",
            side_effect=fake_advise,
        ):
            with mp.request_execution_trace_scope(trace_b):
                wrapper([patcher], memory_required=0)
        assert len(advise_calls) == 2, "cleanup must allow re-activation"
        assert len(_event_meta(trace_b, mp._EVENT_UNET_PAGE_READINESS)) == 1

    def test_background_lane_never_invokes_readiness(self) -> None:
        _set_mode("willneed")
        patcher = _registered_unet_patcher()
        advise_calls: list[Any] = []

        def fake_advise(model: Any) -> dict[str, Any]:
            advise_calls.append(model)
            return _fake_ok_result()

        def fake_original(models, **kwargs):
            return None

        trace = RuntimeTrace(request_id="gpu-lane", process="remote")
        lane = mp.ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)
        wrapper = mp._make_gpu_loader_wrapper(fake_original)
        with patch(
            "comfymodal_runtime.model_preload.advise_storage_pages_willneed",
            side_effect=fake_advise,
        ):
            token_lane = mp._ACTIVE_LANE_TRACE.set(lane)
            try:
                with mp.request_execution_trace_scope(trace):
                    wrapper([patcher], memory_required=0)
            finally:
                mp._ACTIVE_LANE_TRACE.reset(token_lane)

        assert advise_calls == [], "restore-time background lanes must never run readiness"
        assert _event_meta(trace, mp._EVENT_UNET_PAGE_READINESS) == []

    def test_non_unet_call_never_invokes_readiness(self) -> None:
        _set_mode("willneed")
        advise_calls: list[Any] = []

        def fake_advise(model: Any) -> dict[str, Any]:
            advise_calls.append(model)
            return _fake_ok_result()

        def fake_original(models, **kwargs):
            return None

        trace = RuntimeTrace(request_id="gpu-nounet", process="remote")
        wrapper = mp._make_gpu_loader_wrapper(fake_original)
        with patch(
            "comfymodal_runtime.model_preload.advise_storage_pages_willneed",
            side_effect=fake_advise,
        ):
            with mp.request_execution_trace_scope(trace):
                wrapper([SimpleNamespace()], memory_required=0)
        assert advise_calls == [], "non-UNET/CLIP calls must never run readiness"

    def test_off_mode_never_invokes_readiness(self) -> None:
        _set_mode("off")
        patcher = _registered_unet_patcher()

        def fake_original(models, **kwargs):
            return None

        trace = RuntimeTrace(request_id="gpu-off", process="remote")
        wrapper = mp._make_gpu_loader_wrapper(fake_original)
        with patch(
            "comfymodal_runtime.model_preload.advise_storage_pages_willneed",
            side_effect=AssertionError("mode off must not call the helper"),
        ), patch(
            "comfymodal_runtime.model_preload._first_registered_unet_model",
            side_effect=AssertionError(
                "mode off must not traverse registered models"
            ),
        ):
            with mp.request_execution_trace_scope(trace):
                wrapper([patcher], memory_required=0)

        assert _event_meta(trace, mp._EVENT_UNET_PAGE_READINESS) == []
        # Default-off must not claim the per-request guard either: nothing is
        # claimed, traversed, or called when the candidate is disabled.
        assert mp._unet_page_readiness_is_done("gpu-off") is False

    def test_wrapper_still_calls_original_once(self) -> None:
        """The readiness candidate must not interfere with the real transfer."""
        _set_mode("willneed")
        patcher = _registered_unet_patcher()
        original_calls: list[tuple] = []

        def fake_original(models, memory_required=0, force_patch_weights=False,
                          minimum_memory_required=None, force_full_load=False):
            original_calls.append((len(models), memory_required))
            return "loaded"

        def fake_advise(model: Any) -> dict[str, Any]:
            return _fake_ok_result()

        trace = RuntimeTrace(request_id="gpu-orig", process="remote")
        wrapper = mp._make_gpu_loader_wrapper(fake_original)
        with patch(
            "comfymodal_runtime.model_preload.advise_storage_pages_willneed",
            side_effect=fake_advise,
        ):
            with mp.request_execution_trace_scope(trace):
                result = wrapper([patcher], memory_required=123)

        assert result == "loaded"
        assert original_calls == [(1, 123)], "original load_models_gpu must run exactly once"


# ── Request guard unit tests ───────────────────────────────────────────────


class TestUnetPageReadinessGuard:
    def teardown_method(self) -> None:
        mp._unet_page_readiness_clear("guard-req")
        for _i in range(1, 7):
            mp._unet_page_readiness_clear(f"guard-{_i}")
        for _i in range(20):
            mp._unet_page_readiness_clear(f"guard-b{_i}")

    def test_claim_once_then_deny(self) -> None:
        assert mp._unet_page_readiness_begin("guard-req") is True
        assert mp._unet_page_readiness_begin("guard-req") is False
        assert mp._unet_page_readiness_is_done("guard-req") is True

    def test_cleanup_allows_reclaim(self) -> None:
        assert mp._unet_page_readiness_begin("guard-req") is True
        mp._unet_page_readiness_clear("guard-req")
        assert mp._unet_page_readiness_is_done("guard-req") is False
        assert mp._unet_page_readiness_begin("guard-req") is True

    def test_empty_request_id_never_claimed(self) -> None:
        assert mp._unet_page_readiness_begin("") is False
        assert mp._unet_page_readiness_is_done("") is False
        mp._unet_page_readiness_clear("")  # no-op, never raises

    def test_bound_evicts_oldest_claims(self) -> None:
        """Claims beyond the bound evict the OLDEST ids (insertion order),
        so request ids that bypass normal request cleanup cannot leak
        forever; an evicted id is claimable again."""
        with patch.object(mp, "_UNET_PAGE_READINESS_DONE_MAX", 3):
            assert mp._unet_page_readiness_begin("guard-1") is True
            assert mp._unet_page_readiness_begin("guard-2") is True
            assert mp._unet_page_readiness_begin("guard-3") is True
            # Bound reached: the next claim evicts the oldest (guard-1).
            assert mp._unet_page_readiness_begin("guard-4") is True
            assert mp._unet_page_readiness_is_done("guard-1") is False
            assert mp._unet_page_readiness_is_done("guard-2") is True
            assert mp._unet_page_readiness_is_done("guard-3") is True
            assert mp._unet_page_readiness_is_done("guard-4") is True
            # The evicted id is no longer sticky: it can be claimed again,
            # and the now-oldest (guard-2) is evicted in its place.
            assert mp._unet_page_readiness_begin("guard-1") is True
            assert mp._unet_page_readiness_is_done("guard-2") is False
            assert mp._unet_page_readiness_is_done("guard-1") is True

    def test_bound_never_exceeded_even_without_cleanup(self) -> None:
        """Even when request ids never pass through the normal cleanup
        path, the guard map stays bounded (oldest-first eviction)."""
        with patch.object(mp, "_UNET_PAGE_READINESS_DONE_MAX", 4):
            for _i in range(20):
                assert mp._unet_page_readiness_begin(f"guard-b{_i}") is True
            with mp._UNET_PAGE_READINESS_LOCK:
                assert len(mp._UNET_PAGE_READINESS_DONE) <= 4
            # The most recently claimed ids survive; the oldest are gone.
            assert mp._unet_page_readiness_is_done("guard-b19") is True
            assert mp._unet_page_readiness_is_done("guard-b0") is False

    def test_bound_preserves_claim_once_semantics(self) -> None:
        """Claim-once / normal-clear semantics are unchanged under the bound."""
        with patch.object(mp, "_UNET_PAGE_READINESS_DONE_MAX", 3):
            assert mp._unet_page_readiness_begin("guard-5") is True
            assert mp._unet_page_readiness_begin("guard-5") is False
            assert mp._unet_page_readiness_begin("guard-6") is True
            assert mp._unet_page_readiness_begin("guard-5") is False
            # Normal request cleanup still clears the entry for re-claim.
            mp._unet_page_readiness_clear("guard-5")
            assert mp._unet_page_readiness_is_done("guard-5") is False
            assert mp._unet_page_readiness_begin("guard-5") is True


# ── Reconciliation builder stage attribution ───────────────────────────────


class _FakeEvent:
    def __init__(self, name: str, mono_ns: int, metadata: dict[str, Any] | None = None) -> None:
        self.name = name
        self.monotonic_ns = mono_ns
        self.metadata = metadata or {}


class _FakeTrace:
    def __init__(self, events: list[_FakeEvent]) -> None:
        self.events = events


class TestReconciliationPageReadinessStage:
    def test_page_readiness_is_explicit_stage_when_applied(self) -> None:
        # Values in nanoseconds (1_000_000 == 1 ms).
        trace = _FakeTrace([
            _FakeEvent(mp._EVENT_SUBMISSION, 0),
            _FakeEvent(mp._EVENT_WORKER_START, 0),
            _FakeEvent(mp._EVENT_READINESS_START, 1_000_000),
            _FakeEvent(mp._EVENT_READINESS_END, 2_000_000),
            _FakeEvent(mp._EVENT_PAGE_READINESS_START, 2_000_000),
            _FakeEvent(
                mp._EVENT_PAGE_READINESS_END, 5_000_000,
                {"mode": "willneed", "status": "ok", "wall_ms": 3.0,
                 "storage_count": 2, "range_count": 2, "total_bytes": 8192,
                 "total_pages": 2, "advised_pages": 2, "advised_bytes": 8192,
                 "advised_percent": 100.0, "major_faults": 0, "minor_faults": 1,
                 "error_reason": ""},
            ),
            _FakeEvent(mp._EVENT_ENCODE_START, 5_000_000),
            _FakeEvent(mp._EVENT_ENCODE_END, 6_000_000),
            _FakeEvent(mp._EVENT_COMPLETED, 7_000_000, {"encoded_count": 1}),
        ])
        record = mp.build_clip_prefill_reconciliation(
            trace, outcome="consumed", request_id="pr-stage"
        )
        assert record["page_readiness_applied"] is True
        assert record["page_readiness_ms"] == 3.0
        assert record["page_readiness"]["status"] == "ok"
        # Honest advised_* counts flow through the reconciliation record.
        assert record["page_readiness"]["advised_pages"] == 2
        assert record["page_readiness"]["advised_bytes"] == 8192
        assert record["page_readiness"]["advised_percent"] == 100.0
        # children explicitly include the readiness stage — not shifted to residual.
        children = (
            record["queue_ms"] + record["readiness_ms"]
            + record["page_readiness_ms"] + record["encode_ms"]
            + record["completion_ms"]
        )
        assert abs(record["prefill_total_ms"] - children - record["unattributed_ms"]) < 0.01
        assert record["reconciliation_status"] == "complete"

    def test_page_readiness_absent_when_not_applied(self) -> None:
        trace = _FakeTrace([
            _FakeEvent(mp._EVENT_SUBMISSION, 0),
            _FakeEvent(mp._EVENT_WORKER_START, 0),
            _FakeEvent(mp._EVENT_READINESS_START, 1_000_000),
            _FakeEvent(mp._EVENT_READINESS_END, 2_000_000),
            _FakeEvent(mp._EVENT_ENCODE_START, 2_000_000),
            _FakeEvent(mp._EVENT_ENCODE_END, 3_000_000),
            _FakeEvent(mp._EVENT_COMPLETED, 4_000_000, {"encoded_count": 1}),
        ])
        record = mp.build_clip_prefill_reconciliation(
            trace, outcome="consumed", request_id="pr-no-stage"
        )
        assert record["page_readiness_applied"] is False
        assert record["page_readiness_ms"] is None
        assert record["page_readiness"] == {}
        # Default (mode off) still reconciles as complete without the stage.
        assert record["reconciliation_status"] == "complete"
