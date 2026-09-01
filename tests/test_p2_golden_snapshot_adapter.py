"""Focused P2-2 Golden snapshot/adapter checks.

These tests exercise the small adapter seams with fakes.  They do not start
ComfyUI, load models, or invoke CUDA.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from comfymodal_runtime import modal_app
from comfymodal_runtime import golden_serial
from comfymodal_runtime import clip_conditioning_cache
from comfymodal_runtime import snapshot_capture_hygiene
from comfymodal_runtime.trace import RuntimeTrace


def test_golden_gate_uses_dynamic_flag_or_profile(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM", raising=False)
    monkeypatch.delenv("COMFYMODAL_V2CTL_PROFILE", raising=False)
    assert modal_app._golden_serial_profile_active() is False

    monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM", "yes")
    assert modal_app._golden_serial_profile_active() is True

    monkeypatch.setenv("COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM", "0")
    monkeypatch.setenv("COMFYMODAL_V2CTL_PROFILE", " golden_p1 ")
    assert modal_app._golden_serial_profile_active() is True


def test_startup_source_keeps_non_golden_cpu_snapshot_gate_and_golden_bypass():
    source = Path(modal_app.__file__).read_text(encoding="utf-8")
    golden_branch = source.index("if _golden_serial_active:")
    cpu_gate = source.index("elif _cpu_model_snapshot_enabled():", golden_branch)
    assert source.index("_clear_cpu_snapshot_state_for_golden()", golden_branch) < cpu_gate
    surfaces = source.index("_golden_pre_capture_surfaces = self._golden_snapshot_proof_surfaces()", golden_branch)
    assert source.index("_clear_cpu_snapshot_state_for_golden()", golden_branch) < surfaces
    assert source.index("self._run_golden_snapshot_content_proof(") > cpu_gate


def test_golden_snapshot_quiescence_uses_passive_adapter():
    source = Path(snapshot_capture_hygiene.__file__).read_text(encoding="utf-8")
    modal_source = Path(modal_app.__file__).read_text(encoding="utf-8")
    assert "inspect_for_snapshot" in source
    assert "quiesce_for_snapshot(timeout_s=timeout_s)" in source
    assert "prove_snapshot_quiescence(passive=True)" in modal_source


def test_passive_snapshot_quiescence_does_not_call_mutating_cache_path(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        clip_conditioning_cache,
        "inspect_for_snapshot",
        lambda: calls.append("inspect") or {
            "quiesced": True,
            "details": [],
        },
    )
    monkeypatch.setattr(
        clip_conditioning_cache,
        "quiesce_for_snapshot",
        lambda **_kwargs: calls.append("quiesce") or {"quiesced": False},
    )
    monkeypatch.setattr(
        "comfymodal_runtime.snapshot_build_manifest.enumerate_registered_executors",
        lambda: [],
    )

    proof = snapshot_capture_hygiene.prove_snapshot_quiescence(passive=True)

    assert proof["proven"] is True
    assert proof["passive"] is True
    assert calls == ["inspect"]


def test_non_golden_snapshot_proof_default_still_uses_mutating_cache_path(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        clip_conditioning_cache,
        "inspect_for_snapshot",
        lambda: calls.append("inspect") or {"quiesced": True},
    )
    monkeypatch.setattr(
        clip_conditioning_cache,
        "quiesce_for_snapshot",
        lambda **_kwargs: calls.append("quiesce") or {
            "quiesced": True,
            "details": [],
        },
    )
    monkeypatch.setattr(
        "comfymodal_runtime.snapshot_build_manifest.enumerate_registered_executors",
        lambda: [],
    )

    proof = snapshot_capture_hygiene.prove_snapshot_quiescence()

    assert proof["proven"] is True
    assert proof["passive"] is False
    assert calls == ["quiesce"]


def test_cache_passive_inspection_is_state_preserving(tmp_path):
    cache = clip_conditioning_cache.ExactConditioningCache(
        root_dir=str(tmp_path), max_entries=4, max_bytes=1024, mounted=False
    )
    before = {
        "snapshot_quiescing": cache._snapshot_quiescing,
        "closing": cache._closing,
        "lru_closing": cache._lru_closing,
        "pending": list(cache._pending),
        "pending_lru": set(cache._pending_lru),
        "prefetch_events": dict(cache._prefetch_events),
    }

    result = cache.inspect_for_snapshot()

    assert result["quiesced"] is True
    assert cache._snapshot_quiescing is before["snapshot_quiescing"]
    assert cache._closing is before["closing"]
    assert cache._lru_closing is before["lru_closing"]
    assert list(cache._pending) == before["pending"]
    assert cache._pending_lru == before["pending_lru"]
    assert cache._prefetch_events == before["prefetch_events"]


def test_cache_passive_inspection_fails_closed_for_live_worker(tmp_path):
    cache = clip_conditioning_cache.ExactConditioningCache(
        root_dir=str(tmp_path), max_entries=4, max_bytes=1024, mounted=False
    )
    cast(Any, cache)._worker = SimpleNamespace(is_alive=lambda: True)

    result = cache.inspect_for_snapshot()

    assert result["quiesced"] is False
    assert "persistence worker is still alive" in result["details"]
    assert cache._snapshot_quiescing is False
    assert cache._closing is False


def test_golden_state_clear_drops_snapshot_model_references():
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._cpu_snapshot_models = cast(Any, object())
    entrypoint._snapshot_eviction_retained_model = object()
    entrypoint._cpu_snapshot_models_active = True
    entrypoint._clear_cpu_snapshot_state_for_golden()
    assert entrypoint._cpu_snapshot_models is None
    assert entrypoint._snapshot_eviction_retained_model is None
    assert entrypoint._cpu_snapshot_models_active is False


def test_golden_restore_rejects_snapshot_model_residue():
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._cpu_snapshot_models = cast(Any, object())
    with pytest.raises(RuntimeError, match="golden_restore_model_residue"):
        entrypoint._assert_golden_restore_model_free()


def test_golden_execution_rejects_preload_residue():
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._preload_bridge._preparation = cast(Any, object())
    with pytest.raises(RuntimeError, match="golden_preload_state_forbidden"):
        entrypoint._assert_golden_execution_isolated()


def test_pre_capture_proof_is_recorded_and_errors_fail_closed(monkeypatch, tmp_path):
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_api = SimpleNamespace(real_surface=True)
    entrypoint._restore_timing = {}
    monkeypatch.setattr(modal_app, "RUNTIME_STATE_PATH", str(tmp_path))

    calls = []

    def clean_proof(**kwargs):
        calls.append(kwargs)
        assert entrypoint._legacy_api in kwargs["roots"]
        assert kwargs["snapshot_size_bytes"] == 123 * 1024
        assert kwargs["snapshot_size_source"] == golden_serial.SNAPSHOT_SIZE_SOURCE
        assert kwargs["snapshot_size_is_serialized"] is False
        return {
            "schema": "golden_snapshot_content_proof_v1",
            "passive": True,
            "surface_count": 1,
            "snapshot_size_bytes": kwargs["snapshot_size_bytes"],
            "snapshot_size_source": kwargs["snapshot_size_source"],
            "snapshot_size_is_serialized": False,
            "tensor_count": 0,
            "parameter_bytes": 0,
            "model_patcher_count": 0,
            "qd_owner_count": 0,
            "open_payload_reader_count": 0,
            "preload_worker_count": 0,
            "future_count": 0,
            "nonzero": {},
            "nonzero_roles": {},
        }

    monkeypatch.setattr(
        "comfymodal_runtime.snapshot_capture_hygiene.read_process_status_fields",
        lambda: {"rss_kb": 123},
    )
    monkeypatch.setattr(golden_serial, "golden_snapshot_content_proof", clean_proof)
    trace = RuntimeTrace(process="remote")
    proof = entrypoint._run_golden_snapshot_content_proof(trace=trace)
    assert calls and proof["proven"] is True
    assert calls[0]["persist_path"] == str(tmp_path / "golden_snapshot_content_proof.json")
    assert entrypoint._restore_timing["golden_snapshot_content_proof"] == proof
    assert trace.to_dict()["metadata"]["golden_snapshot_content_proof"] == proof

    def failing_proof(**_kwargs):
        raise RuntimeError("contaminated")

    monkeypatch.setattr(golden_serial, "golden_snapshot_content_proof", failing_proof)
    with pytest.raises(RuntimeError, match="golden snapshot content proof failed"):
        entrypoint._run_golden_snapshot_content_proof(trace=trace)
    assert entrypoint._restore_timing["golden_snapshot_content_proof"]["proven"] is False


def test_pre_capture_proof_rejects_incomplete_result(monkeypatch):
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_api = SimpleNamespace(real_surface=True)
    entrypoint._restore_timing = {}

    monkeypatch.setattr(
        golden_serial,
        "golden_snapshot_content_proof",
        lambda **_kwargs: {"schema": "golden_snapshot_content_proof_v1", "passive": True},
    )
    with pytest.raises(RuntimeError, match="golden snapshot content proof failed"):
        entrypoint._run_golden_snapshot_content_proof()


@pytest.mark.parametrize("rss_kb", [None, 0, True, "123"])
def test_pre_capture_proof_fails_closed_when_process_rss_is_invalid(monkeypatch, rss_kb):
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_api = SimpleNamespace(real_surface=True)
    entrypoint._restore_timing = {}
    monkeypatch.setattr(
        "comfymodal_runtime.snapshot_capture_hygiene.read_process_status_fields",
        lambda: {"rss_kb": rss_kb},
    )
    with pytest.raises(RuntimeError, match="golden snapshot content proof failed"):
        entrypoint._run_golden_snapshot_content_proof()
    failure = entrypoint._restore_timing["golden_snapshot_content_proof"]
    assert failure["snapshot_size_source"] == golden_serial.SNAPSHOT_SIZE_SOURCE
    assert failure["snapshot_size_is_serialized"] is False


def test_pre_capture_proof_fails_closed_at_snapshot_size_limit(monkeypatch):
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_api = SimpleNamespace(real_surface=True)
    entrypoint._restore_timing = {}
    limit = golden_serial.GOLDEN_SNAPSHOT_SIZE_LIMIT_BYTES
    monkeypatch.setattr(
        "comfymodal_runtime.snapshot_capture_hygiene.read_process_status_fields",
        lambda: {"rss_kb": limit // 1024},
    )
    with pytest.raises(RuntimeError, match="golden snapshot content proof failed"):
        entrypoint._run_golden_snapshot_content_proof()
    assert "process_rss_limit" in entrypoint._restore_timing[
        "golden_snapshot_content_proof"
    ]["error"]


def test_adapter_passes_mount_restore_metadata_and_terminal_timestamps(monkeypatch, tmp_path, capsys):
    volume = object()
    monkeypatch.setitem(modal_app._MODAL_RESOURCES, "runtime_state_volume", volume)
    monkeypatch.setattr(modal_app, "RUNTIME_STATE_PATH", str(tmp_path))
    monkeypatch.setattr(
        "comfymodal_runtime.golden_aimdo_activation.activate_golden_dynamic_vram",
        lambda: {"activated": True, "already_activated": False, "is_dynamic_alias": True},
    )
    installed_nodes = SimpleNamespace(NODE_CLASS_MAPPINGS={"X": object()})
    monkeypatch.setitem(sys.modules, "nodes", installed_nodes)

    entrypoint = modal_app.ModalRuntimeEntrypoint()
    # Golden request entry requires the already-restored API's explicit GPU
    # readiness seam before activation or delegation.
    entrypoint._legacy_api = SimpleNamespace(
        _ensure_gpu_ready_for_request=lambda: None,
    )
    restore_metadata = {
        "remote_python_resume_wall_unix_ns": 100,
        "remote_python_resume_mono_ns": 100,
        "restore_method_start_wall_unix_ns": 100,
        "restore_method_start_mono_ns": 100,
        "restore_method_end_wall_unix_ns": 200,
        "restore_method_end_mono_ns": 200,
        "restore_method_status": "success",
    }
    entrypoint._restore_timing = restore_metadata
    calls = []

    async def fake_execute(request, **kwargs):
        calls.append((request, kwargs))
        Path(kwargs["telemetry_path"]).write_text(
            json.dumps({
                "schema": "golden_p1_telemetry_v1",
                "external_restore": {"restore_total_ms": 12.5},
                "stages": [
                    {
                        "name": "golden_request_setup",
                        "entry_monotonic_ns": 1,
                        "end_monotonic_ns": 2,
                        "ok": True,
                    },
                    {
                        "name": "golden_clip_forward",
                        "entry_monotonic_ns": 2,
                        "end_monotonic_ns": 4,
                        "ok": True,
                    },
                    {
                        "name": "golden_sampling",
                        "entry_monotonic_ns": 4,
                        "end_monotonic_ns": 7,
                        "ok": True,
                    },
                    {
                        "name": "golden_teardown",
                        "entry_monotonic_ns": 8,
                        "end_monotonic_ns": 10,
                        "end_wall_ns": 10,
                        "ok": True,
                    },
                ],
                "events": [{
                    "name": "TEARDOWN_COMPLETE",
                    "monotonic_ns": 11,
                    "wall_ns": 11,
                    "fields": {"request_id": request.request_id},
                }],
            }),
            encoding="utf-8",
        )
        return golden_serial.GoldenFinalResult(
            request_id=request.request_id,
            image_sha256="a" * 64,
            asset_path="out.png",
            volume_rel_path="golden/out.png",
            true_durable=True,
            seriality_violation_count=0,
            executed_nodes=[],
        )

    monkeypatch.setattr(golden_serial, "golden_serial_execute", fake_execute)
    monkeypatch.setattr(
        modal_app,
        "_emit_golden_telemetry",
        lambda *_args, **_kwargs: pytest.fail("Golden adapter must not emit telemetry"),
    )

    async def collect():
        return [
            event
            async for event in entrypoint.run_golden_serial_stream(
                {"request_id": "p2", "prompt": {"1": {"class_type": "X"}}}
            )
        ]

    events = asyncio.run(collect())
    assert len(calls) == 1
    kwargs = calls[0][1]
    assert kwargs["volume"] is volume
    assert kwargs["volume_mount_root"] == str(tmp_path)
    assert kwargs["restore_metadata"] == restore_metadata
    assert kwargs["node_classes"] is installed_nodes.NODE_CLASS_MAPPINGS

    terminal = next(event["data"]["terminal"] for event in events if event["type"] == "result")
    for key in (
        "return_wall_unix_ns",
        "return_mono_ns",
        "yield_wall_unix_ns",
        "yield_mono_ns",
    ):
        assert isinstance(terminal[key], int)
    assert terminal["return_mono_ns"] <= terminal["yield_mono_ns"]
    telemetry = next(event["data"]["golden_telemetry"] for event in events if event["type"] == "result")
    assert (tmp_path / "golden" / "p2.json").is_file()
    assert json.loads((tmp_path / "golden" / "p2.json").read_text()) == telemetry
    teardown = next(stage for stage in telemetry["stages"] if stage["name"] == "golden_teardown")
    teardown_complete = next(
        event for event in telemetry["events"] if event["name"] == "TEARDOWN_COMPLETE"
    )
    assert teardown["end_monotonic_ns"] <= teardown_complete["monotonic_ns"]
    output = capsys.readouterr().out
    assert "V2 GOLDEN WATERFALL - REMOTE" in output
    assert output.count("V2 GOLDEN WATERFALL - REMOTE") == 1
    assert "golden_request_setup [GOLDEN STAGE]" in output
    assert "golden_clip_forward [GOLDEN STAGE]" in output
    assert "golden_sampling [GOLDEN STAGE]" in output
    assert "V2 COLD WATERFALL - REMOTE" not in output
    assert "V2 COLD WATERFALL - REMOTE/PARTIAL" not in output
    assert "[v2.golden_telemetry]" not in output
    assert [event["name"] for event in telemetry["events"]] == ["TEARDOWN_COMPLETE"]
    assert "adapter_completion" not in telemetry


def test_golden_telemetry_log_format_is_complete_bounded_and_redacts_prompt(capsys):
    telemetry = {
        "schema": "golden_p1_telemetry_v1",
        "true_durable_marked": False,
        "seriality": {"ok": True, "count": 0},
        "external_restore": {"restore_method_status": "success"},
        "stages": [
            {
                "name": "golden_request_setup",
                "entry_monotonic_ns": 100,
                "end_monotonic_ns": 250,
                "ok": True,
                "details": {"node_count": 6, "prompt_text": "do not print me"},
            },
            {
                "name": "golden_sampling",
                "entry_monotonic_ns": 300,
                "end_monotonic_ns": None,
                "ok": False,
                "details": {"error": "RuntimeError: sampler failed"},
            },
        ],
        "events": [{
            "name": "SAMPLER_FAILED",
            "fields": {"step": 3, "secret_token": "do not print me either"},
        }],
    }

    modal_app._emit_golden_telemetry(telemetry)
    output = capsys.readouterr().out
    assert "stage=golden_request_setup duration_ms=0.0 ok=true" in output
    assert "stage=golden_sampling duration_ms=incomplete ok=false" in output
    assert "event=SAMPLER_FAILED" in output
    assert '"step":3' in output
    assert "do not print me" not in output
    assert "<redacted>" in output


def test_golden_telemetry_log_includes_remote_waterfall_and_boundary_timing(capsys):
    telemetry = {
        "external_restore": {"restore_total_ms": 75.0},
        "stages": [
            {
                "name": "golden_request_setup",
                "entry_monotonic_ns": 100_000_000,
                "end_monotonic_ns": 250_000_000,
                "ok": True,
            },
            {
                "name": "golden_sampling",
                "entry_monotonic_ns": 300_000_000,
                "end_monotonic_ns": 500_000_000,
                "ok": False,
            },
            {"name": "golden_output", "entry_monotonic_ns": 600_000_000, "ok": None},
        ],
    }
    timing = {
        "golden_call_wall_ms": 800.0,
        "golden_stage_span_ms": 400.0,
        "golden_stage_sum_ms": 350.0,
        "golden_pre_stage_overhead_ms": 20.0,
        "golden_post_stage_overhead_ms": 430.0,
        "golden_telemetry_persist_ms": 1.25,
    }

    modal_app._emit_golden_telemetry(telemetry, timing=timing)
    output = capsys.readouterr().out
    assert "V2 GOLDEN WATERFALL - REMOTE" in output
    assert "|   # | Stage" in output
    assert "External restore [ADAPTER BOUNDARY]" in output
    assert "golden_request_setup [GOLDEN STAGE]" in output
    assert "150.000 ms" in output
    assert "350.000 ms" in output
    assert "FAILED" in output
    assert "golden_output [GOLDEN STAGE]" in output
    assert "N/A" in output
    assert "V2 GOLDEN BOUNDARIES / TIMING" in output
    assert "Golden call wall [ADAPTER CALL]" in output
    assert "Golden stage span [GOLDEN STAGES]" in output
    assert "Pre-stage overhead [ADAPTER]" in output
    assert "Post-stage overhead [ADAPTER]" in output
    assert "Telemetry persistence [ADAPTER]" in output


def test_golden_adapter_terminal_paths_do_not_emit_telemetry_block():
    source = Path(modal_app.__file__).read_text(encoding="utf-8")
    start = source.index("    async def run_golden_serial_stream(")
    end = source.index("    async def run_prompt_stream(", start)
    assert "_emit_golden_telemetry(" not in source[start:end]
    assert "_emit_golden_waterfall(" in source[start:end]


def test_adapter_failure_propagates_persisted_telemetry_and_timing(monkeypatch, tmp_path, capsys):
    volume = object()
    monkeypatch.setitem(modal_app._MODAL_RESOURCES, "runtime_state_volume", volume)
    monkeypatch.setattr(modal_app, "RUNTIME_STATE_PATH", str(tmp_path))
    monkeypatch.setattr(
        "comfymodal_runtime.golden_aimdo_activation.activate_golden_dynamic_vram",
        lambda: {"activated": True, "already_activated": False, "is_dynamic_alias": True},
    )
    monkeypatch.setitem(sys.modules, "nodes", SimpleNamespace(NODE_CLASS_MAPPINGS={"X": object()}))
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_api = SimpleNamespace(_ensure_gpu_ready_for_request=lambda: None)
    entrypoint._restore_timing = {
        "remote_python_resume_wall_unix_ns": 100,
        "remote_python_resume_mono_ns": 100,
        "restore_method_start_wall_unix_ns": 100,
        "restore_method_start_mono_ns": 100,
        "restore_method_end_wall_unix_ns": 200,
        "restore_method_end_mono_ns": 200,
        "restore_method_status": "success",
    }
    persisted = {
        "schema": "golden_p1_telemetry_v1",
        "stages": [{
            "name": "golden_sampling",
            "entry_monotonic_ns": 1000,
            "end_monotonic_ns": 2500,
            "ok": False,
            "details": {"error": "sampler failed"},
        }],
        "events": [{"name": "SAMPLER_FAILED", "fields": {"step": 4}}],
        "seriality": {"ok": True, "violations": [], "count": 0},
    }

    async def fail_after_persist(request, *, telemetry_path, **_kwargs):
        Path(telemetry_path).write_text(json.dumps(persisted), encoding="utf-8")
        raise RuntimeError("primary-golden-error")

    monkeypatch.setattr(golden_serial, "golden_serial_execute", fail_after_persist)
    monkeypatch.setattr(
        modal_app,
        "_emit_golden_telemetry",
        lambda *_args, **_kwargs: pytest.fail("Golden adapter must not emit telemetry"),
    )

    async def collect():
        return [
            event
            async for event in entrypoint.run_golden_serial_stream(
                {"request_id": "failed", "prompt": {"1": {"class_type": "X"}}}
            )
        ]

    events = asyncio.run(collect())
    assert len(events) == 1
    error = events[0]
    assert error["type"] == "error"
    assert "primary-golden-error" in error["message"]
    assert error["golden_telemetry"] == persisted
    timing = error["golden_adapter_timing"]
    assert timing["golden_call_wall_ms"] is not None
    assert timing["golden_stage_span_ms"] == pytest.approx(0.002)
    assert timing["golden_stage_sum_ms"] == pytest.approx(0.002)
    assert timing["golden_telemetry_persist_ms"] is None
    output = capsys.readouterr().out
    assert "V2 GOLDEN WATERFALL - REMOTE" in output
    assert "golden_sampling [GOLDEN STAGE]" in output
    assert "V2 COLD WATERFALL - REMOTE" not in output
    assert "[v2.golden_telemetry]" not in output


def test_cache_peek_does_not_initialize_or_log(monkeypatch):
    monkeypatch.setattr(clip_conditioning_cache, "_SINGLETON", None)
    monkeypatch.setattr(clip_conditioning_cache, "_SINGLETON_RESOLVED", False)
    monkeypatch.setattr(
        clip_conditioning_cache,
        "ExactConditioningCache",
        lambda **_kwargs: pytest.fail("peek must not construct the cache"),
    )
    monkeypatch.setattr(
        clip_conditioning_cache,
        "_log_once",
        lambda *_args, **_kwargs: pytest.fail("peek must not log"),
    )
    monkeypatch.setattr(
        clip_conditioning_cache,
        "env_flag",
        lambda *_args, **_kwargs: pytest.fail("peek must not resolve the environment"),
    )

    assert clip_conditioning_cache.peek_exact_conditioning_cache() is None


def test_cache_peek_returns_an_existing_resolved_service(monkeypatch):
    cache = object()
    monkeypatch.setattr(clip_conditioning_cache, "_SINGLETON", cache)
    monkeypatch.setattr(clip_conditioning_cache, "_SINGLETON_RESOLVED", True)

    assert clip_conditioning_cache.peek_exact_conditioning_cache() is cache


def test_exit_flushes_only_an_already_resolved_cache(monkeypatch):
    flush_calls = []

    class ExistingCache:
        def flush(self, *, timeout):
            flush_calls.append(timeout)

    cache = ExistingCache()
    monkeypatch.setattr(clip_conditioning_cache, "_SINGLETON", cache)
    monkeypatch.setattr(clip_conditioning_cache, "_SINGLETON_RESOLVED", True)
    monkeypatch.setattr(
        clip_conditioning_cache,
        "get_exact_conditioning_cache",
        lambda: pytest.fail("exit must not initialize the cache"),
    )

    entrypoint = modal_app.ModalRuntimeEntrypoint()
    cast(Any, entrypoint)._teardown_diagnostics = None
    monkeypatch.setattr(entrypoint, "_lazy_init_snapshot_state", lambda: None)

    def run_stage(name, callback):
        if name == "conditioning_cache_flush":
            callback()

    monkeypatch.setattr(entrypoint, "_run_teardown_stage", run_stage)
    entrypoint.exit()

    assert flush_calls == [modal_app._PRELOAD_WORKER_JOIN_BUDGET_S]


def test_adapter_rejects_runtime_mount_identity_mismatch(monkeypatch, tmp_path):
    class MismatchedVolume:
        volume_mount_root = str(tmp_path / "other")

    with pytest.raises(RuntimeError, match="golden_runtime_mount_root_identity_mismatch"):
        modal_app._validate_golden_runtime_mount_root(MismatchedVolume())


def test_adapter_rejects_missing_restore_metadata(monkeypatch, tmp_path):
    monkeypatch.setitem(modal_app._MODAL_RESOURCES, "runtime_state_volume", object())
    monkeypatch.setattr(modal_app, "RUNTIME_STATE_PATH", str(tmp_path))
    entrypoint = modal_app.ModalRuntimeEntrypoint()

    async def collect():
        return [
            event
            async for event in entrypoint.run_golden_serial_stream(
                {"request_id": "missing-meta", "prompt": {"1": {"class_type": "X"}}}
            )
        ]

    events = asyncio.run(collect())
    assert events and events[0]["type"] == "error"
    assert "golden_restore_metadata_missing" in events[0]["message"]


def test_adapter_rejects_contract_override(monkeypatch, tmp_path):
    monkeypatch.setitem(modal_app._MODAL_RESOURCES, "runtime_state_volume", object())
    monkeypatch.setattr(modal_app, "RUNTIME_STATE_PATH", str(tmp_path))
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._restore_timing = {
        "remote_python_resume_wall_unix_ns": 100,
        "remote_python_resume_mono_ns": 100,
        "restore_method_start_wall_unix_ns": 100,
        "restore_method_start_mono_ns": 100,
        "restore_method_end_wall_unix_ns": 200,
        "restore_method_end_mono_ns": 200,
        "restore_method_status": "success",
    }

    async def collect():
        return [
            event
            async for event in entrypoint.run_golden_serial_stream(
                {
                    "request_id": "contract-override",
                    "prompt": {"1": {"class_type": "X"}},
                    "contract": {"workflow_sha256": "0" * 64},
                }
            )
        ]

    events = asyncio.run(collect())
    assert events and events[0]["type"] == "error"
    assert "golden_contract_override_not_allowed" in events[0]["message"]
