"""Agent B tests: tools/v2_control/environment.py (Batch E32).

Covers (contract §21 subset):
- no ambient experimental env leakage (host COMFYMODAL_V2_* / V2_* never
  leak into the child env unless explicitly in config flags);
- required host vars preserved (PATH, TEMP, ...);
- AUTH_INTERNAL_VARS inherited and redacted in display/provenance;
- --set override semantics (flag value wins over profile/default);
- protected refusal (MODAL_TOKEN_ID, COMFYMODAL_V2_APP_NAME, V2CTL_*,
  AWS_..._TOKEN via --set) -> ProtectedVarError;
- secret redaction: display()/provenance_env() never contain token values;
- ProtectedPolicy.check / is_protected / redact_value / default / to_dict;
- EnvironmentBuilder.classify.

Python 3.11 stdlib + pytest only; no network.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.v2_control.environment import (  # noqa: E402
    AUTH_INTERNAL_VARS,
    EXPERIMENTAL_PREFIXES,
    REQUIRED_HOST_VARS,
    EnvironmentBuilder,
    ProtectedPolicy,
)
from tools.v2_control.errors import ProtectedVarError  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal ResolvedConfig duck-type (Agent A's config.py is not required).
# ---------------------------------------------------------------------------


@dataclass
class _Target:
    app: str = "stable-modal-comfy-v2-restore-only-shadow"
    class_name: str = "ModalRuntimeEntrypointV2"
    method: str = "run_plan_stream"


@dataclass
class _Resources:
    gpu: str = "rtx-pro-6000"
    cpu: int = 12
    memory_mb: int = 32768
    min_containers: int = 0
    scaledown_window: int = 4


@dataclass
class _Workload:
    fresh_required: bool = True
    conditioning_cache: str = "forced_miss"
    expected_output_sha: str = ""
    run_count: int = 10
    gap_seconds: float = 35.0
    nonce: str = "test-nonce"


@dataclass
class _Git:
    head: str = "0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997"
    branch: str = "main"
    dirty: bool = False
    dirty_hashes: dict = field(default_factory=dict)


@dataclass
class _Flag:
    name: str
    value: str
    source: str = "set"  # explicit override channel (the refusal-relevant source)
    registered: bool = True
    consumed_at: str = "request"
    change_requires: str = "run"
    type: str = "bool"
    description: str = ""


@dataclass
class _Config:
    profile_name: str = "production"
    owner: str = "v2-core"
    target: _Target = field(default_factory=_Target)
    resources: _Resources = field(default_factory=_Resources)
    workload: _Workload = field(default_factory=_Workload)
    flags: list = field(default_factory=list)
    unregistered: list = field(default_factory=list)
    runtime_override_policy: str = "forbid"
    git: _Git = field(default_factory=_Git)


def _flag(name: str, value: str, change_requires: str = "run") -> _Flag:
    return _Flag(name=name, value=value, change_requires=change_requires)


def _host_env(**extra) -> dict[str, str]:
    base = {
        "PATH": r"C:\Windows\System32;C:\Python311",
        "COMSPEC": r"C:\Windows\System32\cmd.exe",
        "SYSTEMROOT": r"C:\Windows",
        "WINDIR": r"C:\Windows",
        "TEMP": r"C:\Users\x\AppData\Local\Temp",
        "TMP": r"C:\Users\x\AppData\Local\Temp",
        "PATHEXT": ".COM;.EXE;.BAT;.CMD",
        "USERPROFILE": r"C:\Users\x",
        "APPDATA": r"C:\Users\x\AppData\Roaming",
        "LOCALAPPDATA": r"C:\Users\x\AppData\Local",
        "HOMEDRIVE": "C:",
        "HOMEPATH": r"\Users\x",
        "OS": "Windows_NT",
        "PROCESSOR_ARCHITECTURE": "AMD64",
        "NUMBER_OF_PROCESSORS": "16",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "PYTHONHOME": r"C:\Python311",
        "COMPUTERNAME": "HOST-X",
        "USERNAME": "parla",
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# No ambient leakage
# ---------------------------------------------------------------------------


def test_no_ambient_experimental_leakage():
    host = _host_env(
        COMFYMODAL_V2_SOMETHING="1",
        V2_X="2",
        COMFYMODAL_V2_ANOTHER="3",
    )
    env = EnvironmentBuilder().build(_Config(), host_env=host)
    assert "COMFYMODAL_V2_SOMETHING" not in env
    assert "V2_X" not in env
    assert "COMFYMODAL_V2_ANOTHER" not in env
    # required host vars still present
    assert env["PATH"] == host["PATH"]
    assert env["COMSPEC"] == host["COMSPEC"]
    assert env["TEMP"] == host["TEMP"]


def test_config_flags_do_appear():
    host = _host_env(COMFYMODAL_V2_AMBIENT="9")
    config = _Config(
        flags=[_flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "1", "deploy")],
        unregistered=[_flag("V2_BRAND_NEW_EXPERIMENT", "1", "unknown")],
    )
    env = EnvironmentBuilder().build(config, host_env=host)
    assert env["COMFYMODAL_V2_UNET_FASTSAFETENSORS"] == "1"
    assert env["V2_BRAND_NEW_EXPERIMENT"] == "1"
    # the ambient COMFYMODAL_* value is NOT copied
    assert "COMFYMODAL_V2_AMBIENT" not in env


def test_auth_internal_vars_inherited_from_host():
    host = _host_env(
        MODAL_TOKEN_ID="tok_123",
        MODAL_TOKEN_SECRET="sek_456",
        MODAL_ENVIRONMENT="main",
    )
    env = EnvironmentBuilder().build(_Config(), host_env=host)
    assert env["MODAL_TOKEN_ID"] == "tok_123"
    assert env["MODAL_TOKEN_SECRET"] == "sek_456"
    assert env["MODAL_ENVIRONMENT"] == "main"


def test_backend_extra_merged_after_flags():
    host = _host_env()
    config = _Config(flags=[_flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "0")])
    env = EnvironmentBuilder().build(
        config,
        host_env=host,
        backend_extra={"COMFYMODAL_DEPLOY_ONLY": "1", "V2_BENCHMARK_RUNS": "1"},
    )
    assert env["COMFYMODAL_DEPLOY_ONLY"] == "1"
    assert env["V2_BENCHMARK_RUNS"] == "1"
    assert env["COMFYMODAL_V2_UNET_FASTSAFETENSORS"] == "0"


def test_build_is_deterministic():
    host = _host_env(MODAL_TOKEN_ID="tok")
    config = _Config(flags=[_flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "1")])
    a = EnvironmentBuilder().build(config, host_env=host)
    b = EnvironmentBuilder().build(config, host_env=host)
    assert a == b


# ---------------------------------------------------------------------------
# Protected refusal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
        "MODAL_CLIENT_SECRET",
        "MODAL_ENVIRONMENT",
        "MODAL_CLIENT_ID",
        "MODAL_AUTH",
        "COMFYMODAL_V2_APP_NAME",
        "COMFYMODAL_V2_CLASS_NAME",
        "COMFYMODAL_V2_GPU",
        "COMFYMODAL_V2_MEMORY_MB",
        "COMFYMODAL_V2_CPU_REQUEST",
        "COMFYMODAL_V2_RESTORE_ONLY_APP_NAME",
        "V2_DEPLOY_IDENT",
        "COMFYMODAL_COMMAND_START_UNIX_MS",
        "COMFYMODAL_DEPLOY_TIMEOUT_SECONDS",
        "V2CTL_PROVENANCE",
        "V2CTL_DEPLOY_FINGERPRINT",
        "V2CTL_RUN_FINGERPRINT",
        "V2CTL_OWNER",
        "V2CTL_PROFILE",
    ],
)
def test_protected_flag_refused_in_build(name):
    policy = ProtectedPolicy.default()
    assert policy.is_protected(name)
    config = _Config(flags=[_flag(name, "1")])
    with pytest.raises(ProtectedVarError):
        EnvironmentBuilder(policy).build(config, host_env=_host_env())


def test_protected_prefix_refused():
    policy = ProtectedPolicy.default()
    # MODAL_ prefix (auth namespace)
    with pytest.raises(ProtectedVarError):
        policy.check("MODAL_FUTURE_AUTH_VAR")
    # V2CTL_ prefix (v2ctl internal namespace)
    with pytest.raises(ProtectedVarError):
        policy.check("V2CTL_SOME_INTERNAL")


def test_secret_marker_refused():
    policy = ProtectedPolicy.default()
    assert policy.is_protected("MY_AWS_SECRET_ACCESS_KEY")
    assert policy.is_protected("COMFYMODAL_V2_DB_PASSWORD")
    with pytest.raises(ProtectedVarError):
        policy.check("MY_AWS_SECRET_ACCESS_KEY")


def test_regex_cloud_credential_refused():
    policy = ProtectedPolicy.default()
    assert policy.is_protected("AWS_ACCESS_TOKEN")
    assert policy.is_protected("GITHUB_TOKEN")
    assert policy.is_protected("HF_READ_TOKEN")
    with pytest.raises(ProtectedVarError):
        policy.check("AWS_ACCESS_TOKEN")


def test_non_protected_ok():
    policy = ProtectedPolicy.default()
    for name in ("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "V2_BENCHMARK_RUNS", "PATH"):
        assert not policy.is_protected(name)
        policy.check(name)  # must not raise


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def test_display_redacts_auth_and_secrets():
    builder = EnvironmentBuilder()
    env = {
        "PATH": r"C:\Windows",
        "MODAL_TOKEN_ID": "tok_123",
        "MODAL_TOKEN_SECRET": "sek_456",
        "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "1",
        "COMFYMODAL_V2_DB_PASSWORD": "hunter2",
        "GITHUB_TOKEN": "ghp_abc",
    }
    shown = builder.display(env)
    assert shown["MODAL_TOKEN_ID"] == "<redacted>"
    assert shown["MODAL_TOKEN_SECRET"] == "<redacted>"
    assert shown["COMFYMODAL_V2_DB_PASSWORD"] == "<redacted>"
    assert shown["GITHUB_TOKEN"] == "<redacted>"
    assert shown["PATH"] == r"C:\Windows"
    assert shown["COMFYMODAL_V2_UNET_FASTSAFETENSORS"] == "1"
    # raw secret values never appear in redacted output
    joined = repr(shown)
    assert "tok_123" not in joined
    assert "sek_456" not in joined
    assert "hunter2" not in joined
    assert "ghp_abc" not in joined


def test_provenance_env_never_contains_token_values():
    builder = EnvironmentBuilder()
    host = _host_env(MODAL_TOKEN_ID="tok_123", MODAL_TOKEN_SECRET="sek_456")
    config = _Config(flags=[_flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "1")])
    env = builder.build(config, host_env=host)
    prov = builder.provenance_env(env)
    assert prov["MODAL_TOKEN_ID"] == "<redacted>"
    assert prov["MODAL_TOKEN_SECRET"] == "<redacted>"
    assert prov["COMFYMODAL_V2_UNET_FASTSAFETENSORS"] == "1"
    assert "tok_123" not in repr(prov)
    assert "sek_456" not in repr(prov)


def test_secret_named_flag_refused_and_redacted():
    # Secret-named flags (API_KEY marker) are refused at build time...
    builder = EnvironmentBuilder()
    config = _Config(flags=[_flag("COMFYMODAL_V2_API_KEY", "abc123")])
    with pytest.raises(ProtectedVarError):
        builder.build(config, host_env=_host_env())
    # ...and even if present in a raw env, display redacts them.
    shown = builder.display({"COMFYMODAL_V2_API_KEY": "abc123"})
    assert shown["COMFYMODAL_V2_API_KEY"] == "<redacted>"
    assert "abc123" not in repr(shown)


def test_redact_value_secret_vs_plain():
    policy = ProtectedPolicy.default()
    assert policy.redact_value("COMFYMODAL_V2_TOKEN", "x") == "<redacted>"
    assert policy.redact_value("AWS_SECRET_KEY", "x") == "<redacted>"
    assert policy.redact_value("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "1") == "1"
    assert policy.redact_value("PATH", r"C:\Windows") == r"C:\Windows"


def test_redact_value_exact_name_but_not_secret_shape():
    # COMFYMODAL_V2_APP_NAME is protected but not secret-shaped -> value kept
    policy = ProtectedPolicy.default()
    assert policy.redact_value("COMFYMODAL_V2_APP_NAME", "some-app") == "some-app"
    assert policy.is_protected("COMFYMODAL_V2_APP_NAME")


# ---------------------------------------------------------------------------
# Policy introspection / classify
# ---------------------------------------------------------------------------


def test_default_policy_contains_contract_names():
    policy = ProtectedPolicy.default()
    for name in (
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
        "MODAL_CLIENT_SECRET",
        "MODAL_ENVIRONMENT",
        "V2_DEPLOY_IDENT",
        "COMFYMODAL_V2_APP_NAME",
        "COMFYMODAL_V2_CLASS_NAME",
        "COMFYMODAL_V2_GPU",
        "COMFYMODAL_V2_MEMORY_MB",
        "COMFYMODAL_V2_CPU_REQUEST",
        "COMFYMODAL_V2_RESTORE_ONLY_APP_NAME",
        "COMFYMODAL_COMMAND_START_UNIX_MS",
        "COMFYMODAL_DEPLOY_TIMEOUT_SECONDS",
        "V2CTL_PROVENANCE",
        "V2CTL_DEPLOY_FINGERPRINT",
        "V2CTL_RUN_FINGERPRINT",
        "V2CTL_OWNER",
        "V2CTL_PROFILE",
    ):
        assert name in policy.exact_names, name
    assert policy.prefixes == ("MODAL_", "V2CTL_")
    assert len(policy.regexes) == 1


def test_policy_to_dict():
    d = ProtectedPolicy.default().to_dict()
    assert d["exact_names"] == sorted(d["exact_names"])
    assert "MODAL_TOKEN_ID" in d["exact_names"]
    assert d["prefixes"] == ["MODAL_", "V2CTL_"]
    assert "TOKEN" in d["secret_markers"]
    assert len(d["regexes"]) == 1


def test_classify():
    assert EnvironmentBuilder.classify("PATH") == "required"
    assert EnvironmentBuilder.classify("MODAL_TOKEN_ID") == "protected"
    assert EnvironmentBuilder.classify("COMFYMODAL_V2_APP_NAME") == "protected"
    assert EnvironmentBuilder.classify("V2CTL_OWNER") == "protected"
    assert EnvironmentBuilder.classify("COMFYMODAL_V2_UNET_FASTSAFETENSORS") == "experimental"
    assert EnvironmentBuilder.classify("V2_BENCHMARK_RUNS") == "experimental"
    assert EnvironmentBuilder.classify("SOME_OTHER_VAR") == "other"


# ---------------------------------------------------------------------------
# Required-host-vars contract surface
# ---------------------------------------------------------------------------


def test_required_host_vars_constant():
    for name in ("PATH", "COMSPEC", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
                 "PATHEXT", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                 "HOMEDRIVE", "HOMEPATH", "OS", "PROCESSOR_ARCHITECTURE",
                 "NUMBER_OF_PROCESSORS", "PYTHONIOENCODING", "PYTHONUTF8",
                 "PYTHONHOME", "COMPUTERNAME", "USERNAME"):
        assert name in REQUIRED_HOST_VARS
    assert len(REQUIRED_HOST_VARS) == 20


def test_auth_internal_vars_constant():
    assert AUTH_INTERNAL_VARS == (
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
        "MODAL_ENVIRONMENT",
        "MODAL_CLIENT_ID",
        "MODAL_CLIENT_SECRET",
        "MODAL_AUTH",
    )


def test_experimental_prefixes_constant():
    assert EXPERIMENTAL_PREFIXES == ("COMFYMODAL_", "V2_")
