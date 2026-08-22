"""Shared minimal fakes for the Agent C (v2ctl) test suite.

These deliberately do NOT import Agent B's files
(tools/v2_control/backend.py / fingerprints.py / environment.py), so the
tests remain independent of their landing order.  They duck-type against the
contract signatures instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# --------------------------------------------------------------------------
# BackendResult / ArtifactSet fakes (duck-typed against tools/v2_control/backend.py)
# --------------------------------------------------------------------------


@dataclass
class FakeArtifactSet:
    output_dir: Path | None = None
    run_artifact: Path | None = None
    summary_artifact: Path | None = None
    campaign_manifest: Path | None = None
    console_capture: Path | None = None
    # Canonical provenance defaults keep the generic gate fixtures explicit;
    # tests that exercise fail-closed behavior override these with empty
    # values.
    v2ctl_invocation_id: str = "fake-invocation"
    request_id: str = "req-0001"
    request_ids: list[str] = field(default_factory=lambda: ["req-0001"])
    profile: str = "production"
    profile_config_fingerprint: str = "fake-profile-config"
    provenance_validation_status: str = "validated"


@dataclass
class FakeBackendResult:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    command: str = ""
    started_at: str = ""
    ended_at: str = ""
    elapsed_seconds: float = 0.0
    artifacts: FakeArtifactSet = field(default_factory=FakeArtifactSet)

    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass
class FakeBackendRunner:
    """Records invocations; returns a configurable FakeBackendResult.

    ``mode``:
      * "ok"      -> exit 0 with the given stdout/artifacts
      * "fail"    -> exit 1 (backend finished but failed)
      * "raise"   -> raises RuntimeError (backend spawn/timeout failure)
    """

    stdout: str = ""
    stderr: str = ""
    artifacts: FakeArtifactSet | None = None
    mode: str = "ok"
    exit_code: int = 0

    def __post_init__(self) -> None:
        self.invocations: list[dict] = []
        self.invocation_count = 0

    def run(self, spec, *, config, extra_args=(), extra_env=None, capture=True, timeout_seconds=None):
        self.invocation_count += 1
        self.invocations.append(
            {
                "spec": spec,
                "config": config,
                "extra_args": list(extra_args),
                "extra_env": dict(extra_env or {}),
                "capture": capture,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.mode == "raise":
            raise RuntimeError("fake backend crashed at spawn")
        return FakeBackendResult(
            exit_code=self.exit_code if self.mode == "fail" else 0,
            stdout=self.stdout,
            stderr=self.stderr,
            artifacts=self.artifacts or FakeArtifactSet(),
            command="fake-backend",
            started_at="2026-01-01T00:00:00+00:00",
            ended_at="2026-01-01T00:00:01+00:00",
            elapsed_seconds=1.0,
        )


@dataclass
class FakeSpec:
    name: str = "fake-spec"
    bat_path: Path | None = None
    executable: list | None = None
    kind: str = "test_fake"
    description: str = "fake backend spec for tests"
    deploy_only_env: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# FingerprintEngine fake (duck-typed against tools/v2_control/fingerprints.py)
# --------------------------------------------------------------------------


@dataclass
class FakeFingerprints:
    """Deterministic fingerprint engine fake.

    ``inputs`` is the deploy input dict that ``deploy_inputs()`` returns;
    ``deploy_fp`` is derived from it so that mutating the inputs changes the
    fingerprint (mirrors the real engine's sha256-over-canonical-JSON
    semantics).
    """

    inputs: dict = field(default_factory=dict)
    run_inputs_extra: dict = field(default_factory=dict)
    deploy_salt: str = ""
    run_salt: str = ""

    def deploy_fingerprint(self) -> str:
        import hashlib
        import json

        return hashlib.sha256(
            (self.deploy_salt + json.dumps(self.inputs, sort_keys=True, separators=(",", ":"))).encode()
        ).hexdigest()

    def run_fingerprint(self) -> str:
        import hashlib
        import json

        data = {"deploy_fingerprint": self.deploy_fingerprint(), **self.run_inputs_extra}
        return hashlib.sha256(
            (self.run_salt + json.dumps(data, sort_keys=True, separators=(",", ":"))).encode()
        ).hexdigest()

    def deploy_inputs(self) -> dict:
        return dict(self.inputs)


# --------------------------------------------------------------------------
# Minimal ResolvedConfig-like fake
# --------------------------------------------------------------------------


@dataclass
class FakeTarget:
    app: str = "stable-modal-comfy-v2-restore-only-shadow"
    class_name: str = "ModalRuntimeEntrypointV2"
    method: str = "run_plan_stream"


@dataclass
class FakeResources:
    gpu: str = "rtx-pro-6000"
    cpu: int = 12
    memory_mb: int = 32768
    min_containers: int = 0
    scaledown_window: int = 4


@dataclass
class FakeWorkload:
    fresh_required: bool = True
    conditioning_cache: str = "forced_miss"
    expected_output_sha: str = ""
    run_count: int = 10
    gap_seconds: float = 35.0
    nonce: str = "test-nonce"


@dataclass
class FakeGit:
    head: str = "0ba7000bd5f3c7ed52e8d9e0facbc0c598eb6997"
    branch: str = "main"
    dirty: bool = False
    dirty_hashes: dict = field(default_factory=dict)


@dataclass
class FakeFlag:
    name: str
    value: str
    source: str = "profile:production"
    registered: bool = True
    consumed_at: str = "request"
    change_requires: str = "run"
    type: str = "bool"
    description: str = ""


@dataclass
class FakeConfig:
    profile_name: str = "production"
    owner: str = "v2-core"
    target: FakeTarget = field(default_factory=FakeTarget)
    resources: FakeResources = field(default_factory=FakeResources)
    workload: FakeWorkload = field(default_factory=FakeWorkload)
    flags: list = field(default_factory=list)
    unregistered: list = field(default_factory=list)
    runtime_override_policy: str = "forbid"
    git: FakeGit = field(default_factory=FakeGit)

    def flag(self, name: str):
        for flag in self.flags:
            if flag.name == name:
                return flag
        return None


# --------------------------------------------------------------------------
# Validator fake / helpers
# --------------------------------------------------------------------------


@dataclass
class FakeArtifact:
    """A tiny artifact that exists on disk during a test."""

    path: Path

    def is_file(self) -> bool:
        return self.path.is_file()


OK_GATE_STDOUT = (
    "request_id=req-0001\n"
    "correlation_id=corr-0001\n"
    "fresh=1\n"
    "restored=0\n"
    "output_sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260\n"
    "[v2ctl.config] deploy=abc12345 run=def67890 profile=production\n"
)
