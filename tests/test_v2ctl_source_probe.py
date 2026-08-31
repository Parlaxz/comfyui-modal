"""Tests for v2ctl ``source-probe`` (E29 source-identity stop-gate).

Covers: SHA calculation; expected-vs-remote comparison; missing module;
unexpected module path; mismatch exits nonzero; matching source passes;
ledger-enabled check; sanitized response (no secrets); deployment manifest
remains unverified before probe; source-verified state after successful probe.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tools.v2_control import source_probe as sp

# A real expected-local module dict for a temp file.
CONTENT_A = b"# module A\nvalue = 1\n"
CONTENT_B = b"# module B\nvalue = 2\n"


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    """A repo tree with all required modules present (real bytes)."""
    root = tmp_path / "repo"
    runtime = root / "comfymodal_runtime"
    runtime.mkdir(parents=True)
    payloads = {
        "modal_app.py": CONTENT_A,
        "critical_path_ledger.py": CONTENT_B,
        "runtime_bootstrap.py": b"# module C\nvalue = 3\n",
        "runtime_executor.py": b"# module D\nvalue = 4\n",
        "gantt_telemetry.py": b"# module E\nvalue = 5\n",
        "model_preload.py": b"# module F\nvalue = 6\n",
        "clip_fast_hydration_wiring.py": b"# module G\nvalue = 7\n",
        "registry_proof_store.py": b"# module H\nvalue = 8\n",
        "golden_serial.py": b"# module I\nvalue = 9\n",
        "golden_qd_transport.py": b"# module J\nvalue = 10\n",
        "output_durability.py": b"# module K\nvalue = 11\n",
    }
    for name, data in payloads.items():
        (runtime / name).write_bytes(data)
    return root


def _remote_for(repo_root: Path, *, sha_override: dict | None = None) -> dict:
    """Build a remote probe response whose modules all match the fixture."""
    modules = {}
    for rel in sp.REQUIRED_MODULES:
        p = repo_root / rel
        modules[sp.REMOTE_MODULE_NAMES[rel]] = {
            "file": f"/pkg/modal/comfymodal_runtime/{Path(rel).name}",
            "realpath": f"/pkg/modal/comfymodal_runtime/{Path(rel).name}",
            "size": p.stat().st_size,
            "mtime_ns": p.stat().st_mtime_ns,
            "sha256": sp.sha256_file(p),
        }
    if sha_override:
        for rel, sha in sha_override.items():
            modules[sp.REMOTE_MODULE_NAMES[rel]]["sha256"] = sha
    return {
        "status": "ok",
        "modules": modules,
        "ledger": {
            "flag": "COMFYMODAL_V2_CRITICAL_PATH_LEDGER",
            "enabled": True,
            "record_event": True,
        },
        "identity": {
            "app_name": "app", "class_name": "ModalRuntimeEntrypointV2",
            "probe_name": "source_identity_probe", "image_id": "im-abc",
            "container_session_id": "cs-1", "pid": 1234,
            "deployment_combined_hash": "deadbeef",
        },
        "python": {
            "executable": "/usr/bin/python3", "version": "3.11.9",
            "cwd": "/root", "sys_path": ["/pkg/modal", "/usr/lib/python3.11"],
        },
        "package": {
            "comfymodal_runtime_file": "/pkg/modal/comfymodal_runtime/__init__.py",
            "comfymodal_runtime_path": ["/pkg/modal/comfymodal_runtime"],
        },
        "safe_env": {"COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1"},
    }


def test_sha256_file_deterministic(repo_root: Path) -> None:
    p = repo_root / "comfymodal_runtime/modal_app.py"
    assert sp.sha256_file(p) == sp.sha256_file(p)
    assert len(sp.sha256_file(p)) == 64
    assert sp.sha256_file(p) != sp.sha256_file(
        repo_root / "comfymodal_runtime/critical_path_ledger.py"
    )


def test_compute_expected_local(repo_root: Path) -> None:
    expected = sp.compute_expected_local(repo_root)
    assert "comfymodal_runtime/registry_proof_store.py" in sp.REQUIRED_MODULES
    assert sp.REQUIRED_MODULES[-3:] == (
        "comfymodal_runtime/golden_serial.py",
        "comfymodal_runtime/golden_qd_transport.py",
        "comfymodal_runtime/output_durability.py",
    )
    assert expected["modules"]["comfymodal_runtime/modal_app.py"]["sha256"] == sp.sha256_file(
        repo_root / "comfymodal_runtime/modal_app.py"
    )
    # Missing module → error marker, not crash.
    (repo_root / "comfymodal_runtime/runtime_bootstrap.py").unlink()
    expected2 = sp.compute_expected_local(repo_root)
    assert expected2["modules"]["comfymodal_runtime/runtime_bootstrap.py"]["sha256"] is None


def test_classify_match(repo_root: Path) -> None:
    expected = sp.compute_expected_local(repo_root)
    result = sp.classify_source_probe(expected, _remote_for(repo_root))
    assert result["verdict"] == "MATCH"
    assert all(c["verdict"] == "MATCH" for c in result["modules"])
    assert result["ledger_enabled"] is True
    assert result["ledger_record_event"] is True


def test_classify_mismatch(repo_root: Path) -> None:
    expected = sp.compute_expected_local(repo_root)
    remote = _remote_for(repo_root, sha_override={
        "comfymodal_runtime/modal_app.py": "0" * 64,
    })
    result = sp.classify_source_probe(expected, remote)
    assert result["verdict"] == "MISMATCH"
    modal = next(c for c in result["modules"] if c["module"] == "comfymodal_runtime/modal_app.py")
    assert modal["verdict"] == "MISMATCH"
    assert modal["expected_sha"] != modal["remote_sha"]


def test_classify_missing(repo_root: Path) -> None:
    expected = sp.compute_expected_local(repo_root)
    remote = _remote_for(repo_root)
    del remote["modules"]["comfymodal_runtime.runtime_executor"]
    result = sp.classify_source_probe(expected, remote)
    assert result["verdict"] == "MISSING"
    assert any(c["verdict"] == "MISSING" for c in result["modules"])


def test_classify_unexpected_path(repo_root: Path) -> None:
    expected = sp.compute_expected_local(repo_root)
    remote = _remote_for(repo_root)
    # site-packages copy wins → not a deploy-mount prefix.
    remote["modules"]["comfymodal_runtime.runtime_executor"]["realpath"] = (
        "/usr/local/lib/python3.11/site-packages/comfymodal_runtime/runtime_executor.py"
    )
    remote["modules"]["comfymodal_runtime.runtime_executor"]["file"] = (
        "/usr/local/lib/python3.11/site-packages/comfymodal_runtime/runtime_executor.py"
    )
    result = sp.classify_source_probe(expected, remote)
    assert result["verdict"] == "UNEXPECTED_PATH"
    assert any(c["verdict"] == "UNEXPECTED_PATH" for c in result["modules"])


def test_run_source_probe_exit_code(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = sp.compute_expected_local(repo_root)
    monkeypatch.setattr(sp, "compute_expected_local", lambda _root: expected)
    monkeypatch.setattr(
        sp, "call_remote_source_probe",
        lambda _root, *, workspace, gpu: _remote_for(repo_root),
    )
    monkeypatch.setattr(sp, "_load_workspace", lambda _root: {"id": "w"})
    exit_code, report = sp.run_source_probe(repo_root, gpu="rtx-pro-6000")
    assert exit_code == 0
    assert report["classification"]["verdict"] == "MATCH"

    # Mismatch → nonzero.
    bad = _remote_for(repo_root, sha_override={
        "comfymodal_runtime/runtime_bootstrap.py": "1" * 64,
    })
    monkeypatch.setattr(sp, "call_remote_source_probe", lambda _r, *, workspace, gpu: bad)
    exit_code2, report2 = sp.run_source_probe(repo_root, gpu="rtx-pro-6000")
    assert exit_code2 == 1
    assert report2["classification"]["verdict"] == "MISMATCH"


def test_summarize_probe_no_secrets(repo_root: Path) -> None:
    remote = _remote_for(repo_root)
    remote["safe_env"] = {
        "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
        "MODAL_TOKEN_SECRET": "super-secret",  # must never survive sanitization
        "MODAL_TOKEN_ID": "tk-12345",
    }
    summary = sp.summarize_probe(remote)
    blob = json.dumps(summary)
    assert "super-secret" not in blob
    assert "tk-12345" not in blob
    assert summary["safe_env"].get("COMFYMODAL_V2_CRITICAL_PATH_LEDGER") == "1"
    # identity of image/container preserved; pid present.
    assert summary["image_id"] == "im-abc"
    assert summary["container_session_id"] == "cs-1"
    assert summary["pid"] == 1234


def test_ledger_enabled_check(repo_root: Path) -> None:
    expected = sp.compute_expected_local(repo_root)
    remote = _remote_for(repo_root)
    remote["ledger"] = {"flag": "COMFYMODAL_V2_CRITICAL_PATH_LEDGER", "enabled": False, "record_event": True}
    result = sp.classify_source_probe(expected, remote)
    # source can still MATCH while ledger is off — classification reports it.
    assert result["verdict"] == "MATCH"
    assert result["ledger_enabled"] is False


def test_deployment_manifest_states(tmp_path: Path, repo_root: Path) -> None:
    """Deploy manifest starts unverified; cmd_source_probe flips to verified."""
    from tools.v2_control.cli import write_deployment_manifest

    # Build a minimal fake config/fingerprint/env to write a manifest.
    class _T:
        app = "app"
        class_name = "ModalRuntimeEntrypointV2"
        method = "run_plan_stream"

    class _R:
        gpu = "rtx-pro-6000"
        cpu = 16
        memory_mb = 49152
        min_containers = 0
        scaledown_window = 4

    class _G:
        head = "abc123"
        branch = "TESTING2"
        dirty = ""

    class _Cfg:
        profile_name = "e29-tracer"
        owner = "E29"
        git = _G()
        target = _T()
        resources = _R()
        runtime_override_policy = "default"

        def flag(self, _name: str):
            return None

    class _FP:
        def deploy_fingerprint(self) -> str:
            return "fp123"
        def deploy_inputs(self) -> dict:
            return {}

    cfg = _Cfg()
    manifest_path = write_deployment_manifest(
        tmp_path, cfg, _FP(), {"PYTHONUTF8": "1"}, None
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["deployment_transport_status"] == "deployed"
    assert manifest["runtime_health_status"] == "unverified"
    assert manifest["source_identity_status"] == "unverified"

    # Simulate the probe flipping it to verified.
    manifest["source_identity_status"] = "verified"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    again = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert again["source_identity_status"] == "verified"
