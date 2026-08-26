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
        assert data["resources"]["memory_mb"] == 32768
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
            "app": "stable-modal-comfy-v2-golden-p1",
            "class": "ModalRuntimeEntrypointV2",
            "method": "run_golden_serial_stream",
        }
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
            ("deploy-run", "golden_p1", "golden_p1"),
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
