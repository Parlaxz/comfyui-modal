from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import studio_golden_run
from studio_golden_run import GoldenRunError, GoldenStageEventStore, browser_override_error
from tools.v2_control import profile_catalog


pytestmark = pytest.mark.fast_unit


def test_modal_snapshot_lifecycle_uses_startup_boundaries_not_teardown():
    phase = studio_golden_run._modal_lifecycle_phase
    assert phase("[v2.startup_stage] stage=snapshot_startup_callback event=return status=ready") == "snapshot_capturing"
    assert phase("Snapshot created. Restoring Function from memory snapshot.") == "restoring"
    assert phase("", "TASK_STATE_QUEUED") == "scheduling"
    assert phase("[v2.golden.progress] stage=golden_teardown") is None


def test_studio_span_log_bridge_filters_foreign_requests_and_malformed_lines():
    text = '\n'.join([
        '[v2.studio_span] {"type":"gantt_span","request_id":"ours","span_id":"clip","phase":"started"}',
        '[v2.studio_span] {"type":"gantt_span","request_id":"other","phase":"started"}',
        '[v2.studio_span] broken json',
    ])
    events = studio_golden_run._studio_span_events(text, "ours")
    assert [event["span_id"] for event in events] == ["clip"]


@pytest.mark.asyncio
async def test_modal_lifecycle_ignores_old_logs_and_reports_ambiguous_tasks(monkeypatch):
    from modal.client import _Client
    from modal.cli import app as modal_app_cli

    store = GoldenStageEventStore()
    store.start("lifecycle-test")
    async def batches(query):
        assert query.function_id == "fu-test"
        for task, stamp in [("ta-old", 9), ("ta-one", 11), ("ta-two", 12)]:
            yield SimpleNamespace(
                entry_id=str(stamp), app_done=False, task_id=task,
                items=[SimpleNamespace(timestamp=stamp, task_state=0,
                    data="[v2.lifecycle] method=startup snap=True status=ready")],
            )
        yield SimpleNamespace(entry_id="done", app_done=True, items=[])
    client = SimpleNamespace(stub=SimpleNamespace(AppGetLogs=SimpleNamespace(unary_stream=batches)))
    async def credentials(*args):
        return client
    async def resolve(*args):
        return "ap-test", "", None
    async def hydrate():
        pass
    monkeypatch.setattr(_Client, "from_credentials", credentials)
    monkeypatch.setattr(modal_app_cli, "resolve_app_identifier", resolve)
    method = SimpleNamespace(object_id="fu-test", hydrate=SimpleNamespace(aio=hydrate))
    await studio_golden_run._observe_modal_lifecycle(
        SimpleNamespace(target={"app": "test-app"}),
        {"token_id": "test", "token_secret": "test"}, method,
        "lifecycle-test", store, 10,
    )
    events = store.read("lifecycle-test")["events"]
    assert [(event["phase"], event["task_id"]) for event in events] == [
        ("snapshot_capturing", "ta-one"), ("lifecycle_unknown", "ta-two"),
    ]


def test_stage_store_cursor_is_idempotent_and_bounded() -> None:
    store = GoldenStageEventStore(max_events=2, max_runs=1, ttl_seconds=60)
    store.start("studio-1")
    store.append("studio-1", {"type": "stage", "sequence": 4})
    store.append("studio-1", {"type": "stage", "sequence": 5})
    with pytest.raises(GoldenRunError):
        store.start("studio-2")
    store.append("studio-1", {"type": "result", "sequence": 6})

    first = store.read("studio-1", 0)
    again = store.read("studio-1", 0)
    assert [event["cursor"] for event in first["events"]] == [2, 3]
    assert [event["sequence"] for event in first["events"]] == [5, 6]
    assert first == again
    assert first["terminal"] is True


def test_browser_target_and_flag_overrides_are_rejected() -> None:
    assert browser_override_error({"controls": {"gpu": "not-a-target"}}) is None
    message = browser_override_error({
        "gpu": "A100",
        "modal_options": {"method": "run_plan_stream"},
    })
    assert message is not None
    assert "gpu" in message
    assert "modal_options.method" in message


def test_catalog_projects_golden_profiles_and_skips_unreadable(tmp_path, monkeypatch) -> None:
    profiles_dir = tmp_path / "config" / "v2" / "profiles"
    profiles_dir.mkdir(parents=True)
    registry = tmp_path / "config" / "v2" / "flag_registry.toml"
    registry.write_text(
        (Path(__file__).parents[1] / "config" / "v2" / "flag_registry.toml").read_text(),
        encoding="utf-8",
    )
    (profiles_dir / "golden.toml").write_text(
        """schema_version = 1
name = "golden"
owner = "test"
[target]
app = "test-golden"
class = "ModalRuntimeEntrypointV2"
method = "run_golden_parallel_stream"
[resources]
gpu = "H100"
cpu = 12
memory_mb = 24576
""",
        encoding="utf-8",
    )
    (profiles_dir / "broken.toml").write_text("not = [valid", encoding="utf-8")

    projected = profile_catalog.catalog_golden_profiles(tmp_path)
    assert [item.name for item in projected] == ["golden"]
    assert projected[0].to_dict() == {
        "name": "golden",
        "owner": "test",
        "target": {
            "app": "test-golden",
            "class": "ModalRuntimeEntrypointV2",
            "method": "run_golden_parallel_stream",
        },
        "resources": {
            "gpu": "H100",
            "gpu_alt": "",
            "gpu_fallbacks": [],
            "cpu": 12,
            "memory_mb": 24576,
        },
        "gpu_order_a": ["h100"],
        "gpu_order_b": [],
        "region": "",
        "deployed": False,
    }


def test_catalog_cache_tracks_modal_destination_changes(tmp_path, monkeypatch) -> None:
    profiles_dir = tmp_path / "config" / "v2" / "profiles"
    profiles_dir.mkdir(parents=True)
    config_dir = tmp_path / "config" / "v2"
    registry = config_dir / "flag_registry.toml"
    registry.write_text(
        (Path(__file__).parents[1] / "config" / "v2" / "flag_registry.toml").read_text(),
        encoding="utf-8",
    )
    (profiles_dir / "golden.toml").write_text(
        """schema_version = 1
name = "golden"
owner = "test"
[target]
app = "test-golden"
class = "ModalRuntimeEntrypointV2"
method = "run_golden_parallel_stream"
[resources]
gpu = "H100"
cpu = 12
memory_mb = 24576
""",
        encoding="utf-8",
    )
    target = config_dir / "modal_target.toml"
    target.write_text(
        '[modal]\nworkspace_id = "legacy"\nworkspace_label = "Legacy"\nenvironment = "(default)"\n',
        encoding="utf-8",
    )
    profile_catalog.invalidate_catalog_cache()
    first_signature = profile_catalog._catalog_signature(tmp_path)
    target.write_text(
        '[modal]\nworkspace_id = "testing"\nworkspace_label = "Testing"\nenvironment = "(default)"\n',
        encoding="utf-8",
    )
    second_signature = profile_catalog._catalog_signature(tmp_path)
    assert first_signature != second_signature


def test_unknown_method_fails_closed(tmp_path) -> None:
    profiles_dir = tmp_path / "config" / "v2" / "profiles"
    profiles_dir.mkdir(parents=True)
    (tmp_path / "config" / "v2" / "flag_registry.toml").parent.mkdir(exist_ok=True)
    (tmp_path / "config" / "v2" / "flag_registry.toml").write_text(
        (Path(__file__).parents[1] / "config" / "v2" / "flag_registry.toml").read_text(),
        encoding="utf-8",
    )
    (profiles_dir / "unknown.toml").write_text(
        """schema_version = 1
name = "unknown"
[target]
app = "x"
class = "ModalRuntimeEntrypointV2"
method = "run_plan_stream"
""",
        encoding="utf-8",
    )
    with pytest.raises(profile_catalog.GoldenProfileError, match="unsupported target method"):
        profile_catalog.resolve_golden_profile("unknown", tmp_path)


def test_receipt_resource_mismatch_refuses_profile(monkeypatch) -> None:
    receipt = SimpleNamespace(
        profile="golden_p1_parallel_c0_p8_h100",
        target={
            "app": "batch-c0-p8-h100",
            "class": "ModalRuntimeEntrypointV2",
            "method": "run_golden_parallel_stream",
        },
        effective_config={
            "resources": {"gpu": "H100", "cpu": 99, "memory_mb": 24576},
        },
        deployment_identity={},
        profile_config_fingerprint="ignored-after-resource-mismatch",
    )
    monkeypatch.setattr(
        profile_catalog,
        "latest_deployment_receipt",
        lambda *args, **kwargs: (Path("receipt.json"), receipt),
    )
    with pytest.raises(profile_catalog.GoldenProfileError, match="no matching deployment receipt"):
        profile_catalog.resolve_golden_profile("golden_p1_parallel_c0_p8_h100")


@pytest.mark.asyncio
async def test_selected_workflow_controls_reach_configured_golden_method(monkeypatch, tmp_path) -> None:
    target = {
        "app": "configured-app",
        "class": "ModalRuntimeEntrypointV2",
        "method": "run_golden_parallel_stream",
    }
    profile = profile_catalog.GoldenProfile(
        name="golden-test",
        owner="test",
        target=target,
        resources={"gpu": "H100", "cpu": 12, "memory_mb": 24576},
        config=SimpleNamespace(),  # type: ignore[arg-type]
        receipt=SimpleNamespace(deploy_fingerprint="deploy-test"),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(studio_golden_run, "resolve_golden_profile", lambda name: profile)

    captured: dict = {}

    class RemoteGenerator:
        def aio(self, payload, **kwargs):
            captured["payload"] = payload
            captured["kwargs"] = kwargs

            async def events():
                yield {"type": "stage", "sequence": 8, "name": "decode"}
                yield {"type": "result", "sequence": 9, "data": {"image": "ok"}}

            return events()

    handle = SimpleNamespace(
        run_golden_studio_stream=SimpleNamespace(remote_gen=RemoteGenerator()),
        run_plan_stream=SimpleNamespace(remote_gen=RemoteGenerator()),
    )
    bundle = {
        "status": "ok",
        "workflow": {"workflow_id": "wf"},
        "version": {"workflow_version_id": "wv"},
        "preset": {"preset_id": "preset", "values": {"strength": 1}},
        "defaults": {"strength": 1},
        "control_schema": {
            "strength": {"node_id": "1", "input_name": "strength", "type": "number"},
        },
        "mapping": {"output_node_id": "2"},
        "executable_prompt": {
            "1": {"class_type": "TestNode", "inputs": {"strength": 1}},
            "2": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": "krea2\\krea2_turbo_fp8_scaled.safetensors"},
            },
        },
    }
    import studio_workflow_run
    def fake_build_plan(bundle_arg, values, *args, **kwargs):
        workflow = copy.deepcopy(bundle_arg["executable_prompt"])
        workflow["1"]["inputs"]["strength"] = values["strength"]
        workflow["2"]["inputs"]["unet_name"] = "krea2_turbo_fp8_scaled.safetensors"
        return (
            SimpleNamespace(
                to_dict=lambda: {
                    "workflow": workflow,
                    "output_node_ids": ["2"],
                }
            ),
            None,
        )

    monkeypatch.setattr(studio_workflow_run, "build_workflow_execution_plan", fake_build_plan)
    monkeypatch.setattr(
        studio_workflow_run,
        "resolve_workflow_run_bundle",
        lambda *args, **kwargs: bundle,
    )

    store = GoldenStageEventStore(max_events=8, max_runs=2, ttl_seconds=60)
    result = await studio_golden_run.run_golden_workflow(
        workflow_id="wf",
        version_id="wv",
        preset_id="preset",
        controls={"strength": 7},
        request_id="studio-test",
        node_dir=tmp_path,
        profile_name="golden-test",
        event_store=store,
        handle_factory=lambda *_args: handle,
    )
    assert result["status"] == "ok"
    assert captured["payload"]["workflow"]["1"]["inputs"]["strength"] == 7
    assert captured["payload"]["workflow"]["2"]["inputs"]["unet_name"] == "krea2_turbo_fp8_scaled.safetensors"
    assert captured["kwargs"]["request_id"] == "studio-test"
    assert store.read("studio-test")["terminal"] is True


def test_materialize_image_uses_date_names(monkeypatch, tmp_path) -> None:
    import base64
    import re
    from datetime import datetime

    import local_artifacts

    monkeypatch.setattr(
        local_artifacts, "get_studio_outputs_dir", lambda: tmp_path / "outputs"
    )
    raw = b"fakepng-bytes"
    result = {
        "images": [{
            "asset_id": "815df67881e0b8cd",
            "byte_count": len(raw),
            "data": base64.b64encode(raw).decode("ascii"),
        }],
    }
    materialized = studio_golden_run._materialize_image(
        result, "de521c37-fae8-4f97-8ceb-4ed539187d20"
    )
    names = materialized["output_paths"]
    assert len(names) == 1
    assert re.fullmatch(r"golden_\d{4}-\d{2}-\d{2}_\d{6}(_\d+)?.png", names[0]), names[0]
    assert len(names[0]) <= 32, names[0]
    assert (tmp_path / "outputs" / names[0]).read_bytes() == raw
    assert "data" not in materialized["images"][0]


def test_materialized_names_disambiguate_same_second_collisions(tmp_path) -> None:
    from datetime import datetime

    out_dir = tmp_path / "outputs"
    out_dir.mkdir()
    now = datetime(2026, 10, 12, 15, 30, 22)
    first = studio_golden_run._materialized_image_name(out_dir, now=now)
    assert first == "golden_2026-10-12_153022.png"
    (out_dir / first).write_bytes(b"x")
    second = studio_golden_run._materialized_image_name(out_dir, now=now)
    assert second == "golden_2026-10-12_153022_1.png"


def test_sniff_image_extension_reads_magic_bytes() -> None:
    sniff = studio_golden_run._sniff_image_extension
    assert sniff(bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 8) == "png"
    assert sniff(b"RIFF\x00\x00\x00\x00WEBP") == "webp"
    assert sniff(b"\xff\xd8\xff\xe0" + b"\x00" * 8) == "jpg"
    assert sniff(b"GIF89a" + b"\x00" * 8) == "gif"
    assert sniff(b"BM" + b"\x00" * 10) == "bmp"
    assert sniff(b"not-an-image-at-all!") is None
    assert sniff(b"short") is None
    assert sniff(None) is None


def test_materialize_image_names_by_actual_bytes(monkeypatch, tmp_path) -> None:
    import base64
    import io
    import re

    from PIL import Image

    import local_artifacts

    monkeypatch.setattr(
        local_artifacts, "get_studio_outputs_dir", lambda: tmp_path / "outputs"
    )
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, format="WEBP")
    raw = buffer.getvalue()
    result = {
        "images": [{
            "asset_id": "815df67881e0b8cd",
            "byte_count": len(raw),
            "data": base64.b64encode(raw).decode("ascii"),
        }],
    }
    materialized = studio_golden_run._materialize_image(
        result, "de521c37-fae8-4f97-8ceb-4ed539187d20"
    )
    names = materialized["output_paths"]
    assert len(names) == 1
    # WebP bytes must never land in a .png name (previously hardcoded).
    assert re.fullmatch(r"golden_\d{4}-\d{2}-\d{2}_\d{6}(_\d+)?.webp", names[0]), names[0]
    assert (tmp_path / "outputs" / names[0]).read_bytes() == raw


def test_golden_history_meta_records_actual_executor_method() -> None:
    profile = profile_catalog.GoldenProfile(
        name="golden-test",
        owner="test",
        target={
            "app": "configured-app",
            "class": "ModalRuntimeEntrypointV2",
            "method": "run_golden_parallel_stream",
        },
        resources={"gpu": "H100", "cpu": 12, "memory_mb": 24576},
        config=SimpleNamespace(),  # type: ignore[arg-type]
        receipt=SimpleNamespace(deploy_fingerprint="deploy-test"),  # type: ignore[arg-type]
    )
    generic = studio_golden_run._golden_history_meta(
        "r1", profile, {}, method="run_plan_stream"
    )
    assert generic["golden_method"] == "run_plan_stream"
    assert generic["golden_executor"] == "generic"
    canonical = studio_golden_run._golden_history_meta("r2", profile, {})
    assert canonical["golden_method"] == "run_golden_parallel_stream"
    assert canonical["golden_executor"] == "canonical"


@pytest.mark.asyncio
async def test_materialization_failure_fails_run_truthfully(monkeypatch, tmp_path) -> None:
    target = {
        "app": "configured-app",
        "class": "ModalRuntimeEntrypointV2",
        "method": "run_golden_parallel_stream",
    }
    profile = profile_catalog.GoldenProfile(
        name="golden-test",
        owner="test",
        target=target,
        resources={"gpu": "H100", "cpu": 12, "memory_mb": 24576},
        config=SimpleNamespace(),  # type: ignore[arg-type]
        receipt=SimpleNamespace(deploy_fingerprint="deploy-test"),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(studio_golden_run, "resolve_golden_profile", lambda name: profile)

    class RemoteGenerator:
        def aio(self, payload, **kwargs):
            async def events():
                yield {"type": "result", "sequence": 9, "data": {"image": "ok"}}

            return events()

    handle = SimpleNamespace(
        run_golden_studio_stream=SimpleNamespace(remote_gen=RemoteGenerator()),
        run_plan_stream=SimpleNamespace(remote_gen=RemoteGenerator()),
    )
    bundle = {
        "status": "ok",
        "workflow": {"workflow_id": "wf"},
        "version": {"workflow_version_id": "wv"},
        "preset": {"preset_id": "preset", "values": {}},
        "defaults": {},
        "control_schema": {},
        "mapping": {"output_node_id": "2"},
        "executable_prompt": {
            "2": {"class_type": "UNETLoader", "inputs": {}},
        },
    }
    import studio_workflow_run
    monkeypatch.setattr(
        studio_workflow_run,
        "resolve_workflow_run_bundle",
        lambda *args, **kwargs: bundle,
    )

    def fake_build_plan(bundle_arg, values, *args, **kwargs):
        return (
            SimpleNamespace(
                to_dict=lambda: {"workflow": {}, "output_node_ids": ["2"]}
            ),
            None,
        )

    monkeypatch.setattr(
        studio_workflow_run, "build_workflow_execution_plan", fake_build_plan
    )
    monkeypatch.setattr(
        studio_golden_run,
        "_materialize_image",
        lambda data, request_id: {"output_materialization_error": "boom"},
    )
    import experiment_service

    calls: dict = {}

    class FakeHistory:
        def record_run(self, **kwargs):
            calls["meta"] = kwargs.get("meta")
            return {"run_id": "run-1", "history_generation_id": "gen-1"}

        def update_run(self, run_id, **kwargs):
            calls["update"] = (run_id, kwargs)

    class FakeRegistry:
        def history(self):
            return FakeHistory()

    monkeypatch.setattr(experiment_service, "REGISTRY", FakeRegistry())

    store = GoldenStageEventStore(max_events=8, max_runs=2, ttl_seconds=60)
    result = await studio_golden_run.run_golden_workflow(
        workflow_id="wf",
        version_id="wv",
        preset_id="preset",
        controls={},
        request_id="studio-test",
        node_dir=tmp_path,
        profile_name="golden-test",
        event_store=store,
        handle_factory=lambda *_args: handle,
    )
    assert result["status"] == "error"
    assert "boom" in result["message"]
    assert calls["meta"]["golden_method"] == "run_plan_stream"
    assert calls["meta"]["golden_executor"] == "generic"
    assert calls["update"][1]["status"] == "failed"


@pytest.mark.asyncio
async def test_golden_fast_path_repairs_empty_dropdown_link(monkeypatch, tmp_path) -> None:
    """The canonical fast path submits apply() output directly, so it must run
    the empty-dropdown repair itself — otherwise "" reaches
    ImageScaleToTotalPixels.megapixels and crashes remote execution AFTER
    model loading (TypeError: str / int, live 2026-10-11)."""
    target = {
        "app": "configured-app",
        "class": "ModalRuntimeEntrypointV2",
        "method": "run_golden_serial_stream",
    }
    profile = profile_catalog.GoldenProfile(
        name="golden-test",
        owner="test",
        target=target,
        resources={"gpu": "H100", "cpu": 12, "memory_mb": 24576},
        config=SimpleNamespace(),  # type: ignore[arg-type]
        receipt=SimpleNamespace(deploy_fingerprint="deploy-test"),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(studio_golden_run, "resolve_golden_profile", lambda name: profile)
    monkeypatch.setattr(studio_golden_run, "_canonical_golden_fast_path", lambda wf: True)

    captured: dict = {}

    class RemoteGenerator:
        def aio(self, payload, **kwargs):
            captured["payload"] = payload
            captured["kwargs"] = kwargs

            async def events():
                yield {"type": "result", "sequence": 9, "data": {"image": "ok"}}

            return events()

    handle = SimpleNamespace(
        run_golden_studio_stream=SimpleNamespace(remote_gen=RemoteGenerator()),
    )
    bundle = {
        "status": "ok",
        "workflow": {"workflow_id": "wf"},
        "version": {"workflow_version_id": "wv"},
        "preset": {"preset_id": "preset", "values": {}},
        "defaults": {},
        "control_schema": {},
        "mapping": {"output_node_id": "15"},
        "executable_prompt": {
            "6": {"class_type": "PixaromaDropdown", "inputs": {"DropdownState": "{}"}},
            "15": {
                "class_type": "ImageScaleToTotalPixels",
                "inputs": {"image": ["1", 0], "megapixels": ["6", 0]},
            },
        },
    }
    import studio_workflow_run
    monkeypatch.setattr(
        studio_workflow_run,
        "resolve_workflow_run_bundle",
        lambda *args, **kwargs: bundle,
    )

    store = GoldenStageEventStore(max_events=8, max_runs=2, ttl_seconds=60)
    result = await studio_golden_run.run_golden_workflow(
        workflow_id="wf",
        version_id="wv",
        preset_id="preset",
        controls={},
        request_id="studio-dropdown",
        node_dir=tmp_path,
        profile_name="golden-test",
        event_store=store,
        handle_factory=lambda *_args: handle,
    )
    assert result["status"] == "ok"
    prompt = captured["payload"]["prompt"]
    assert prompt["6"]["inputs"]["DropdownState"] == '{"type": "float", "value": 1.0}'
    assert captured["payload"]["extra_data"]["repaired_empty_dropdowns"] != []


@pytest.mark.asyncio
async def test_generic_run_marks_cursor_and_hides_plan_received(monkeypatch, tmp_path) -> None:
    """A non-canonical workflow takes the generic executor, which streams no
    Golden stages. The cursor must carry the generic_execution marker (so the
    UI can name the executor) and must NOT carry the generic executor's own
    plan_received status (which would refreeze the UI on "Starting up")."""
    target = {
        "app": "configured-app",
        "class": "ModalRuntimeEntrypointV2",
        "method": "run_golden_parallel_stream",
    }
    profile = profile_catalog.GoldenProfile(
        name="golden-test",
        owner="test",
        target=target,
        resources={"gpu": "H100", "cpu": 12, "memory_mb": 24576},
        config=SimpleNamespace(),  # type: ignore[arg-type]
        receipt=SimpleNamespace(deploy_fingerprint="deploy-test"),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(studio_golden_run, "resolve_golden_profile", lambda name: profile)

    class RemoteGenerator:
        def aio(self, payload, **kwargs):
            async def events():
                yield {"type": "status", "phase": "plan_received", "request_id": "studio-generic"}
                yield {"type": "result", "sequence": 9, "data": {"image": "ok"}}

            return events()

    handle = SimpleNamespace(
        run_golden_studio_stream=SimpleNamespace(remote_gen=RemoteGenerator()),
        run_plan_stream=SimpleNamespace(remote_gen=RemoteGenerator()),
    )
    bundle = {
        "status": "ok",
        "workflow": {"workflow_id": "wf"},
        "version": {"workflow_version_id": "wv"},
        "preset": {"preset_id": "preset", "values": {}},
        "defaults": {},
        "control_schema": {},
        "mapping": {"output_node_id": "1"},
        "executable_prompt": {
            "1": {"class_type": "TestNode", "inputs": {}},
        },
    }
    import studio_workflow_run
    monkeypatch.setattr(
        studio_workflow_run,
        "resolve_workflow_run_bundle",
        lambda *args, **kwargs: bundle,
    )

    def fake_build_plan(bundle_arg, values, *args, **kwargs):
        return (
            SimpleNamespace(
                to_dict=lambda: {
                    "workflow": bundle_arg["executable_prompt"],
                    "output_node_ids": ["1"],
                }
            ),
            None,
        )

    monkeypatch.setattr(studio_workflow_run, "build_workflow_execution_plan", fake_build_plan)

    store = GoldenStageEventStore(max_events=16, max_runs=2, ttl_seconds=60)
    result = await studio_golden_run.run_golden_workflow(
        workflow_id="wf",
        version_id="wv",
        preset_id="preset",
        controls={},
        request_id="studio-generic",
        node_dir=tmp_path,
        profile_name="golden-test",
        event_store=store,
        handle_factory=lambda *_args: handle,
    )
    assert result["status"] == "ok"
    page = store.read("studio-generic", 0)
    phases = [
        (event.get("type"), event.get("phase"))
        for event in page["events"]
    ]
    assert ("status", "generic_execution") in phases
    assert not any(
        phase == "plan_received" for _type, phase in phases
    ), "generic plan_received must not reach the polled cursor"
    assert page["terminal"] is True


# ── Phase 8 Lane B: reference-image execution (Golden lane) ──────────────
#
# Fast unit tests only: temp-dir domain service, fake input files, fake
# Modal handles, real shared prep/mutation from studio_workflow_run (one
# implementation for both lanes). The canonical fast-path classifier is
# monkeypatched (it would otherwise import the heavy golden runtime); no
# Torch/Modal/heavy lifecycle.


def _g_ref_defs(class_type: str):
    if class_type == "RefConditioner":
        return (
            {
                "clip": ("CLIP",),
                "text": ("STRING", {"multiline": True}),
                "image_1": ("IMAGE",),
                "image_2": ("IMAGE",),
            },
            {},
        )
    if class_type == "LoadImage":
        return ({"image": ("STRING",)}, {})
    if class_type == "CLIPLoader":
        return ({"clip_name": ("STRING",)}, {})
    if class_type == "CLIPTextEncode":
        return ({"text": ("STRING", {"multiline": True}), "clip": ("CLIP",)}, {})
    return ({}, {})


def _g_m1_prompt() -> dict:
    return {
        "1": {"class_type": "CLIPLoader", "inputs": {"clip_name": "c.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "cat", "clip": ["1", 0]}},
        "3": {"class_type": "RefConditioner", "inputs": {
            "clip": ["1", 0], "text": "cat",
            "image_1": ["7", 0], "image_2": ["8", 0]}},
        "7": {"class_type": "LoadImage", "inputs": {"image": "base.png"}},
        "8": {"class_type": "LoadImage", "inputs": {"image": "other.png"}},
        "9": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "m.safetensors"}},
        "4": {"class_type": "KSampler", "inputs": {
            "model": ["9", 0], "seed": 1, "steps": 5, "cfg": 7.0,
            "sampler_name": "euler", "scheduler": "normal",
            "positive": ["3", 0], "negative": ["2", 0],
            "latent_image": ["5", 0], "denoise": 1.0}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 64, "height": 64, "batch_size": 1}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["4", 0]}},
    }


def _g_entry(role, node_id, input_name, control_kind="string"):
    return {
        "semantic_role": role, "node_id": node_id, "input_name": input_name,
        "kind": "node_input", "control_kind": control_kind, "required": False,
    }


def _g_m1_bindings():
    return {
        "candidate_id": "conditioning_slots:3",
        "slots": [
            {"node_id": "3", "socket": "image_1", "order": 0, "kind": "reference"},
            {"node_id": "3", "socket": "image_2", "order": 1, "kind": "reference"},
        ],
    }


def _g_setup_service(root):
    from studio_domain import WorkflowDomainService

    svc = WorkflowDomainService(str(root))
    svc._node_def_provider = _g_ref_defs
    (root / "input").mkdir(parents=True, exist_ok=True)
    for name in ("ref_a.png", "ref_b.png", "base.png", "other.png"):
        (root / "input" / name).write_bytes(b"fake-" + name.encode())
    wf = svc.create_workflow("golden refs")
    version = svc.create_version_from_capture(
        wf["workflow_id"],
        {"graph_json": {"id": "g", "nodes": []},
         "api_prompt_json": {"workflow": {}, "output": _g_m1_prompt()}},
    )
    svc.set_mapping(
        version["workflow_version_id"],
        entries={
            "positive_prompt": _g_entry("positive_prompt", "2", "text"),
            "seed": _g_entry("seed", "4", "seed", "integer"),
            "steps": _g_entry("steps", "4", "steps", "integer"),
        },
        output_node_id="6",
        reference_method="conditioning_slots",
        reference_bindings=_g_m1_bindings(),
    )
    return svc, wf, version


def _g_patch_service(monkeypatch, root):
    import studio_workflow_run

    def _factory(node_dir):
        from studio_domain import WorkflowDomainService

        svc = WorkflowDomainService(str(node_dir))
        svc._node_def_provider = _g_ref_defs
        return svc

    monkeypatch.setattr(studio_workflow_run, "_get_domain_service", _factory)
    monkeypatch.setitem(
        sys.modules,
        "folder_paths",
        SimpleNamespace(get_input_directory=lambda: str(root / "input")),
    )


def _g_profile():
    return profile_catalog.GoldenProfile(
        name="golden-test",
        owner="test",
        target={
            "app": "configured-app",
            "class": "ModalRuntimeEntrypointV2",
            "method": "run_golden_parallel_stream",
        },
        resources={"gpu": "H100", "cpu": 12, "memory_mb": 24576},
        config=SimpleNamespace(),  # type: ignore[arg-type]
        receipt=SimpleNamespace(deploy_fingerprint="deploy-test"),  # type: ignore[arg-type]
    )


def _g_handle(captured, raw=b"fakepng-bytes"):
    import base64

    class RemoteGenerator:
        def aio(self, payload, **kwargs):
            captured["payload"] = payload
            captured["kwargs"] = kwargs

            async def events():
                yield {"type": "stage", "sequence": 8, "name": "decode"}
                yield {"type": "result", "sequence": 9, "data": {
                    "images": [{
                        "byte_count": len(raw),
                        "data": base64.b64encode(raw).decode("ascii"),
                    }],
                }}

            return events()

    return SimpleNamespace(
        run_golden_studio_stream=SimpleNamespace(remote_gen=RemoteGenerator()),
        run_plan_stream=SimpleNamespace(remote_gen=RemoteGenerator()),
    )


def _g_ref_companion(wf_id, ver_id, images, target=""):
    return {
        "method": "conditioning_slots" if not target else "dedicated",
        "images": list(images),
        "card_ids": [],
        "dedicated_target": target,
        "origin_workflow_id": wf_id,
        "origin_version_id": ver_id,
        "executing_workflow_id": "",
        "executing_version_id": "",
    }


@pytest.mark.asyncio
async def test_golden_generic_agrees_with_ordinary(monkeypatch, tmp_path) -> None:
    """Ordinary + Golden run the same shared mutation: byte-identical graphs."""
    import studio_workflow_run

    root = tmp_path / "svc"
    root.mkdir()
    _, wf, version = _g_setup_service(root)
    _g_patch_service(monkeypatch, root)
    monkeypatch.setattr(studio_golden_run, "resolve_golden_profile", lambda name: _g_profile())
    monkeypatch.setattr(studio_golden_run, "_canonical_golden_fast_path", lambda workflow: False)
    import local_artifacts

    monkeypatch.setattr(local_artifacts, "get_studio_outputs_dir", lambda: tmp_path / "outputs")

    # Ordinary lane through the real shared prep + plan builder.
    bundle = studio_workflow_run.resolve_workflow_run_bundle(
        wf["workflow_id"], version["workflow_version_id"], str(root))
    assert bundle["status"] == "ok"
    merged = studio_workflow_run.merge_workflow_controls(
        bundle["defaults"], {}, bundle["control_schema"])
    ref, err = studio_workflow_run._sanitize_studio_references(
        _g_ref_companion(wf["workflow_id"], version["workflow_version_id"], ["ref_a.png", "ref_b.png"]))
    assert err is None
    prep = studio_workflow_run._prepare_reference_run(
        bundle, ref, merged["values"], str(root))
    assert "error" not in prep, prep.get("error")
    ordinary, ordinary_err = studio_workflow_run.build_workflow_execution_plan(
        bundle, prep["values"],
        modal_options={"production": {"enabled": False}},
        comfyui_root=str(root),
        prompt_mutator=studio_workflow_run._build_reference_prompt_mutator(prep["prep"]),
        studio_references=prep["companion"],
    )
    assert ordinary_err is None

    captured: dict = {}
    store = GoldenStageEventStore(max_events=16, max_runs=2, ttl_seconds=60)
    result = await studio_golden_run.run_golden_workflow(
        workflow_id=wf["workflow_id"],
        version_id=version["workflow_version_id"],
        controls={},
        request_id="golden-refs-agree",
        node_dir=str(root),
        profile_name="golden-test",
        modal_options={"production": {"enabled": False}},
        event_store=store,
        handle_factory=lambda *_args: _g_handle(captured),
        studio_references=_g_ref_companion(
            wf["workflow_id"], version["workflow_version_id"], ["ref_a.png", "ref_b.png"]),
    )
    assert result["status"] == "ok", result
    submitted = captured["payload"]
    assert submitted["workflow"] == ordinary.to_dict()["workflow"]
    assert submitted["workflow_hash"] == ordinary.to_dict()["workflow_hash"]
    companion = submitted["request_metadata"]["studio_references"]
    assert list(companion["images"]) == ["ref_a.png", "ref_b.png"]
    assert companion["method"] == "conditioning_slots"


@pytest.mark.asyncio
async def test_golden_fast_path_submits_final_mutated_graph(monkeypatch, tmp_path) -> None:
    """Classification runs on the FINAL graph; the fast path never submits stripped graphs."""
    root = tmp_path / "svc"
    root.mkdir()
    _, wf, version = _g_setup_service(root)
    _g_patch_service(monkeypatch, root)
    monkeypatch.setattr(studio_golden_run, "resolve_golden_profile", lambda name: _g_profile())
    seen = {}

    def _classifier(workflow):
        seen["graph"] = copy.deepcopy(dict(workflow))
        return True

    monkeypatch.setattr(studio_golden_run, "_canonical_golden_fast_path", _classifier)
    import local_artifacts

    monkeypatch.setattr(local_artifacts, "get_studio_outputs_dir", lambda: tmp_path / "outputs")

    captured: dict = {}
    store = GoldenStageEventStore(max_events=16, max_runs=2, ttl_seconds=60)
    result = await studio_golden_run.run_golden_workflow(
        workflow_id=wf["workflow_id"],
        version_id=version["workflow_version_id"],
        controls={},
        request_id="golden-refs-fast",
        node_dir=str(root),
        profile_name="golden-test",
        event_store=store,
        handle_factory=lambda *_args: _g_handle(captured),
        studio_references=_g_ref_companion(
            wf["workflow_id"], version["workflow_version_id"], ["ref_a.png", "ref_b.png"]),
    )
    assert result["status"] == "ok", result
    # The classifier saw the mutated graph (references included)...
    assert seen["graph"]["7"]["inputs"]["image"] == "ref_a.png"
    assert seen["graph"]["8"]["inputs"]["image"] == "ref_b.png"
    # ...and the fast path submitted exactly that final graph, never the
    # pre-mutation copy, with the frozen companion beside it.
    assert captured["payload"]["prompt"] == seen["graph"]
    extra = captured["payload"]["extra_data"]
    assert list(extra["studio_references"]["images"]) == ["ref_a.png", "ref_b.png"]


@pytest.mark.asyncio
async def test_golden_reference_failure_dispatches_nothing(monkeypatch, tmp_path) -> None:
    root = tmp_path / "svc"
    root.mkdir()
    _, wf, version = _g_setup_service(root)
    _g_patch_service(monkeypatch, root)
    monkeypatch.setattr(studio_golden_run, "resolve_golden_profile", lambda name: _g_profile())
    monkeypatch.setattr(studio_golden_run, "_canonical_golden_fast_path", lambda workflow: False)

    def _forbid(*args, **kwargs):
        raise AssertionError("reference rejection must dispatch nothing")

    store = GoldenStageEventStore(max_events=16, max_runs=2, ttl_seconds=60)
    result = await studio_golden_run.run_golden_workflow(
        workflow_id=wf["workflow_id"],
        version_id=version["workflow_version_id"],
        controls={},
        request_id="golden-refs-fail",
        node_dir=str(root),
        profile_name="golden-test",
        event_store=store,
        handle_factory=_forbid,
        studio_references=_g_ref_companion(
            wf["workflow_id"], version["workflow_version_id"], ["ghost.png", "ref_b.png"]),
    )
    assert result["status"] == "error"
    assert "ghost.png" in result["message"]
    assert store.active_count == 0


@pytest.mark.asyncio
async def test_golden_dedicated_transfers_only_four_roles(monkeypatch, tmp_path) -> None:
    """Golden dedicated shares the ordinary transfer: 4 roles + card binding."""
    import studio_workflow_run
    from studio_domain import WorkflowDomainService
    from studio_domain.models import Mapping, MappingEntry, make_mapping_id, now_iso
    from tests.test_workflow_run_integration import txt2img_prompt

    root = tmp_path / "svc"
    root.mkdir()
    _, override_wf, _ = _g_setup_service(root)
    svc = WorkflowDomainService(str(root))
    svc._node_def_provider = _g_ref_defs
    origin_wf = svc.create_workflow("origin")
    origin_ver = svc.create_version_from_capture(
        origin_wf["workflow_id"],
        {"graph_json": {"id": "g", "nodes": []},
         "api_prompt_json": {"workflow": {}, "output": txt2img_prompt()}},
    )
    svc.store.insert_mapping(Mapping(
        mapping_id=make_mapping_id(),
        workflow_version_id=origin_ver["workflow_version_id"],
        created_at=now_iso(), updated_at=now_iso(),
        output_node_id="6", text_generate_node_id=None,
        entries={
            "positive_prompt": MappingEntry.from_dict({
                "semantic_role": "positive_prompt", "node_id": "1",
                "input_name": "text", "kind": "node_input",
                "control_kind": "multiline", "required": False}),
            "seed": MappingEntry.from_dict({
                "semantic_role": "seed", "node_id": "3",
                "input_name": "seed", "kind": "node_input",
                "control_kind": "integer", "required": False}),
            "steps": MappingEntry.from_dict({
                "semantic_role": "steps", "node_id": "3",
                "input_name": "steps", "kind": "node_input",
                "control_kind": "integer", "required": False}),
        },
        reference_method="dedicated",
        reference_bindings={"dedicated_target": override_wf["workflow_id"], "card_ids": []},
    ))
    _g_patch_service(monkeypatch, root)
    monkeypatch.setattr(studio_golden_run, "resolve_golden_profile", lambda name: _g_profile())
    monkeypatch.setattr(studio_golden_run, "_canonical_golden_fast_path", lambda workflow: False)
    import local_artifacts

    monkeypatch.setattr(local_artifacts, "get_studio_outputs_dir", lambda: tmp_path / "outputs")

    captured: dict = {}
    store = GoldenStageEventStore(max_events=16, max_runs=2, ttl_seconds=60)
    result = await studio_golden_run.run_golden_workflow(
        workflow_id=origin_wf["workflow_id"],
        version_id=origin_ver["workflow_version_id"],
        controls={"positive_prompt": "transferred prompt", "seed": 4242, "steps": 99},
        request_id="golden-refs-dedicated",
        node_dir=str(root),
        profile_name="golden-test",
        modal_options={"production": {"enabled": False}},
        event_store=store,
        handle_factory=lambda *_args: _g_handle(captured),
        studio_references={
            "method": "dedicated",
            "images": ["ref_a.png", "ref_b.png"],
            "card_ids": [],
            "dedicated_target": override_wf["workflow_id"],
            "origin_workflow_id": origin_wf["workflow_id"],
            "origin_version_id": origin_ver["workflow_version_id"],
            "executing_workflow_id": "",
            "executing_version_id": "",
        },
    )
    assert result["status"] == "ok", result
    submitted = captured["payload"]["workflow"]
    assert submitted["2"]["inputs"]["text"] == "transferred prompt"
    assert submitted["4"]["inputs"]["seed"] == 4242
    assert submitted["4"]["inputs"]["steps"] == 5
    assert submitted["7"]["inputs"]["image"] == "ref_a.png"
    companion = captured["payload"]["request_metadata"]["studio_references"]
    assert companion["executing_workflow_id"] == override_wf["workflow_id"]


def test_golden_rejects_method_combination(monkeypatch, tmp_path) -> None:
    import asyncio

    root = tmp_path / "svc"
    root.mkdir()
    _, wf, version = _g_setup_service(root)
    _g_patch_service(monkeypatch, root)
    monkeypatch.setattr(studio_golden_run, "resolve_golden_profile", lambda name: _g_profile())

    def _forbid(*args, **kwargs):
        raise AssertionError("combined request must dispatch nothing")

    store = GoldenStageEventStore(max_events=16, max_runs=2, ttl_seconds=60)
    result = asyncio.run(studio_golden_run.run_golden_workflow(
        workflow_id=wf["workflow_id"],
        version_id=version["workflow_version_id"],
        controls={},
        request_id="golden-refs-combo",
        node_dir=str(root),
        profile_name="golden-test",
        event_store=store,
        handle_factory=_forbid,
        studio_method={"kind": "expand", "method": "pad",
                       "params": {"top": 1, "right": 0, "bottom": 0, "left": 0}},
        studio_references=_g_ref_companion(
            wf["workflow_id"], version["workflow_version_id"], ["ref_a.png"]),
    ))
    assert result["status"] == "error"
    assert "cannot be combined" in result["message"]
    assert store.active_count == 0


def _g_dual_profile():
    profile = _g_profile()
    import dataclasses

    return dataclasses.replace(
        profile,
        resources={
            "gpu": "h100!",
            "gpu_alt": "rtx-pro-6000",
            "gpu_fallbacks": ["rtx-pro-6000", "h100!", "h200", "a100-80gb"],
            "cpu": 12,
            "memory_mb": 24576,
        },
    )


def test_gpu_order_a_returns_profile_unchanged() -> None:
    from gpu_catalog import GOLDEN_ALT_CLASS_NAME

    profile = _g_dual_profile()
    effective = studio_golden_run.effective_profile_for_gpu_order(profile, "A")
    assert effective is profile
    assert effective.target["class"] == "ModalRuntimeEntrypointV2"
    assert GOLDEN_ALT_CLASS_NAME == "ModalRuntimeEntrypointV2Alt"


def test_gpu_order_b_swaps_to_alt_function() -> None:
    from gpu_catalog import GOLDEN_ALT_CLASS_NAME

    profile = _g_dual_profile()
    effective = studio_golden_run.effective_profile_for_gpu_order(profile, "B")
    assert effective is not profile
    assert effective.target["class"] == GOLDEN_ALT_CLASS_NAME
    assert effective.target["app"] == profile.target["app"]
    assert effective.target["method"] == profile.target["method"]
    assert effective.name == profile.name


def test_gpu_order_b_without_alt_refuses() -> None:
    with pytest.raises(GoldenRunError, match="no alt GPU order"):
        studio_golden_run.effective_profile_for_gpu_order(_g_profile(), "B")


def test_gpu_order_rejects_unknown_order() -> None:
    with pytest.raises(GoldenRunError, match="gpu_order must be"):
        studio_golden_run.effective_profile_for_gpu_order(_g_dual_profile(), "C")


def test_gpu_orders_derive_exact_dual_lists() -> None:
    order_a, order_b = profile_catalog.gpu_orders_for({
        "gpu": "h100!",
        "gpu_alt": "rtx-pro-6000",
        "gpu_fallbacks": ["rtx-pro-6000", "h100!", "h200", "a100-80gb"],
    })
    assert order_a == ["h100!", "rtx-pro-6000", "h200", "a100-80gb"]
    assert order_b == ["rtx-pro-6000", "h100!", "h200", "a100-80gb"]


def test_gpu_orders_without_alt_is_single() -> None:
    order_a, order_b = profile_catalog.gpu_orders_for({
        "gpu": "rtx-pro-6000",
        "gpu_alt": "",
        "gpu_fallbacks": [],
    })
    assert order_a == ["rtx-pro-6000"]
    assert order_b == []
