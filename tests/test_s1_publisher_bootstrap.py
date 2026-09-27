"""Focused local contracts for the S1 publisher bootstrap path."""

from __future__ import annotations

import asyncio
import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.v2_control import backend, cli
from tools.v2_control.environment import EnvironmentBuilder
from comfymodal_runtime.publication_policy import CUSTOM_NODES_PUBLISHER_APP_NAME


REPO_ROOT = Path(__file__).resolve().parents[1]


def _args(**overrides):
    values = dict(
        profile=cli.GOLDEN_P1_PROFILE,
        app="batch-s1-cache-e1",
        dry_run=False,
        owner=None,
        set=[],
        inherit=[],
        gpu=None,
        memory_mb=None,
        cpu=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_publisher_name_is_deterministic_and_fails_without_truncation():
    assert cli.derive_publisher_app_name("Batch-S1-Cache-E1") == CUSTOM_NODES_PUBLISHER_APP_NAME
    assert cli.derive_publisher_app_name("another-consumer") == CUSTOM_NODES_PUBLISHER_APP_NAME


def test_backend_registry_publisher_spec_is_native_comfyapp_deploy(tmp_path):
    spec = backend.BackendRegistry(tmp_path).publisher_bootstrap()
    assert spec.kind == "deploy"
    assert spec.bat_path is None
    assert spec.executable == ["modal", "deploy", "-m", "comfyapp"]
    assert backend.BackendRegistry(tmp_path).by_name(spec.name).executable == spec.executable


def test_publisher_bootstrap_dry_run_does_not_load_credentials_or_backend(monkeypatch, capsys):
    class UnexpectedRunner:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("dry-run must not construct a backend")

        @staticmethod
        def build_command_line(spec, extra_args):
            return " ".join(spec.executable + extra_args)

    monkeypatch.setattr(cli.backend_mod, "BackendRunner", UnexpectedRunner)
    monkeypatch.setattr(
        cli,
        "_active_workspace_credentials",
        lambda _root: (_ for _ in ()).throw(AssertionError("dry-run loaded credentials")),
    )

    assert cli.cmd_publisher_bootstrap(_args(dry_run=True), REPO_ROOT) == 0
    output = capsys.readouterr().out
    assert f"modal deploy -m comfyapp --name {CUSTOM_NODES_PUBLISHER_APP_NAME}" in output
    assert f"publisher_app={CUSTOM_NODES_PUBLISHER_APP_NAME}" in output
    assert "deployment_manifest=none" in output


def test_publisher_bootstrap_uses_active_env_lock_and_version_order(monkeypatch):
    events: list = []
    versions = iter((3, 4))

    class FakeLock:
        def __init__(self, _path):
            pass

        def acquire(self, **kwargs):
            events.append(("lock.acquire", kwargs["target"]))

        def release(self):
            events.append("lock.release")

    class FakeResult:
        exit_code = 0
        stdout = ""
        stderr = ""

        def ok(self):
            return True

    class FakeRunner:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def build_command_line(spec, extra_args):
            return " ".join(spec.executable + extra_args)

        def run(self, spec, **kwargs):
            events.append(("backend", spec.executable, kwargs["extra_args"], kwargs["extra_env"]))
            return FakeResult()

    monkeypatch.setattr(cli.locking_mod, "DeployLock", FakeLock)
    monkeypatch.setattr(cli.backend_mod, "BackendRunner", FakeRunner)
    monkeypatch.setattr(cli, "_active_workspace_credentials", lambda _root: {
        "MODAL_TOKEN_ID": "active-id",
        "MODAL_TOKEN_SECRET": "active-secret",
    })
    monkeypatch.setattr(cli, "_app_version_number", lambda app: events.append(("version", app)) or next(versions))
    monkeypatch.setattr(cli, "write_deployment_manifest", lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("publisher bootstrap must not write a Golden manifest")
    ))

    assert cli.cmd_publisher_bootstrap(_args(), REPO_ROOT) == 0
    assert events[0] == ("lock.acquire", CUSTOM_NODES_PUBLISHER_APP_NAME)
    assert events[1] == ("version", CUSTOM_NODES_PUBLISHER_APP_NAME)
    backend_event = events[2]
    assert backend_event[0] == "backend"
    assert backend_event[1] == ["modal", "deploy", "-m", "comfyapp"]
    assert backend_event[2] == ["--name", CUSTOM_NODES_PUBLISHER_APP_NAME]
    assert backend_event[3]["MODAL_TOKEN_ID"] == "active-id"
    assert backend_event[3]["COMFYMODAL_PUBLISHER_ONLY"] == "1"
    assert "V2_BENCHMARK_MODE" not in backend_event[3]
    assert events[3] == ("version", CUSTOM_NODES_PUBLISHER_APP_NAME)
    assert events[4] == "lock.release"


def test_normal_environment_does_not_inherit_publisher_only_selector(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_PUBLISHER_ONLY", "1")
    config = SimpleNamespace(flags=[], unregistered=[])

    env = EnvironmentBuilder().build(config, host_env=os.environ)

    # The selector is an invocation-local backend extra, never an ambient
    # config/profile value that a normal deploy can inherit.
    assert "COMFYMODAL_PUBLISHER_ONLY" not in env


def test_comfyapp_publisher_bootstrap_selects_lightweight_image_without_sync_bypass():
    source = (REPO_ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    assert '_PUBLISHER_ONLY = os.environ.get("COMFYMODAL_PUBLISHER_ONLY", "").strip() == "1"' in source
    assert "CANONICAL_IMAGE_PLAN = None" in source
    assert "image = publisher_image" in source
    sync_start = source.index("def sync_custom_nodes_to_volume(")
    sync_body = source[sync_start:source.find("\ndef ", sync_start + 10)]
    decorator_start = source.rfind("@app.function(", 0, sync_start)
    decorator = source[decorator_start:sync_start]
    assert "image=publisher_image" in decorator
    assert "custom_nodes_vol.commit()" in sync_body

    cli_source = (REPO_ROOT / "tools" / "v2_control" / "cli.py").read_text(encoding="utf-8")
    publisher_block = cli_source[cli_source.index("def cmd_publisher_bootstrap("):]
    deploy_block = cli_source[cli_source.index("def cmd_deploy("):]
    deploy_block = deploy_block[:deploy_block.index("def cmd_deploy_run(")]
    assert '"COMFYMODAL_PUBLISHER_ONLY": "1"' in publisher_block
    assert "COMFYMODAL_PUBLISHER_ONLY" not in deploy_block


def test_sync_custom_nodes_propagates_explicit_publisher_app(monkeypatch):
    calls = []

    class Handle:
        def remote(self, archive):
            calls.append(archive)
            return {"status": "ok"}

    def fake_workspace_function(name, workspace, environment_name=None, app_name=None):
        calls.append((name, workspace["id"], app_name))
        return Handle()

    import modal_client

    monkeypatch.setattr(modal_client, "_workspace_function", fake_workspace_function)
    result = asyncio.run(modal_client.sync_custom_nodes(
        b"archive",
        workspace={"id": "ws", "token_id": "id", "token_secret": "secret"},
        app_name="consumer-a",
    ))
    assert result == {"status": "ok"}
    assert calls[0] == (
        "sync_custom_nodes_to_volume", "ws", CUSTOM_NODES_PUBLISHER_APP_NAME
    )
    assert modal_client.APP_NAME == "comfyui"


def test_sync_result_exposes_persisted_generation_for_host_readback_gate():
    source = (REPO_ROOT / "comfyapp.py").read_text(encoding="utf-8-sig")
    start = source.index("def sync_custom_nodes_to_volume(")
    end = source.find("\ndef ", start + 10)
    body = source[start:end]

    assert '"content_generation": _cn_gen.get("content_generation", "")' in body
    assert '"generation_record_path": CUSTOM_NODES_GENERATION_CONTROL_PATH' in body


def test_publication_failure_diagnostic_reports_generation_triplet_without_payload_dump(
    monkeypatch, tmp_path
):
    from tools.v2_control import custom_nodes as custom_nodes_mod

    decision = SimpleNamespace(
        action="publish",
        reason="publication_incomplete",
        skip=False,
        identity=SimpleNamespace(generation="expected-generation"),
        result={
            "status": "ok",
            "generation": "result-generation",
            "readback_generation": None,
            "secret": "must-not-be-dumped",
        },
    )
    monkeypatch.setattr(custom_nodes_mod, "resolve_custom_nodes_root", lambda _root: tmp_path)
    monkeypatch.setattr(custom_nodes_mod, "run_publish_or_skip", lambda *args, **kwargs: decision)
    monkeypatch.setattr(cli, "_active_workspace", lambda _root: {"id": "workspace"})

    with pytest.raises(cli.GateError) as failure:
        cli._publish_golden_custom_nodes(tmp_path, "publisher-app")

    message = str(failure.value)
    assert '"expected_generation":"expected-gener' in message
    assert '"result_generation":"result-gener' in message
    assert '"readback_generation":null' in message
    assert "must-not-be-dumped" not in message


def test_golden_publisher_wires_s1_identity_into_publication(monkeypatch, tmp_path):
    from comfymodal_runtime import deployment_spec
    from tools.v2_control import custom_nodes as custom_nodes_mod

    source_root = tmp_path / "custom-nodes"
    source_root.mkdir()
    captured = {}

    class Identity:
        custom_node_hash = "canonical-source-generation"
        combined_hash = "combined-deployment-generation"

    def build_identity(runtime_root, *, custom_node_paths):
        captured["runtime_root"] = runtime_root
        captured["custom_node_paths"] = custom_node_paths
        return Identity()

    def fake_publish(root, **kwargs):
        captured["root"] = root
        captured["kwargs"] = kwargs
        generation = kwargs["identity_provider"](Path("different-root"))["generation"]
        return SimpleNamespace(
            action="skip",
            reason="exact_match",
            skip=True,
            identity=SimpleNamespace(generation=generation),
        )

    monkeypatch.setattr(deployment_spec, "build_deployment_identity", build_identity)
    monkeypatch.setattr(custom_nodes_mod, "resolve_custom_nodes_root", lambda _root: source_root)
    monkeypatch.setattr(custom_nodes_mod, "run_publish_or_skip", fake_publish)
    monkeypatch.setattr(cli, "_active_workspace", lambda _root: {"id": "workspace"})

    decision = cli._publish_golden_custom_nodes(tmp_path, "publisher-app")

    assert captured["root"] == source_root
    assert captured["runtime_root"] == tmp_path / "comfymodal_runtime"
    assert captured["custom_node_paths"] == [source_root]
    assert captured["kwargs"]["identity_provider"] is not None
    assert decision.identity.generation == "canonical-source-generation"


def test_publisher_image_carries_canonical_plan_metadata(tmp_path):
    """The lightweight sync image must use the deterministic metadata file handoff."""
    tree = ast.parse(
        (REPO_ROOT / "comfyapp.py").read_text(encoding="utf-8-sig"),
        filename="comfyapp.py",
    )
    publisher_assignment = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "publisher_image"
            for target in node.targets
        )
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "env"
    )

    class FakeIdentity:
        def __init__(self, payload):
            self.payload = payload

        def to_dict(self):
            return self.payload

    class FakeImage:
        def __init__(self):
            self.add_calls = []
            self.file_payload = None
            self.env_payload = None

        def add_local_file(self, *args, **kwargs):
            self.add_calls.append((args, kwargs))
            self.file_payload = Path(args[0]).read_text(encoding="utf-8")
            return self

        def env(self, payload):
            self.env_payload = payload
            return self

    fake_image = FakeImage()
    expected_payload = {
        "canonical_identity": {"canonical": "identity"},
        "source_identity": {"source": "identity"},
    }
    serialized = json.dumps(
        expected_payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    host_metadata_path = tmp_path / ".baked_custom_node_deps" / "canonical_image_plan.json"
    host_metadata_path.parent.mkdir()
    host_metadata_path.write_text(serialized, encoding="utf-8")
    namespace = {
        "CANONICAL_IMAGE_PLAN": SimpleNamespace(
            source_identity=FakeIdentity({"source": "identity"}),
            identity=FakeIdentity({"canonical": "identity"}),
        ),
        "_add_comfymodal_local_python_sources": lambda image: image,
        "modal": SimpleNamespace(
            Image=SimpleNamespace(
                debian_slim=lambda **kwargs: fake_image,
            ),
        ),
        "json": json,
        "_CANONICAL_PLAN_METADATA_HOST_PATH": str(host_metadata_path),
        "_CANONICAL_PLAN_METADATA_IMAGE_PATH": "/opt/comfymodal/canonical_image_plan.json",
        "_CANONICAL_PLAN_METADATA_PATH_ENV": "COMFYMODAL_CANONICAL_IMAGE_PLAN_PATH",
    }
    module = ast.Module(body=[publisher_assignment], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "comfyapp.py", "exec"), namespace)

    assert fake_image.add_calls == [
        (
            (str(host_metadata_path),
             "/opt/comfymodal/canonical_image_plan.json"),
            {"copy": True},
        )
    ]
    assert fake_image.file_payload == serialized
    assert fake_image.env_payload == {
        "COMFYMODAL_CANONICAL_IMAGE_PLAN_PATH": "/opt/comfymodal/canonical_image_plan.json",
    }

    assert serialized == '{"canonical_identity":{"canonical":"identity"},"source_identity":{"source":"identity"}}'


def test_canonical_image_uses_file_handoff_without_inline_plan_payload():
    tree = ast.parse(
        (REPO_ROOT / "comfyapp.py").read_text(encoding="utf-8-sig"),
        filename="comfyapp.py",
    )
    builder = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "build_canonical_image_plan"
    )
    source_assignment = next(
        node
        for node in builder.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "source"
            for target in node.targets
        )
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "add_local_python_source"
    )
    metadata_persist = next(
        node
        for node in builder.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "_persist_canonical_plan_metadata"
    )
    file_handoff = next(
        node
        for node in ast.walk(builder)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_local_file"
    )
    path_env = next(
        node
        for node in ast.walk(builder)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "env"
    )

    assert builder.body.index(metadata_persist) < builder.body.index(source_assignment)
    assert [ast.unparse(argument) for argument in file_handoff.args] == [
        "_CANONICAL_PLAN_METADATA_HOST_PATH",
        "_CANONICAL_PLAN_METADATA_IMAGE_PATH",
    ]
    assert any(
        keyword.arg == "copy"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in file_handoff.keywords
    )
    assert "_CANONICAL_PLAN_METADATA_PATH_ENV" in ast.unparse(path_env)
    assert "_CANONICAL_PLAN_METADATA_IMAGE_PATH" in ast.unparse(path_env)
    assert not any(
        isinstance(node, ast.Name) and node.id == "_CANONICAL_PLAN_METADATA_ENV"
        for node in ast.walk(builder)
    )
