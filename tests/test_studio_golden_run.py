from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

import studio_golden_run
from studio_golden_run import GoldenRunError, GoldenStageEventStore, browser_override_error
from tools.v2_control import profile_catalog


pytestmark = pytest.mark.fast_unit


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
        "resources": {"gpu": "H100", "cpu": 12, "memory_mb": 24576},
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
