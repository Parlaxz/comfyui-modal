"""CLI integration tests for v2ctl (Batch E32).

Exercises tools/v2ctl.py end-to-end against the REAL repo config trees and
the REAL backend scripts — but never invokes a backend (dry-run, or refusal
paths).  No network, no Modal.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
V2CTL = REPO_ROOT / "tools" / "v2ctl.py"


def run_v2ctl(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(V2CTL), *argv],
        cwd=REPO_ROOT,
        env=full_env,
        capture_output=True,
        text=True,
        timeout=120,
    )


class TestVersion:
    def test_version_exits_zero(self) -> None:
        r = run_v2ctl("version")
        assert r.returncode == 0
        assert "v2ctl" in r.stdout


class TestConfig:
    def test_config_production_json(self) -> None:
        r = run_v2ctl("config", "--json")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["profile"] == "production"
        assert data["target"]["app"] == "stable-modal-comfy-v2-restore-only-shadow"
        assert data["target"]["class"] == "ModalRuntimeEntrypointV2"
        assert data["target"]["method"] == "run_plan_stream"
        assert data["resources"]["gpu"] == "rtx-pro-6000"
        assert data["resources"]["memory_mb"] == 8192
        assert data["runtime_override_policy"] == "forbid"
        assert data["deploy_fingerprint"] and data["run_fingerprint"]
        names = {f["name"] for f in data["flags"]}
        assert "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE" in names
        assert "COMFYMODAL_V2_ENV_PROFILE" in names
        # Registered flag metadata printed
        fp32 = next(f for f in data["flags"] if f["name"] == "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE")
        assert fp32["consumed_at"] == "module_import"
        assert fp32["change_requires"] == "deploy"
        assert fp32["source"] == "default"  # production profile does not override it
        assert fp32["value"] == "0"

    def test_config_golden_p1_uses_dedicated_target_method_and_flag(self) -> None:
        r = run_v2ctl("config", "--profile", "golden_p1", "--json")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["profile"] == "golden_p1"
        assert data["target"] == {
            "app": "batch-r0-golden-ops",
            "class": "ModalRuntimeEntrypointV2",
            "method": "run_golden_serial_stream",
        }
        assert data["resources"]["memory_mb"] == 8192
        flags = {flag["name"]: flag["value"] for flag in data["flags"]}
        assert flags["COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM"] == "1"
    def test_config_e29_profile(self) -> None:
        r = run_v2ctl("config", "--profile", "e29-tracer", "--json")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["profile"] == "e29-tracer"
        assert data["owner"] == "E29"
        vals = {f["name"]: f["value"] for f in data["flags"]}
        assert vals["COMFYMODAL_V2_GANTT_TELEMETRY"] == "1"
        assert vals["V2_BENCHMARK_RUNS"] == "1"

    def test_config_missing_profile_fails(self) -> None:
        r = run_v2ctl("config", "--profile", "no-such-profile")
        assert r.returncode == 1
        assert "ERROR" in r.stderr

    def test_config_set_precedence_and_unregistered(self) -> None:
        r = run_v2ctl("config", "--json",
                      "--set", "COMFYMODAL_V2_UNET_FASTSAFETENSORS=1",
                      "--set", "COMFYMODAL_V2_BRAND_NEW_EXPERIMENT=1")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        vals = {f["name"]: f["value"] for f in data["flags"]}
        assert vals["COMFYMODAL_V2_UNET_FASTSAFETENSORS"] == "1"
        unreg = {u["name"]: u["value"] for u in data["unregistered"]}
        assert unreg["COMFYMODAL_V2_BRAND_NEW_EXPERIMENT"] == "1"

    def test_config_inherit_from_ambient(self) -> None:
        r = run_v2ctl("config", "--json",
                      "--inherit", "V2_MY_AMBIENT_FLAG",
                      env={"V2_MY_AMBIENT_FLAG": "7"})
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        unreg = {u["name"]: u["value"] for u in data["unregistered"]}
        assert unreg["V2_MY_AMBIENT_FLAG"] == "7"

    def test_config_inherit_missing_fails(self) -> None:
        r = run_v2ctl("config", "--inherit", "V2_NOT_SET_ANYWHERE")
        assert r.returncode == 1
        assert "ERROR" in r.stderr

    def test_config_protected_set_refused(self) -> None:
        r = run_v2ctl("config", "--set", "MODAL_TOKEN_ID=leak-token-value")
        assert r.returncode == 1
        assert "MODAL_TOKEN_ID" in r.stderr
        assert "leak-token-value" not in r.stdout

    def test_config_ambient_experiment_env_not_merged(self) -> None:
        r = run_v2ctl("config", "--json",
                      env={"COMFYMODAL_V2_UNET_FASTSAFETENSORS": "1",
                           "V2_BENCHMARK_RUNS": "99"})
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        vals = {f["name"]: f["value"] for f in data["flags"]}
        assert vals["COMFYMODAL_V2_UNET_FASTSAFETENSORS"] == "0"
        assert vals["V2_BENCHMARK_RUNS"] == "10"


class TestGate1FlatSafety:
    @pytest.mark.parametrize("command", ["config", "doctor", "deploy", "deploy-run", "run"])
    @pytest.mark.parametrize("allow_production", [False, True])
    def test_flat_commands_refuse_protected_app_before_backend(
        self, command: str, allow_production: bool, monkeypatch, capsys
    ) -> None:
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control import cli

        class UnexpectedBackend:
            def __init__(self, *args, **kwargs):
                raise AssertionError("protected app refusal must not invoke a backend")

        monkeypatch.setattr(cli.backend_mod, "BackendRunner", UnexpectedBackend)
        argv = [command, "--app", "stable-modal-comfy-v2-golden-p1", "--dry-run"]
        if allow_production:
            argv.append("--allow-production")

        assert cli.main(argv) == 2
        captured = capsys.readouterr()
        assert "production-protected" in captured.err
        assert "no invocation performed" not in captured.out

    @pytest.mark.parametrize("command", ["config", "doctor", "deploy", "deploy-run", "run"])
    def test_non_golden_profile_refuses_golden_mode_before_backend(
        self, command: str, monkeypatch, capsys
    ) -> None:
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control import cli

        class UnexpectedBackend:
            def __init__(self, *args, **kwargs):
                raise AssertionError("Golden mode refusal must not invoke a backend")

        monkeypatch.setattr(cli.backend_mod, "BackendRunner", UnexpectedBackend)
        assert cli.main([
            command,
            "--profile", "production",
            "--app", "gate1-experimental",
            "--set", "V2_BENCHMARK_MODE=golden_p1_serial",
            "--dry-run",
        ]) == 1
        captured = capsys.readouterr()
        assert "golden_p1_serial" in captured.err
        assert "non-Golden profile" in captured.err
        assert "no invocation performed" not in captured.out


class TestGoldenNamespace:
    def test_filtered_manifest_lookup_ignores_newer_unrelated_deployment(self, tmp_path) -> None:
        from tools.v2_control import cli

        manifest_dir = tmp_path / ".v2ctl" / "deployments"
        manifest_dir.mkdir(parents=True)

        def write(name: str, manifest: dict) -> None:
            (manifest_dir / name).write_text(json.dumps(manifest), encoding="utf-8")

        base = {
            "schema_version": cli.SCHEMA_VERSION,
            "deployment_hash_namespace": cli.DEPLOYMENT_HASH_NAMESPACE,
            "fingerprint_algorithm": cli.FINGERPRINT_ALGORITHM,
        }
        write(
            "deploy_20260830-090243_s1.json",
            {
                **base,
                "profile": "golden_p1",
                "deploy_fingerprint": "s1-fingerprint",
                "deployment_hash": "s1-fingerprint",
                "deploy_inputs": {
                    "target": {
                        "app": "batch-s1-cache-e1",
                        "class_name": "ModalRuntimeEntrypointV2",
                        "method": "run_golden_serial_stream",
                    }
                },
            },
        )
        write(
            "deploy_20260830-090427_ra5.json",
            {
                **base,
                "profile": "golden_p1",
                "deploy_fingerprint": "ra5-fingerprint",
                "deployment_hash": "ra5-fingerprint",
                "target": {
                    "app": "batch-ra5-attention-shootout",
                    "class": "ModalRuntimeEntrypointV2",
                    "method": "run_golden_serial_stream",
                },
            },
        )

        target = {
            "app": "batch-s1-cache-e1",
            "class": "ModalRuntimeEntrypointV2",
            "method": "run_golden_serial_stream",
        }
        selected = cli.latest_deployment_manifest(
            tmp_path, profile="golden_p1", target=target
        )
        assert selected is not None
        assert selected["deploy_fingerprint"] == "s1-fingerprint"
        selected_path = cli.latest_deployment_manifest_path(
            tmp_path, profile="golden_p1", target=target
        )
        assert selected_path is not None
        assert selected_path.name == "deploy_20260830-090243_s1.json"

    def test_filtered_manifest_lookup_returns_none_without_valid_match(self, tmp_path) -> None:
        from tools.v2_control import cli

        manifest_dir = tmp_path / ".v2ctl" / "deployments"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "deploy_20260830-090243_invalid.json").write_text(
            json.dumps({"schema_version": 1}), encoding="utf-8"
        )
        assert cli.latest_deployment_manifest(
            tmp_path,
            profile="golden_p1",
            target={
                "app": "batch-s1-cache-e1",
                "class": "ModalRuntimeEntrypointV2",
                "method": "run_golden_serial_stream",
            },
        ) is None

    def test_golden_doctor_uses_dedicated_profile_namespace(self) -> None:
        r = run_v2ctl("golden", "doctor")
        assert r.returncode in (0, 1)
        assert "[v2ctl.doctor]" in r.stdout
        assert "git.head=" in r.stdout

    def test_golden_namespace_rejects_internal_config_command(self) -> None:
        r = run_v2ctl("golden", "config", "--json")
        assert r.returncode == 2
        assert "publisher-bootstrap" in r.stderr

    def test_golden_namespace_rejects_other_profile(self) -> None:
        r = run_v2ctl("golden", "doctor", "--profile", "e29-tracer")
        assert r.returncode == 1
        assert "golden_p1" in r.stderr

    def test_golden_run_rejects_more_than_one_request(self) -> None:
        r = run_v2ctl("golden", "run", "--run-count", "2", "--dry-run")
        assert r.returncode == 2
        assert "exactly one request" in r.stderr

    @pytest.mark.parametrize(
        "mode",
        ["acceptance", "variance_cold", "variance_matrix", "volume_read", "snapshot_restore_only"],
    )
    def test_golden_run_rejects_explicit_generic_mode(self, mode: str) -> None:
        r = run_v2ctl(
            "golden", "run", "--dry-run", "--app", "golden-review-experimental",
            "--set", f"V2_BENCHMARK_MODE={mode}",
        )
        assert r.returncode == 1
        assert "V2_BENCHMARK_MODE" in r.stderr
        assert mode in r.stderr
        assert "only golden_p1_serial is allowed" in r.stderr
        assert "no invocation performed" not in r.stdout

    def test_golden_run_accepts_only_canonical_mode(self) -> None:
        r = run_v2ctl(
            "golden", "run", "--dry-run", "--app", "golden-review-experimental",
            "--set", "V2_BENCHMARK_MODE=golden_p1_serial",
        )
        assert r.returncode == 0, r.stderr
        assert "no invocation performed" in r.stdout
        assert "V2_BENCHMARK_MODE=golden_p1_serial" in r.stdout

    def test_golden_deploy_dry_run_uses_native_modal_deploy(self) -> None:
        r = run_v2ctl("golden", "deploy", "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "profile=golden_p1" in r.stdout
        assert "golden_p1" in r.stdout
        assert "modal deploy -m comfymodal_runtime.modal_app" in r.stdout
        assert "--name" in r.stdout
        assert "deploy_and_run_v2_single.bat" not in r.stdout
        assert "no invocation performed" in r.stdout

    def test_golden_namespace_accepts_global_options_after_command(self) -> None:
        r = run_v2ctl(
            "golden", "deploy", "--dry-run",
            "--app", "Batch-R0-Golden-Ops",
            "--gpu", "rtx-pro-6000",
        )
        assert r.returncode == 0, r.stderr
        assert "COMFYMODAL_V2_APP_NAME=batch-r0-golden-ops" in r.stdout
        assert "COMFYMODAL_V2_GPU=rtx-pro-6000" in r.stdout

    def test_golden_status_honors_explicit_experimental_app(self) -> None:
        r = run_v2ctl("golden", "status", "--json", "--app", "Batch-R0-golden-ops")
        assert r.returncode in (0, 1)
        assert r.stderr == ""
        data = json.loads(r.stdout)
        assert data["target"]["app"] == "batch-r0-golden-ops"

    def test_golden_rejects_production_target_without_explicit_override(self) -> None:
        r = run_v2ctl(
            "golden", "deploy", "--app", "stable-modal-comfy-v2-golden-p1"
        )
        assert r.returncode == 2
        assert "production-protected" in r.stderr

    def test_golden_rejects_invalid_experimental_app_name(self) -> None:
        r = run_v2ctl("golden", "deploy", "--dry-run", "--app", "Batch_R0")
        assert r.returncode == 2
        assert "invalid Golden app name" in r.stderr

    @pytest.mark.parametrize("command", ["status", "doctor", "deploy", "run"])
    def test_golden_hard_denies_protected_app_even_read_only_dry_run(self, command) -> None:
        argv = ["golden", command, "--app", "STABLE-MODAL-COMFY-V2-GOLDEN-P1"]
        if command in {"deploy", "run"}:
            argv.append("--dry-run")
        r = run_v2ctl(*argv)
        assert r.returncode == 2
        assert "production-protected" in r.stderr

    @pytest.mark.parametrize("command", ["status", "doctor", "deploy", "run"])
    def test_golden_allow_production_is_not_a_bypass(self, command) -> None:
        r = run_v2ctl("golden", command, "--allow-production", "--dry-run")
        assert r.returncode == 2
        assert "allow-production" in r.stderr

    @pytest.mark.parametrize("command", ["deploy", "deploy-run", "run"])
    def test_flat_golden_command_hard_denies_protected_app(self, command) -> None:
        r = run_v2ctl(
            command, "--profile", "golden_p1", "--app",
            "STABLE-MODAL-COMFY-V2-GOLDEN-P1", "--dry-run",
        )
        assert r.returncode == 2
        assert "production-protected" in r.stderr

    def test_golden_commands_share_resolved_identity(self) -> None:
        outputs = {}
        for command in ("status", "doctor", "deploy", "run"):
            argv = ["golden", command, "--app", "Batch-R0-Golden-Ops"]
            if command == "status":
                argv.append("--json")
            if command in {"deploy", "run"}:
                argv.append("--dry-run")
            r = run_v2ctl(*argv)
            assert r.returncode in (0, 1), r.stderr
            outputs[command] = r.stdout
        assert (
            '"app": "batch-r0-golden-ops"' in outputs["status"]
            or "target={'app': 'batch-r0-golden-ops'" in outputs["status"]
        )
        assert "target.app=batch-r0-golden-ops" in outputs["doctor"]
        for command in ("deploy", "run"):
            assert "COMFYMODAL_V2_APP_NAME=batch-r0-golden-ops" in outputs[command]
            assert "profile=golden_p1" in outputs[command]

    def test_golden_status_is_read_only_and_reports_remote_boundary(self) -> None:
        r = run_v2ctl("golden", "status", "--json")
        assert r.returncode in (0, 1)
        assert r.stderr == ""
        data = json.loads(r.stdout)
        assert data["profile"] == "golden_p1"
        assert data["target"]["method"] == "run_golden_serial_stream"
        assert data["remote_checks"] == "not_performed"
        assert isinstance(data["deployed_state_present"], bool)
        assert isinstance(data["deployed_state_target_match"], bool)

    def test_golden_status_does_not_adopt_unrelated_manifest_health(self, monkeypatch, tmp_path, capsys) -> None:
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control import cli

        monkeypatch.setattr(
            cli,
            "latest_deployment_manifest",
            lambda _root, **_kwargs: {
                "profile": "golden_p1",
                "deploy_fingerprint": "stale",
                "target": {
                    "app": "stable-modal-comfy-v2-golden-p1",
                    "class": "ModalRuntimeEntrypointV2",
                    "method": "run_golden_serial_stream",
                },
                "runtime_health_status": "verified",
                "source_identity_status": "verified",
            },
        )
        monkeypatch.setattr(cli, "_deployment_manifest_dir", lambda _root: tmp_path)
        args = SimpleNamespace(
            profile="golden_p1", app=None, gpu=None, memory_mb=None, cpu=None,
            owner=None, set=[], inherit=[], json=True,
            workspace_id=None, workspace=None, environment=None,
        )
        components = cli._build_components_for_args(REPO_ROOT, args)
        config, fingerprints = components[3], components[4]
        destination = SimpleNamespace(
            workspace_id="workspace-from-config",
            workspace_label="configured-workspace",
            environment="main",
        )
        config.modal_destination = destination
        expected_fingerprint = fingerprints.deploy_fingerprint()
        config.modal_destination = None
        monkeypatch.setattr(cli, "_build_components_for_args", lambda _root, _args: components)
        monkeypatch.setattr(
            cli,
            "_canonical_workspace_binding",
            lambda _args, _root, bound_config: (
                setattr(bound_config, "modal_destination", destination) or destination
            ),
        )
        assert cli.cmd_golden_status(args, REPO_ROOT) == 1
        data = json.loads(capsys.readouterr().out)
        assert data["target"]["app"] == "batch-r0-golden-ops"
        assert data["deployment_target_match"] is False
        assert data["deployment_fingerprint_match"] is False
        assert data["runtime_health_status"] == "unverified"
        assert data["source_identity_status"] == "unverified"
        assert data["deployment_fingerprint_current"] == expected_fingerprint

    def test_golden_status_is_not_ready_while_next_request_guarded(
        self, monkeypatch, tmp_path, capsys
    ) -> None:
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control import cli

        args = SimpleNamespace(
            profile="golden_p1", app="golden-experimental", gpu=None,
            memory_mb=None, cpu=None, owner=None, set=[], inherit=[], json=True,
        )
        components = cli._build_components_for_args(REPO_ROOT, args)
        config, fingerprints = components[3], components[4]
        target = {
            "app": config.target.app,
            "class": config.target.class_name,
            "method": config.target.method,
        }
        (tmp_path / ".deployed_state.json").write_text(
            json.dumps({"app_name": config.target.app, "class_name": config.target.class_name}),
            encoding="utf-8",
        )
        monkeypatch.setattr(cli, "_build_components_for_args", lambda _root, _args: components)
        monkeypatch.setattr(
            cli,
            "latest_deployment_manifest",
            lambda _root, **_kwargs: {
                "profile": "golden_p1",
                "deploy_fingerprint": fingerprints.deploy_fingerprint(),
                "target": target,
                "runtime_health_status": "verified",
                "source_identity_status": "verified",
            },
        )
        monkeypatch.setattr(cli, "_deployment_manifest_dir", lambda _root: tmp_path / "deployments")

        class PendingGuard:
            @staticmethod
            def deployment_identity(**kwargs):
                return "test-deployment"

            @staticmethod
            def path_for_deployment(root, identity):
                return tmp_path / "guard.json"

            def __init__(self, path, deployment_identity=None):
                pass

            def snapshot(self):
                return {"post_capture_guard_pending": True}

        class NoopLock:
            def __init__(self, path):
                pass

            def status(self):
                return None

        class NoOverrides:
            def __init__(self, **kwargs):
                pass

            def list_local(self):
                return []

        monkeypatch.setattr(cli, "_golden_capture_guard_class", lambda _root: PendingGuard)
        monkeypatch.setattr(cli.locking_mod, "DeployLock", NoopLock)
        monkeypatch.setattr(cli.ro_mod, "RuntimeOverrideInventory", NoOverrides)

        assert cli.cmd_golden_status(args, tmp_path) == 1
        data = json.loads(capsys.readouterr().out)
        assert data["next_request_guarded"] is True
        assert data["ready"] is False

    def test_flat_golden_deploy_run_refuses_before_backend(self, monkeypatch, capsys) -> None:
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control import cli

        class UnexpectedBackend:
            def __init__(self, *args, **kwargs):
                raise AssertionError("flat Golden deploy-run must not construct a backend")

        monkeypatch.setattr(cli.backend_mod, "BackendRunner", UnexpectedBackend)
        args = SimpleNamespace(
            profile="golden_p1", app="golden-experimental", set=[], inherit=[],
            owner=None, dry_run=False, gpu=None, memory_mb=None, cpu=None,
        )

        assert cli.cmd_deploy_run(args, REPO_ROOT) == 2
        error = capsys.readouterr().err
        assert "flat `v2ctl deploy-run" in error
        assert "v2ctl golden deploy" in error


class TestGoldenDeployVersionVerification:
    def test_app_version_lookup_distinguishes_absent_from_uncertain(
        self, monkeypatch
    ) -> None:
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control import cli

        class Result:
            def __init__(self, returncode, stdout="", stderr=""):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        outputs = iter([
            Result(1, stderr="App 'new-app' not found"),
            Result(1, stderr="permission denied while listing app history"),
            Result(0, stdout="header only\n"),
            Result(0, stdout="| v7 | deployment |\n"),
        ])
        monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: next(outputs))
        assert cli._app_version_number("new-app") == 0
        assert cli._app_version_number("uncertain-app") is None
        assert cli._app_version_number("empty-history") is None
        assert cli._app_version_number("deployed-app") == 7

    def test_native_golden_deploy_env_has_no_generic_benchmark_controls(self):
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control import cli

        env = cli._native_golden_deploy_env({
            "V2_BENCHMARK_MODE": "golden_p1_serial",
            "V2_BENCHMARK_RUNS": "1",
            "V2_E28_VALIDATION": "1",
            "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
        })
        assert not any(name.startswith("V2_") for name in env)
        assert env["COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM"] == "1"

    def test_public_golden_deploy_requires_real_version_advance(
        self, monkeypatch, tmp_path, capsys
    ) -> None:
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control import cli
        from tools.v2_control.backend import BackendResult

        backend_calls = []
        lock_instances = []
        manifest = tmp_path / "deploy.json"

        class FakeRunner:
            def __init__(self, repo_root, env_builder):
                pass

            @staticmethod
            def build_command_line(spec, extra_args):
                return "fake-backend"

            def run(self, *args, **kwargs):
                backend_calls.append(kwargs)
                return BackendResult(
                    exit_code=0, stdout="", stderr="", command="fake-backend",
                    started_at="2026-01-01T00:00:00+00:00",
                    ended_at="2026-01-01T00:00:01+00:00", elapsed_seconds=1.0,
                )

        class FakeLock:
            def __init__(self, path):
                lock_instances.append(self)

            def acquire(self, **kwargs):
                pass

            def release(self):
                pass

        def fake_manifest(*args, **kwargs):
            manifest.write_text("{}", encoding="utf-8")
            return manifest

        monkeypatch.setattr(cli.backend_mod, "BackendRunner", FakeRunner)
        monkeypatch.setattr(cli.locking_mod, "DeployLock", FakeLock)
        monkeypatch.setattr(cli, "write_deployment_manifest", fake_manifest)
        # Keep this version-advance unit test isolated from the repository's
        # persistent Golden receipt ledger.
        monkeypatch.setattr(
            cli, "_write_golden_deployment_receipt",
            lambda *args, **kwargs: tmp_path / "deployment-receipt.json",
        )
        # Native Golden deploys gate Modal deployment on verified custom-node
        # publication.  Keep this version-advance test focused on its existing
        # contract by supplying that verified publication explicitly.
        monkeypatch.setattr(
            cli,
            "_publish_golden_custom_nodes",
            lambda _root: SimpleNamespace(
                action="published", reason="published_verified", identity=SimpleNamespace(
                    generation="test-generation",
                    identity_schema=1,
                    packaging_policy_version=1,
                    file_count=0,
                    total_bytes=0,
                    manifest_digest="test-manifest",
                )
            ),
        )
        args = SimpleNamespace(
            profile="golden_p1", app="golden-experimental", set=[], inherit=[],
            owner=None, dry_run=False, gpu=None, memory_mb=None, cpu=None,
            golden_public=True,
        )

        versions = iter((7, 8, 8, 8))
        monkeypatch.setattr(cli, "_app_version_number", lambda app: next(versions))
        assert cli.cmd_deploy(args, REPO_ROOT) == 0
        assert manifest.exists()

        # A second backend exit 0 with no version advance is not a valid deploy.
        assert cli.cmd_deploy(args, REPO_ROOT) == 1
        assert not manifest.exists()
        assert len(backend_calls) == 2
        assert lock_instances
        assert "version did NOT advance" in capsys.readouterr().err


class TestFlags:
    def test_flags_list(self) -> None:
        r = run_v2ctl("flags", "list")
        assert r.returncode == 0
        assert "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE" in r.stdout

    def test_flags_explain_registered(self) -> None:
        r = run_v2ctl("flags", "explain", "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE")
        assert r.returncode == 0
        assert "consumed_at=module_import" in r.stdout
        assert "change_requires=deploy" in r.stdout

    def test_flags_explain_unregistered(self) -> None:
        r = run_v2ctl("flags", "explain", "COMFYMODAL_V2_NEVER_EXISTS")
        assert r.returncode == 0
        assert "UNREGISTERED" in r.stdout

    def test_flags_validate_ok(self) -> None:
        r = run_v2ctl("flags", "validate", "COMFYMODAL_V2_UNET_FASTSAFETENSORS=1")
        assert r.returncode == 0
        assert "VALID" in r.stdout

    def test_flags_validate_type_error(self) -> None:
        r = run_v2ctl("flags", "validate", "COMFYMODAL_V2_UNET_FASTSAFETENSORS=banana")
        assert r.returncode == 1
        assert "INVALID" in r.stderr

    def test_flags_validate_bad_syntax(self) -> None:
        r = run_v2ctl("flags", "validate", "NOVALUE")
        assert r.returncode == 1

    def test_flags_audit_runs(self) -> None:
        r = run_v2ctl("flags", "audit")
        assert r.returncode == 0
        assert "advisory lint" in r.stdout


class TestDryRun:
    def test_deploy_dry_run(self) -> None:
        r = run_v2ctl("deploy", "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "deploy_and_run_v2_single.bat" in r.stdout
        assert "COMFYMODAL_DEPLOY_ONLY=1" in r.stdout
        assert "no invocation performed" in r.stdout

    def test_deploy_manifest_is_truthful_about_health(self, tmp_path) -> None:
        """A deploy manifest must distinguish transport status from runtime
        health: deploy exit 0 proves transport only; runtime health stays
        'unverified' until a gate/run observes the container actually run."""
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control.cli import build_components, write_deployment_manifest
        from tools.v2_control.backend import BackendResult

        registry, profiles, resolver, config, fingerprints, env_builder, backend_registry = (
            build_components(REPO_ROOT, "e29-tracer")
        )
        result = BackendResult(
            exit_code=0, stdout="App deployed!", stderr="", command="deploy",
            started_at="2026-01-01T00:00:00+00:00", ended_at="2026-01-01T00:00:01+00:00",
            elapsed_seconds=1.0,
        )
        manifest_path = write_deployment_manifest(
            tmp_path, config, fingerprints, {}, result,
        )
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["deployment_transport_status"] == "deployed"
        assert data["runtime_health_status"] == "unverified"
        assert "unverified" in data["health_check_note"]

    def test_deploy_run_dry_run(self) -> None:
        r = run_v2ctl("deploy-run", "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "deploy_and_run_v2_single.bat" in r.stdout

    def test_run_dry_run_without_deployment_refused(self) -> None:
        # Ensure no deployment manifest can interfere (fresh tmp state is not
        # possible for the real repo; instead assert the refusal path when the
        # manifest dir is absent).
        manifest_dir = REPO_ROOT / ".v2ctl" / "deployments"
        if not manifest_dir.is_dir():
            r = run_v2ctl("run", "--dry-run")
            assert r.returncode == 1
            assert "no deployment manifest" in r.stderr
        else:
            pytest.skip("a real deployment manifest exists in the repo; dry-run path covered elsewhere")

    def test_run_refuses_deploy_required_change(self) -> None:
        r = run_v2ctl("run", "--dry-run", "--set", "COMFYMODAL_V2_UNET_FASTSAFETENSORS=1")
        assert r.returncode == 1
        assert "run-only configuration refuses changed deploy-required flags" in r.stderr
        assert "COMFYMODAL_V2_UNET_FASTSAFETENSORS" in r.stderr

    def test_run_refuses_unregistered_flag(self) -> None:
        r = run_v2ctl("run", "--dry-run", "--set", "COMFYMODAL_V2_NEW_UNSAFE_THING=1")
        assert r.returncode == 1
        assert "unregistered" in r.stderr

    def test_run_refuses_snapshot_restore_only_mode(self) -> None:
        # The snapshot-restore-only mode is a PROBE (run_snapshot_restore_only_probe)
        # that never invokes run_plan_stream and produces no generation artifact.
        # The v2ctl full-run guard must refuse it directly (unit-level, so the
        # deployment-manifest check cannot mask the guard).
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control.cli import _require_full_run_mode
        from tools.v2_control.errors import GateError
        from tools.v2_control.config import ConfigResolver

        resolver = ConfigResolver(
            REPO_ROOT,
            __import__("tools.v2_control.profiles", fromlist=["Profiles"]).Profiles(
                REPO_ROOT / "config" / "v2" / "profiles"
            ),
            __import__("tools.v2_control.registry", fromlist=["FlagRegistry"]).FlagRegistry(
                REPO_ROOT / "config" / "v2" / "flag_registry.toml"
            ),
        )
        # A profile with the probe mode must be refused.
        config = resolver.resolve(
            profile_name="production",
            sets=[("V2_BENCHMARK_MODE", "snapshot_restore_only")],
        )
        with pytest.raises(GateError, match="snapshot_restore_only"):
            _require_full_run_mode(config, command="v2ctl run")
        # The e29-tracer profile (full run) must pass the guard.
        config_e29 = resolver.resolve(profile_name="e29-tracer")
        _require_full_run_mode(config_e29, command="v2ctl gate")

        # Only golden_p1 may select the dedicated Golden method.
        config_non_golden = resolver.resolve(profile_name="production")
        config_non_golden.target.method = "run_golden_serial_stream"
        with pytest.raises(GateError, match="non-Golden profiles"):
            _require_full_run_mode(config_non_golden, command="v2ctl gate")

    @pytest.mark.parametrize(
        "mode",
        ["acceptance", "variance_cold", "variance_matrix", "volume_read", "snapshot_restore_only"],
    )
    def test_flat_golden_run_rejects_explicit_generic_mode(self, mode: str) -> None:
        r = run_v2ctl(
            "run", "--profile", "golden_p1", "--dry-run", "--app",
            "golden-review-experimental", "--set", f"V2_BENCHMARK_MODE={mode}",
        )
        assert r.returncode == 1
        assert "only golden_p1_serial is allowed" in r.stderr

    def test_e29_tracer_profile_forces_full_run_mode(self) -> None:
        # The e29-tracer profile must resolve to a FULL generation mode
        # (e28_single), never the snapshot-restore-only probe default.
        r = run_v2ctl("config", "--profile", "e29-tracer", "--json")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        flags = {f["name"]: f["value"] for f in data.get("flags", [])}
        assert flags.get("V2_BENCHMARK_MODE") == "e28_single"
        assert flags.get("V2_E28_VALIDATION") == "1"

    def test_dry_run_env_is_redacted(self) -> None:
        r = run_v2ctl("deploy", "--dry-run",
                      env={"MODAL_TOKEN_ID": "sekrit-token", "MODAL_TOKEN_SECRET": "sekrit-secret"})
        assert r.returncode == 0, r.stderr
        assert "sekrit-token" not in r.stdout
        assert "sekrit-secret" not in r.stdout
        # Keys may appear but only with redacted values.
        assert "MODAL_TOKEN_ID=<redacted>" in r.stdout

    def test_deploy_failure_surfaces_bounded_diagnostics_and_success_stays_quiet(
        self, monkeypatch, tmp_path, capsys
    ) -> None:
        """Failed backend streams are diagnostic-only; deploy bookkeeping is unchanged."""
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control import cli
        from tools.v2_control.backend import BackendResult

        manifest = tmp_path / "deploy.json"
        lock_instances = []
        result = BackendResult(
            exit_code=7,
            stdout=("backend stdout\n" + ("diagnostic-line\n" * 1000)
                    + "terminal-bat-error\n"),
            stderr="backend stderr\nMODAL_TOKEN_SECRET=sekrit-backend-token\n",
            command="fake-backend",
            started_at="2026-01-01T00:00:00+00:00",
            ended_at="2026-01-01T00:00:01+00:00",
            elapsed_seconds=1.0,
        )

        class FakeLock:
            def __init__(self, path):
                self.released = False
                lock_instances.append(self)

            def acquire(self, **kwargs):
                pass

            def release(self):
                self.released = True

        class FakeRunner:
            def __init__(self, repo_root, env_builder):
                pass

            @staticmethod
            def build_command_line(spec, extra_args):
                return "fake-backend"

            def run(self, *args, **kwargs):
                return result

        def fake_manifest(*args, **kwargs):
            manifest.write_text("{}", encoding="utf-8")
            return manifest

        monkeypatch.setenv("MODAL_TOKEN_SECRET", "sekrit-backend-token")
        monkeypatch.setattr(cli.locking_mod, "DeployLock", FakeLock)
        monkeypatch.setattr(cli.backend_mod, "BackendRunner", FakeRunner)
        monkeypatch.setattr(cli, "write_deployment_manifest", fake_manifest)
        # Version lookup is a required deploy preflight.  The failed backend
        # consumes the first pre-version; the later successful deploy consumes
        # the remaining pre/post pair.
        versions = iter((0, 0, 1))
        monkeypatch.setattr(cli, "_app_version_number", lambda app: next(versions))
        args = SimpleNamespace(
            profile="production", set=[], inherit=[], owner=None, dry_run=False,
            app=None, gpu=None, memory_mb=None, cpu=None,
        )

        assert cli.cmd_deploy(args, REPO_ROOT) == 7
        failed_output = capsys.readouterr().err
        assert "BEGIN backend diagnostics" in failed_output
        assert failed_output.index("backend stderr") < failed_output.index("backend stdout")
        assert "--- backend stderr (head) ---" in failed_output
        assert "--- backend stderr (tail) ---" in failed_output
        assert "--- backend stdout (head) ---" in failed_output
        assert "--- backend stdout (tail) ---" in failed_output
        stdout_head = failed_output.index("--- backend stdout (head) ---")
        stdout_tail = failed_output.index("--- backend stdout (tail) ---")
        assert "terminal-bat-error" not in failed_output[stdout_head:stdout_tail]
        assert "terminal-bat-error" in failed_output[stdout_tail:]
        assert "sekrit-backend-token" not in failed_output
        assert "diagnostic output truncated" in failed_output
        assert "END backend diagnostics" in failed_output
        assert not manifest.exists()
        assert lock_instances[-1].released

        result.exit_code = 0
        versions = iter((0, 1))
        monkeypatch.setattr(cli, "_app_version_number", lambda app: next(versions))
        assert cli.cmd_deploy(args, REPO_ROOT) == 0
        success_output = capsys.readouterr().err
        assert "backend diagnostics" not in success_output
        assert manifest.exists()
        assert lock_instances[-1].released


class TestBackendSelectorForwarding:
    @pytest.mark.parametrize(
        ("command", "profile", "selector"),
        [
            ("deploy", "e31-clip-fp32-qd4-arm-b", "E31_VALIDATION"),
            ("deploy-run", "e31-clip-fp32-qd4-arm-b", "E31_VALIDATION"),
            ("deploy-run", "e29-tracer", "E28_VALIDATION"),
        ],
    )
    def test_selector_reaches_backend_and_matches_printed_command(
        self, command, profile, selector, monkeypatch, tmp_path, capsys
    ) -> None:
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control import cli
        from tools.v2_control.backend import BackendResult

        command_args = []
        run_args = []

        class FakeRunner:
            def __init__(self, repo_root, env_builder):
                pass

            @staticmethod
            def build_command_line(spec, extra_args):
                command_args.append(list(extra_args))
                return "fake-backend " + " ".join(extra_args)

            def run(self, *args, **kwargs):
                run_args.append(list(kwargs["extra_args"]))
                return BackendResult(
                    exit_code=0,
                    stdout="",
                    stderr="",
                    command="fake-backend",
                    started_at="2026-01-01T00:00:00+00:00",
                    ended_at="2026-01-01T00:00:01+00:00",
                    elapsed_seconds=1.0,
                )

        class FakeLock:
            def __init__(self, path):
                pass

            def acquire(self, **kwargs):
                pass

            def release(self):
                pass

        manifest = tmp_path / "deploy.json"

        def fake_manifest(*args, **kwargs):
            manifest.write_text("{}", encoding="utf-8")
            return manifest

        monkeypatch.setattr(cli.backend_mod, "BackendRunner", FakeRunner)
        monkeypatch.setattr(cli.locking_mod, "DeployLock", FakeLock)
        monkeypatch.setattr(cli, "write_deployment_manifest", fake_manifest)
        if command == "deploy":
            versions = iter((0, 1))
            monkeypatch.setattr(cli, "_app_version_number", lambda app: next(versions))

        args = SimpleNamespace(
            profile=profile,
            set=[],
            inherit=[],
            owner=None,
            dry_run=False,
            app=None,
            gpu=None,
            memory_mb=None,
            cpu=None,
        )
        handler = cli.cmd_deploy if command == "deploy" else cli.cmd_deploy_run

        assert handler(args, REPO_ROOT) == 0
        assert command_args == [[selector]]
        assert run_args == [[selector]]
        assert f"fake-backend {selector}" in capsys.readouterr().out


class TestRuntimeFlags:
    def test_runtime_flags_list(self) -> None:
        r = run_v2ctl("runtime-flags", "list")
        assert r.returncode == 0
        assert "runtime_override_policy=forbid" in r.stdout
        assert "remote listing: not available" in r.stdout

    def test_runtime_flags_clear_missing(self) -> None:
        r = run_v2ctl("runtime-flags", "clear", "DEFINITELY_NOT_A_FLAG")
        assert r.returncode == 1
        assert "not present locally" in r.stdout

    def test_runtime_flags_clear_all_requires_confirm(self) -> None:
        r = run_v2ctl("runtime-flags", "clear-all")
        assert r.returncode == 2  # argparse required --confirm


class TestLock:
    def test_lock_status_none(self) -> None:
        r = run_v2ctl("lock", "status")
        assert r.returncode == 0
        assert "deploy.lock=none" in r.stdout

    def test_lock_acquire_conflict_release(self) -> None:
        # acquire
        r = run_v2ctl("lock", "acquire", "--owner", "e32test", "--target", "t")
        assert r.returncode == 0, r.stderr
        try:
            # conflicting acquire fails
            r = run_v2ctl("lock", "acquire", "--owner", "other")
            assert r.returncode == 1
            assert "ERROR" in r.stderr
            # status shows owner
            r = run_v2ctl("lock", "status")
            assert "owner=e32test" in r.stdout
            # release by other owner fails
            r = run_v2ctl("lock", "release", "--owner", "other")
            assert r.returncode == 1
        finally:
            r = run_v2ctl("lock", "force-release", "--owner", "e32test")
            assert r.returncode == 0, r.stderr
        r = run_v2ctl("lock", "status")
        assert "deploy.lock=none" in r.stdout


class TestGateConfirm:
    def test_confirm_dry_run_reports_e28_selector(self) -> None:
        r = run_v2ctl(
            "--profile", "e29-tracer", "confirm", "--dry-run",
            "--from", "does-not-need-to-exist.json", "--runs", "3",
        )
        assert r.returncode == 0, r.stderr
        assert "selector=E28_VALIDATION" in r.stdout
        assert "E28_VALIDATION" in r.stdout
        assert "--run-count 1" in r.stdout
        assert "--conditioning-cache-nonce" in r.stdout
        assert "V2_E28_CONDITIONING_NONCE=" in r.stdout
        assert "V2_BENCHMARK_RUNS=1" in r.stdout

    def test_e31_qd4_profile_uses_distinct_selector_and_nonce(self) -> None:
        r = run_v2ctl(
            "--profile", "e31-clip-fp32-qd4-arm-b", "confirm", "--dry-run",
            "--from", "does-not-need-to-exist.json",
        )
        assert r.returncode == 0, r.stderr
        assert "selector=E31_VALIDATION" in r.stdout
        assert "E31_VALIDATION" in r.stdout
        assert "--run-count 1" in r.stdout
        assert "--conditioning-cache-nonce" in r.stdout
        assert "V2_E31_CONDITIONING_NONCE=" in r.stdout
        assert "V2_E28_VALIDATION=0" in r.stdout

    def test_gate_requires_deployment(self) -> None:
        manifest_dir = REPO_ROOT / ".v2ctl" / "deployments"
        if not manifest_dir.is_dir():
            r = run_v2ctl("gate", "--dry-run")
            assert r.returncode == 1
            assert "gate requires a deployment" in r.stderr
        else:
            pytest.skip("a real deployment manifest exists; gate refusal path covered elsewhere")

    def test_gate_requires_manifest_target_match_alongside_fingerprint(
        self, monkeypatch, capsys
    ) -> None:
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control import cli

        _, _, _, config, fingerprints, _, _ = cli.build_components(REPO_ROOT, "production")

        class NoopLock:
            def __init__(self, path):
                pass

            def status(self):
                return None

            def is_stale(self, status):
                return False

        monkeypatch.setattr(cli.locking_mod, "DeployLock", NoopLock)
        monkeypatch.setattr(
            cli,
            "latest_deployment_manifest",
            lambda _root, **_kwargs: {
                "deploy_fingerprint": fingerprints.deploy_fingerprint(),
                "target": {
                    "app": "wrong-target",
                    "class": config.target.class_name,
                    "method": config.target.method,
                },
            },
        )
        args = SimpleNamespace(
            profile="production", app=None, gpu=None, memory_mb=None, cpu=None,
            owner=None, set=[], inherit=[], dry_run=True,
        )

        assert cli.cmd_gate(args, REPO_ROOT) == 1
        assert "deployment target mismatch" in capsys.readouterr().err

    def test_confirm_requires_from(self) -> None:
        r = run_v2ctl("confirm")
        assert r.returncode == 2  # argparse: --from required


class TestDoctor:
    def test_doctor_reports_and_exits(self) -> None:
        r = run_v2ctl("doctor")
        assert r.returncode in (0, 1)
        assert "git.head=" in r.stdout
        assert "backend.deploy_and_run_v2_single.exists=1" in r.stdout
        assert "registry.flags=" in r.stdout
        assert "profiles=" in r.stdout

    def test_doctor_uses_destination_bound_fingerprint(
        self, monkeypatch, capsys
    ) -> None:
        sys.path.insert(0, str(REPO_ROOT))
        from tools.v2_control import cli

        args = SimpleNamespace(
            profile="golden_p1", app="golden-experimental", gpu=None,
            memory_mb=None, cpu=None, owner=None, set=[], inherit=[],
            workspace_id=None, workspace=None, environment=None,
        )
        components = cli._build_components_for_args(REPO_ROOT, args)
        config, fingerprints = components[3], components[4]
        destination = SimpleNamespace(
            workspace_id="workspace-from-config",
            workspace_label="configured-workspace",
            environment="main",
        )
        config.modal_destination = destination
        expected_fingerprint = fingerprints.deploy_fingerprint()
        config.modal_destination = None
        target = {
            "app": config.target.app,
            "class": config.target.class_name,
            "method": config.target.method,
        }

        monkeypatch.setattr(cli, "_build_components_for_args", lambda _root, _args: components)
        monkeypatch.setattr(
            cli,
            "_canonical_workspace_binding",
            lambda _args, _root, bound_config: (
                setattr(bound_config, "modal_destination", destination) or destination
            ),
        )
        monkeypatch.setattr(
            cli,
            "latest_deployment_manifest",
            lambda _root, **_kwargs: {
                "profile": "golden_p1",
                "deploy_fingerprint": expected_fingerprint,
                "target": target,
            },
        )

        monkeypatch.setattr(
            cli.locking_mod, "DeployLock",
            lambda _path: SimpleNamespace(status=lambda: None),
        )
        monkeypatch.setattr(
            cli.ro_mod, "RuntimeOverrideInventory",
            lambda **_kwargs: SimpleNamespace(list_local=lambda: []),
        )

        assert cli.cmd_doctor(args, REPO_ROOT) == 0
        output = capsys.readouterr().out
        assert f"deployment.fingerprint.current={expected_fingerprint}" in output
        assert "deployment.fingerprint.match=1" in output
