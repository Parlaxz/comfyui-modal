"""Focused tests for low-perturbation Golden runtime composition telemetry."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

from comfymodal_runtime import modal_app
from comfymodal_runtime import restore_state_probe as probe
from comfymodal_runtime.runtime_bootstrap import BootstrapConfig, RuntimeBootstrap
from comfymodal_runtime.trace import RuntimeTrace
from comfymodal_runtime.trace import merge_runtime_traces


FAKE_SMAPS = """\
7f0000000000-7f0000001000 r--p 00000000 00:00 1 /usr/lib/libcudart.so.12
Size:                  4 kB
Rss:                   3 kB
Pss:                   2 kB
Private_Clean:         1 kB
7f0000010000-7f0000020000 rw-p 00000000 00:00 0 [stack:42]
Size:                 64 kB
Rss:                  20 kB
Pss:                  10 kB
"""


def test_bounded_smaps_aggregates_categories_and_largest_mappings():
    result = probe._parse_bounded_smaps(FAKE_SMAPS)

    assert result["available"] is True
    assert result["native_library_resident_bytes"] == 3 * 1024
    assert result["cuda_runtime_host_mapped_bytes"] == 3 * 1024
    assert result["file_backed_resident_bytes"] == 3 * 1024
    assert result["thread_stack_resident_bytes"] == 20 * 1024
    assert result["largest_mappings"][0]["resident_bytes"] == 20 * 1024


def test_process_probe_keeps_unavailable_fields_explicit_and_rollup_is_single_read(monkeypatch):
    reads: list[str] = []

    def fake_proc(name: str):
        reads.append(name)
        if name == "smaps_rollup":
            return "Rss: 100 kB\nPss: 60 kB\nPrivate_Clean: 10 kB\nPrivate_Dirty: 20 kB\n"
        return None

    monkeypatch.setattr(probe, "_proc_self_file", fake_proc)
    monkeypatch.setattr(probe, "_read_text", lambda *_args, **_kwargs: None)
    result = probe.probe_process_memory(include_smaps=False)

    assert reads.count("smaps_rollup") == 1
    assert result["rss_bytes"] == 100 * 1024
    assert result["pss_bytes"] == 60 * 1024
    assert result["uss_status"] == "approximate_private_clean_plus_dirty"
    assert result["uss_bytes"] == 30 * 1024
    assert result["file_backed_resident_bytes"] is None
    assert result["native_library_resident_bytes"] is None
    assert result["thread_stack_resident_bytes"] is None


def test_bounded_smaps_truncation_is_partial_for_all_categories(monkeypatch):
    bounded_calls: list[tuple[str, int]] = []

    def fake_bounded(name: str, max_bytes: int):
        bounded_calls.append((name, max_bytes))
        return FAKE_SMAPS, True

    def fake_proc(name: str):
        if name == "smaps_rollup":
            return "Rss: 100 kB\nPss: 60 kB\n"
        return None

    monkeypatch.setattr(probe, "_proc_self_file", fake_proc)
    monkeypatch.setattr(probe, "_proc_self_file_bounded", fake_bounded)
    monkeypatch.setattr(probe, "_read_text", lambda *_args, **_kwargs: None)

    result = probe.probe_process_memory(
        include_smaps=True,
        max_smaps_bytes=4096,
        max_smaps_mappings=2,
    )

    assert bounded_calls == [("smaps", 4096)]
    assert result["smaps"]["status"] == "partial"
    assert "byte_limit" in result["smaps"]["partial_reasons"]
    for key in (
        "native_library_resident_status",
        "cuda_runtime_host_mapped_status",
        "file_backed_resident_status",
        "custom_node_resident_status",
        "thread_stack_resident_status",
    ):
        assert result["smaps"].get(key) == "partial"
        assert result.get(key) == "partial"

    mapping_limited = probe._parse_bounded_smaps(
        FAKE_SMAPS,
        max_mappings=1,
        max_bytes=4096,
    )
    assert mapping_limited["partial"] is True
    assert "mapping_limit" in mapping_limited["partial_reasons"]
    assert mapping_limited["native_library_resident_status"] == "partial"


def test_runtime_probe_is_json_safe_and_serialized_size_is_not_inferred(monkeypatch):
    monkeypatch.setattr(
        probe,
        "probe_process_memory",
        lambda **_kwargs: {
            "rss_bytes": 123,
            "pss_bytes": 100,
            "uss_bytes": None,
            "smaps": {"available": False},
        },
    )
    result = probe.capture_runtime_memory("before_capture", extra={"object": object()})

    json.dumps(result)
    assert result["stage"] == "before_capture"
    assert result["serialized_snapshot_size_bytes"] is None
    assert result["serialized_snapshot_size_status"] == "unavailable"


def test_runtime_probe_does_not_probe_cuda_or_start_tracemalloc(monkeypatch):
    calls: list[str] = []

    def forbidden(*_args, **_kwargs):
        calls.append("forbidden")
        raise AssertionError("CUDA probe has side effects")

    fake_cuda = SimpleNamespace(is_initialized=lambda: False, is_available=forbidden)
    fake_torch = SimpleNamespace(cuda=fake_cuda)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.delitem(sys.modules, "tracemalloc", raising=False)
    monkeypatch.setattr(
        probe,
        "probe_process_memory",
        lambda **_kwargs: {"smaps": {"available": False}},
    )

    result = probe.capture_runtime_memory("restore")

    assert calls == []
    assert result["cuda"]["cuda_context_initialized"] is False
    assert result["python_heap"]["tracemalloc_tracing"] is False


def test_canonical_bootstrap_lifecycle_invokes_runtime_memory_callback(tmp_path, monkeypatch):
    calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        "comfymodal_runtime.runtime_bootstrap.ensure_models_symlink",
        lambda *_args: "unused",
    )

    def capture(stage, *, trace=None, metadata=None):
        calls.append((stage, dict(metadata or {})))

    bootstrap = RuntimeBootstrap(
        BootstrapConfig(
            comfyui_root=str(tmp_path / "comfy"),
            models_path=str(tmp_path / "models"),
            manager_offline=False,
        ),
        sync_custom_nodes=lambda: None,
        start_backend=lambda: "fake_backend",
        initialize_cuda=lambda: {"cuda_available": False},
        capture_runtime_memory=capture,
    )
    trace = RuntimeTrace(process="remote")

    bootstrap.startup(snapshot=True, trace=trace)
    bootstrap.restore(trace=trace)

    assert [stage for stage, _ in calls] == [
        "after_custom_node_source_copy",
        "after_custom_node_registration",
        "after_runtime_backend_initialization",
        "after_bootstrap_startup_completion",
        "after_cuda_initialization",
        "after_bootstrap_restore_completion",
    ]
    assert calls[0][1]["custom_node_source_copy"] == "complete"
    assert calls[1][1]["custom_node_registration"] == "complete"
    assert calls[2][1]["runtime_backend_initialization"] == "complete"
    assert calls[3][1] == {
        "lifecycle": "startup",
        "snapshot": True,
        "boundary": "bootstrap_startup_complete",
    }
    assert calls[4][1]["cuda_initialization"] == "complete"
    assert calls[5][1]["bootstrap_restore"] == "complete"


def test_replacement_and_v2_bootstrap_construction_keep_memory_callback():
    entrypoint = modal_app.ModalRuntimeEntrypoint(
        config=BootstrapConfig(),
        executor=object(),
    )
    entrypoint._bootstrap_injected = False
    entrypoint._load_legacy_runtime = lambda: SimpleNamespace()
    entrypoint._legacy_module = SimpleNamespace()
    entrypoint._configure_runtime()
    assert entrypoint.bootstrap.capture_runtime_memory.__self__ is entrypoint

    v2_class = modal_app.ModalRuntimeEntrypointV2
    raw = getattr(v2_class.startup, "_get_raw_f", lambda: None)()
    assert raw is not None
    lazy_wrapper = next(
        cell.cell_contents
        for cell in (raw.__closure__ or ())
        if callable(cell.cell_contents)
        and "_v2_init_instance" in getattr(
            getattr(cell.cell_contents, "__code__", None), "co_freevars", ()
        )
    )
    lazy_init = lazy_wrapper.__closure__[
        lazy_wrapper.__code__.co_freevars.index("_v2_init_instance")
    ].cell_contents
    v2_entrypoint = object.__new__(v2_class)
    lazy_init(v2_entrypoint)
    assert v2_entrypoint.bootstrap.capture_runtime_memory.__self__ is v2_entrypoint


def test_decorated_v2_entrypoint_real_bootstrap_boundary_order(monkeypatch, tmp_path):
    """Exercise ``entrypoint.startup()`` through the decorated V2 boundary."""
    monkeypatch.setattr(modal_app, "_golden_serial_profile_active", lambda: True)
    monkeypatch.setattr(
        probe,
        "capture_runtime_memory",
        lambda stage, extra=None: {"stage": stage, "extra": dict(extra or {})},
    )
    monkeypatch.setattr(
        "comfymodal_runtime.runtime_bootstrap.ensure_models_symlink",
        lambda *_args: "unused",
    )
    monkeypatch.setattr(
        modal_app,
        "preimport_cachedit_family",
        lambda: {
            "ok": True,
            "versions": {},
            "paths": {},
            "cache_dit_info": {},
            "errors": [],
        },
    )
    quiescence_calls: list[dict] = []

    def fake_quiescence(**kwargs):
        quiescence_calls.append(dict(kwargs))
        return {"proven": True, "skipped": False}

    monkeypatch.setattr(
        "comfymodal_runtime.snapshot_capture_hygiene.prove_snapshot_quiescence",
        fake_quiescence,
    )
    monkeypatch.setattr(
        "comfymodal_runtime.snapshot_capture_hygiene.read_process_status_fields",
        lambda: {"rss_kb": 1},
    )

    content_proof_calls: list[dict] = []

    def fake_content_proof(**kwargs):
        content_proof_calls.append(dict(kwargs))
        return {
            "schema": "golden_snapshot_content_proof_v1",
            "passive": True,
            "surface_count": 1,
            "snapshot_size_bytes": kwargs["snapshot_size_bytes"],
            "snapshot_size_source": kwargs["snapshot_size_source"],
            "snapshot_size_is_serialized": kwargs["snapshot_size_is_serialized"],
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
        "comfymodal_runtime.golden_serial.golden_snapshot_content_proof",
        fake_content_proof,
    )

    class FakeModal:
        @staticmethod
        def enter(**_kwargs):
            return lambda function: function

        @staticmethod
        def exit(**_kwargs):
            return lambda function: function

        @staticmethod
        def method(**_kwargs):
            return lambda function: function

    monkeypatch.setattr(modal_app, "_modal", FakeModal)
    monkeypatch.setattr(
        modal_app.ModalRuntimeEntrypoint,
        "_configure_runtime",
        lambda self: None,
    )
    bootstrap_config = BootstrapConfig(
        comfyui_root=str(tmp_path / "comfy"),
        models_path=str(tmp_path / "models"),
        manager_offline=False,
    )

    def bootstrap_factory(_config=None, **kwargs):
        bootstrap = RuntimeBootstrap(
            bootstrap_config,
            sync_custom_nodes=lambda: calls.append(("registration_hook", {})),
            start_backend=lambda: "fake_backend",
            initialize_cuda=lambda: {"cuda_available": False},
            capture_runtime_memory=kwargs.get(
                "capture_runtime_memory", None,
            ),
        )
        return bootstrap

    monkeypatch.setattr(modal_app, "RuntimeBootstrap", bootstrap_factory)
    v2_class = modal_app._build_decorated_v2_class()
    entrypoint = v2_class()
    calls: list[tuple[str, dict]] = []
    result = entrypoint.startup()
    assert result["status"] == "ready"
    assert quiescence_calls == [{"passive": True}]
    assert len(content_proof_calls) == 1
    assert content_proof_calls[0]["snapshot_size_bytes"] == 1024
    assert content_proof_calls[0]["snapshot_size_is_serialized"] is False

    stages = [sample["stage"] for sample in entrypoint._golden_runtime_memory_samples]
    assert stages == [
        "startup_first_line",
        "after_custom_node_source_copy",
        "after_custom_node_registration",
        "after_runtime_backend_initialization",
        "after_bootstrap_startup_completion",
        "pre_capture_quiescence",
        "after_snapshot_content_proof",
        "before_snapshot_capture",
    ]
    assert calls == [("registration_hook", {})]
    assert stages.index("after_custom_node_registration") > stages.index(
        "after_custom_node_source_copy"
    )


def test_startup_restore_trace_merge_preserves_golden_memory_metadata():
    startup_sample = {"stage": "before_snapshot_capture"}
    restore_sample = {"stage": "after_bootstrap_restore_completion"}
    entrypoint = object.__new__(modal_app.ModalRuntimeEntrypoint)
    entrypoint._golden_runtime_memory_samples = [restore_sample]
    startup = RuntimeTrace(process="remote")
    startup.set_metadata(golden_runtime_memory_samples=[startup_sample])
    restore = RuntimeTrace(process="remote")
    restore.set_metadata(golden_runtime_memory_samples=[restore_sample])
    entrypoint._lifecycle_trace = startup

    entrypoint._remember_lifecycle_trace(restore)
    merged = merge_runtime_traces(entrypoint._lifecycle_trace, restore)
    merged.set_metadata(
        golden_runtime_memory_samples=entrypoint._golden_runtime_memory_metadata(
            entrypoint._lifecycle_trace, restore,
        )
    )

    assert merged.to_dict()["metadata"]["golden_runtime_memory_samples"] == [
        startup_sample,
        restore_sample,
    ]


def test_mixed_status_rssfile_and_partial_smaps_keep_smaps_source(monkeypatch):
    def fake_proc(name: str):
        if name == "smaps_rollup":
            return "Rss: 100 kB\nPss: 60 kB\nAnonymous: 10 kB\n"
        if name == "status":
            return "RssFile: 90 kB\n"
        return None

    monkeypatch.setattr(probe, "_proc_self_file", fake_proc)
    monkeypatch.setattr(probe, "_proc_self_file_bounded", lambda *_args: (FAKE_SMAPS, True))
    monkeypatch.setattr(probe, "_read_text", lambda *_args, **_kwargs: None)

    result = probe.probe_process_memory(include_smaps=True, max_smaps_bytes=4096)

    # A partial bounded smaps read cannot supersede the complete status:RssFile
    # fallback.  The smaps subdocument still records its own partial sample.
    assert result["file_backed_resident_bytes"] == 90 * 1024
    assert result["rss_file_bytes"] == 90 * 1024
    assert result["file_backed_resident_status"] == "status_rssfile"
    assert result["smaps"]["file_backed_resident_status"] == "partial"


def test_unreadable_smaps_keeps_status_rssfile_and_marks_smaps_fields_unavailable(monkeypatch):
    def fake_proc(name: str):
        if name == "status":
            return "RssFile: 90 kB\n"
        return None

    def unreadable(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(probe, "_proc_self_file", fake_proc)
    monkeypatch.setattr(probe, "_proc_self_file_bounded", unreadable)
    monkeypatch.setattr(probe, "_read_text", lambda *_args, **_kwargs: None)

    result = probe.probe_process_memory(include_smaps=True)

    assert result["file_backed_resident_bytes"] == 90 * 1024
    assert result["file_backed_resident_status"] == "status_rssfile"
    for key in (
        "native_library_resident_status",
        "cuda_runtime_host_mapped_status",
        "custom_node_resident_status",
        "thread_stack_resident_status",
    ):
        assert result[key] == "unavailable"
    assert result["smaps"]["native_library_resident_status"] == "unavailable"


def test_partial_smaps_preserves_approximate_file_backed_fallback(monkeypatch):
    def fake_proc(name: str):
        if name == "smaps_rollup":
            return "Rss: 100 kB\nPss: 60 kB\nAnonymous: 10 kB\n"
        return None

    monkeypatch.setattr(probe, "_proc_self_file", fake_proc)
    monkeypatch.setattr(
        probe, "_proc_self_file_bounded", lambda *_args: (FAKE_SMAPS, True)
    )
    monkeypatch.setattr(probe, "_read_text", lambda *_args, **_kwargs: None)

    result = probe.probe_process_memory(include_smaps=True, max_smaps_bytes=4096)

    assert result["rss_file_mib"] == 0.09
    assert result["file_backed_resident_bytes"] == int(0.09 * 1024 * 1024)
    assert result["file_backed_resident_status"] == "approximate_rss_minus_anonymous"
    assert result["field_sources"]["file_backed_resident_bytes"] == (
        "approximate_rss_minus_anonymous"
    )
    assert result["smaps"]["file_backed_resident_status"] == "partial"


def test_runtime_probe_exception_returns_uniform_json_safe_schema(monkeypatch):
    def fail_probe(**_kwargs):
        raise RuntimeError("forced probe failure")

    monkeypatch.setattr(probe, "probe_process_memory", fail_probe)
    result = probe.capture_runtime_memory("forced_failure", extra={"object": object()})

    json.dumps(result)
    assert result["status"] == "measurement_error"
    assert result["error"].startswith("RuntimeError: forced probe failure")
    for key in (
        "process", "python_heap", "allocator", "resource", "cuda",
        "threads", "modules", "serialized_snapshot_size_bytes",
        "serialized_snapshot_size_status",
    ):
        assert key in result
    assert result["process"]["status"] == "error"


def test_runtime_memory_statuses_share_one_schema_including_forced_exception(monkeypatch):
    def captured_probe(**_kwargs):
        return {"rss_bytes": 123, "pss_bytes": 100, "swap_bytes": 7,
                "rss_source": "test_source", "pss_source": "test_source",
                "swap_source": "test_source",
                "smaps": {"available": True}}

    def partial_probe(**_kwargs):
        return {"status": "partial", "rss_bytes": 123,
                "smaps": {"available": True, "partial": True,
                           "status": "partial"}}

    monkeypatch.setattr(probe, "probe_process_memory", captured_probe)
    captured = probe.capture_runtime_memory("captured")
    monkeypatch.setattr(probe, "probe_process_memory", partial_probe)
    partial = probe.capture_runtime_memory("partial")

    def forced_failure(**_kwargs):
        raise RuntimeError("forced capture exception")

    monkeypatch.setattr(probe, "probe_process_memory", forced_failure)
    error = probe.capture_runtime_memory("error")

    assert {captured["status"], partial["status"], error["status"]} == {
        "captured", "partial", "measurement_error",
    }
    assert captured["process"]["rss_bytes"] == 123
    assert captured["process"]["rss_source"] == "test_source"
    assert captured["process"]["swap_bytes"] == 7
    assert partial["process"]["status"] == "partial"
    assert error["error"].startswith("RuntimeError: forced capture exception")
    assert set(captured) == set(partial) == set(error)
    assert set(captured["process"]) == set(partial["process"]) == set(error["process"])
    for result in (captured, partial, error):
        json.dumps(result)


def test_lifecycle_trace_metadata_survives_startup_restore_request_merge():
    entrypoint = object.__new__(modal_app.ModalRuntimeEntrypoint)
    entrypoint._golden_runtime_memory_samples = []
    startup = RuntimeTrace(process="remote", trace_id="startup-trace")
    startup.set_metadata(
        trace_id="startup-trace", restored_instance_id="startup-instance",
        restore_session_id="startup-restore", cpu=2, resource_volume="startup",
        golden_runtime_memory_samples=[{"stage": "startup"}],
    )
    restore = RuntimeTrace(process="remote", trace_id="restore-trace")
    restore.set_metadata(
        trace_id="restore-trace", restored_instance_id="restored-instance",
        restore_session_id="restore-session", cpu=8, resource_volume="restore",
        cuda_type="test-gpu", golden_runtime_memory_samples=[{"stage": "restore"}],
    )
    request = RuntimeTrace(process="remote", request_id="request")
    request.set_metadata(
        trace_id="request-trace", restored_instance_id="request-instance",
        cpu=1, resource_volume="request", golden_runtime_memory_samples=[{"stage": "request"}],
    )

    entrypoint._lifecycle_trace = None
    entrypoint._remember_lifecycle_trace(startup)
    entrypoint._remember_lifecycle_trace(restore)
    merged = merge_runtime_traces(entrypoint._lifecycle_trace, request)
    entrypoint._merge_final_trace_metadata(merged, request.to_dict())
    metadata = merged.to_dict()["metadata"]

    assert metadata["restore_session_id"] == "restore-session"
    assert metadata["restored_instance_id"] == "restored-instance"
    assert metadata["trace_id"] == "restore-trace"
    assert metadata["cpu"] == 8
    assert metadata["resource_volume"] == "restore"
    assert [item["stage"] for item in metadata["golden_runtime_memory_samples"]] == [
        "startup", "restore", "request"
    ]
    assert metadata["golden_runtime_memory_samples"] is not startup.to_dict()["metadata"][
        "golden_runtime_memory_samples"
    ]


def test_modal_runtime_memory_helper_persists_trace_timing_and_resets(monkeypatch):
    samples: list[dict] = []

    monkeypatch.setattr(modal_app, "_golden_serial_profile_active", lambda: True)
    monkeypatch.setattr(
        probe,
        "capture_runtime_memory",
        lambda stage, extra=None: {"stage": stage, "extra": dict(extra or {})},
    )
    entrypoint = object.__new__(modal_app.ModalRuntimeEntrypoint)
    entrypoint._golden_runtime_memory_samples = samples
    entrypoint._restore_timing = {}
    trace = RuntimeTrace(process="remote")

    entrypoint._capture_golden_runtime_memory(
        "restore_first_line",
        trace=trace,
        metadata={"boundary": "first_python_line"},
    )
    assert [item["stage"] for item in entrypoint._golden_runtime_memory_samples] == [
        "restore_first_line"
    ]
    assert entrypoint._restore_timing["golden_runtime_memory_samples"] == entrypoint._golden_runtime_memory_samples
    assert trace.to_dict()["metadata"]["golden_runtime_memory_samples"] == entrypoint._golden_runtime_memory_samples
    assert trace.to_dict()["events"][-1]["name"] == "golden_runtime_memory_sample"

    # A new restore cycle owns a new list; no prior sample may be reused.
    entrypoint._golden_runtime_memory_samples = []
    entrypoint._restore_timing = {}
    entrypoint._capture_golden_runtime_memory("after_cuda_initialization", trace=trace)
    assert [item["stage"] for item in entrypoint._golden_runtime_memory_samples] == [
        "after_cuda_initialization"
    ]
