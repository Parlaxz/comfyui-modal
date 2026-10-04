"""v2ctl ``source-probe``: prove the exact bytes the deployed class imports.

The E29 source-identity stop-gate.  Computes EXPECTED_LOCAL source identities
(SHA-256 of the exact filesystem bytes that ``add_local_python_source`` would
upload for the deploy), invokes the deployed GPU class's no-generation
``source_identity_probe`` method through the SAME Modal class/transport used
by ``run_plan_stream``, and classifies every required module:

- MATCH          : remote SHA-256 == EXPECTED_LOCAL SHA-256
- MISMATCH       : remote module exists but bytes differ
- MISSING        : remote module absent
- UNEXPECTED_PATH: remote module loaded from a path that cannot be the
                   deployed source mount (e.g. a site-packages copy winning
                   over the add_local_python_source mount)

The command exits nonzero on any MISMATCH/MISSING/UNEXPECTED_PATH so a wrong
deployment can never be mistaken for valid.

This is the only v2ctl command that makes a direct Modal SDK call; it invokes
NO generation and NO sampling — the probe method is read-only.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Modules that must byte-match the deployed image.
REQUIRED_MODULES = (
    "comfymodal_runtime/modal_app.py",
    "comfymodal_runtime/config_authority.py",
    "comfymodal_runtime/deployment_spec.py",
    "comfymodal_runtime/critical_path_ledger.py",
    "comfymodal_runtime/runtime_bootstrap.py",
    "comfymodal_runtime/runtime_executor.py",
    "comfymodal_runtime/gantt_telemetry.py",
    "comfymodal_runtime/model_preload.py",
    "comfymodal_runtime/clip_fast_hydration_wiring.py",
    "comfymodal_runtime/registry_proof_store.py",
    "comfymodal_runtime/golden_serial.py",
    "comfymodal_runtime/golden_io_process_v2.py",
    "comfymodal_runtime/golden_model_transport.py",
    "comfymodal_runtime/golden_qd_transport.py",
    "comfymodal_runtime/golden_source_threads.py",
    # P9 source/destination copy-isolation experiment.  Proven here because a
    # deployment that omitted it would still pass every other identity check
    # while silently running no arm at all -- exactly the failure 975aec14 had
    # to fix for the per-copy probe.
    "comfymodal_runtime/source_copy_isolation.py",
    "comfymodal_runtime/source_population_policy.py",
    "comfymodal_runtime/source_copy_probe.py",
    "comfymodal_runtime/source_stall_classification.py",
    "comfymodal_runtime/golden_parallel.py",
    "comfymodal_runtime/output_durability.py",
)

# Remote module names (dotted, as imported inside the container).
REMOTE_MODULE_NAMES = {
    "comfymodal_runtime/modal_app.py": "comfymodal_runtime.modal_app",
    "comfymodal_runtime/config_authority.py": "comfymodal_runtime.config_authority",
    "comfymodal_runtime/deployment_spec.py": "comfymodal_runtime.deployment_spec",
    "comfymodal_runtime/critical_path_ledger.py": "comfymodal_runtime.critical_path_ledger",
    "comfymodal_runtime/runtime_bootstrap.py": "comfymodal_runtime.runtime_bootstrap",
    "comfymodal_runtime/runtime_executor.py": "comfymodal_runtime.runtime_executor",
    "comfymodal_runtime/gantt_telemetry.py": "comfymodal_runtime.gantt_telemetry",
    "comfymodal_runtime/model_preload.py": "comfymodal_runtime.model_preload",
    "comfymodal_runtime/clip_fast_hydration_wiring.py": "comfymodal_runtime.clip_fast_hydration_wiring",
    "comfymodal_runtime/registry_proof_store.py": "comfymodal_runtime.registry_proof_store",
    "comfymodal_runtime/golden_serial.py": "comfymodal_runtime.golden_serial",
    "comfymodal_runtime/golden_io_process_v2.py": "comfymodal_runtime.golden_io_process_v2",
    "comfymodal_runtime/golden_model_transport.py": "comfymodal_runtime.golden_model_transport",
    "comfymodal_runtime/golden_qd_transport.py": "comfymodal_runtime.golden_qd_transport",
    "comfymodal_runtime/golden_source_threads.py": "comfymodal_runtime.golden_source_threads",
    "comfymodal_runtime/source_copy_isolation.py": "comfymodal_runtime.source_copy_isolation",
    "comfymodal_runtime/source_population_policy.py": "comfymodal_runtime.source_population_policy",
    "comfymodal_runtime/source_copy_probe.py": "comfymodal_runtime.source_copy_probe",
    "comfymodal_runtime/source_stall_classification.py": "comfymodal_runtime.source_stall_classification",
    "comfymodal_runtime/golden_parallel.py": "comfymodal_runtime.golden_parallel",
    "comfymodal_runtime/output_durability.py": "comfymodal_runtime.output_durability",
}

# Expected container-side path prefixes for add_local_python_source mounts.
# Modal mounts local Python packages under /pkg/modal/... inside the image;
# anything else (site-packages, /usr/lib, ...) is an import-shadowing red flag.
_EXPECTED_PATH_PREFIXES = (
    "/pkg/modal/",
    "/root/",
    "/opt/",
)


def sha256_file(path: Path) -> str:
    """SHA-256 of the exact bytes at ``path``.  Raises on read failure."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_expected_local(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Compute EXPECTED_LOCAL source identities from the exact source tree.

    Includes git HEAD, git dirty state, and per-file SHA-256 + size + mtime +
    host realpath so a deploy that includes uncommitted bytes is compared
    against the bytes that would actually be uploaded.
    """
    expected: dict[str, dict[str, Any]] = {}
    for rel in REQUIRED_MODULES:
        p = repo_root / rel
        if not p.exists():
            expected[rel] = {"sha256": None, "error": "local file missing"}
            continue
        st = p.stat()
        expected[rel] = {
            "sha256": sha256_file(p),
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "realpath": str(p.resolve()),
        }
    # git state (best effort; never fail the probe on git absence)
    git_head = ""
    git_dirty = ""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(repo_root), timeout=30,
        )
        if r.returncode == 0:
            git_head = r.stdout.strip()
        r2 = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(repo_root), timeout=30,
        )
        git_dirty = r2.stdout.strip() if r2.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        pass
    return {
        "git_head": git_head,
        "git_dirty": git_dirty,
        "modules": expected,
    }


def _classify_module(
    rel: str, expected: dict[str, Any], remote: dict[str, Any]
) -> dict[str, Any]:
    """Classify one module: MATCH / MISMATCH / MISSING / UNEXPECTED_PATH."""
    remote_sha = str(remote.get("sha256") or "")
    remote_path = str(remote.get("realpath") or remote.get("file") or "")
    expected_sha = str(expected.get("sha256") or "")
    if not remote_path:
        return {
            "module": rel, "verdict": "MISSING",
            "detail": "remote module absent or no __file__",
            "remote_sha": remote_sha, "expected_sha": expected_sha,
        }
    if remote_sha != expected_sha:
        return {
            "module": rel, "verdict": "MISMATCH",
            "detail": "remote bytes differ from expected local source",
            "remote_path": remote_path, "remote_sha": remote_sha,
            "expected_sha": expected_sha,
        }
    # SHA matches; still flag unexpected import provenance (site-packages
    # shadowing a deploy mount, etc.).
    if not remote_path.startswith(_EXPECTED_PATH_PREFIXES):
        return {
            "module": rel, "verdict": "UNEXPECTED_PATH",
            "detail": f"remote path {remote_path!r} is not a known deploy mount prefix",
            "remote_path": remote_path, "remote_sha": remote_sha,
            "expected_sha": expected_sha,
        }
    return {
        "module": rel, "verdict": "MATCH",
        "remote_path": remote_path, "remote_sha": remote_sha,
        "expected_sha": expected_sha,
    }


def classify_source_probe(
    expected: dict[str, Any], probe: dict[str, Any]
) -> dict[str, Any]:
    """Compare EXPECTED_LOCAL against the remote probe response.

    Returns a dict with per-module verdicts, an aggregate ``verdict``
    (MATCH or the worst failure), and ledger enablement state.
    """
    modules = expected.get("modules", {})
    remote_modules = probe.get("modules", {}) if isinstance(probe, dict) else {}
    classifications = []
    for rel in REQUIRED_MODULES:
        exp = modules.get(rel) or {"sha256": None}
        remote = remote_modules.get(REMOTE_MODULE_NAMES.get(rel, rel)) or {}
        classifications.append(_classify_module(rel, exp, remote))

    verdicts = {c["verdict"] for c in classifications}
    if "MISSING" in verdicts:
        aggregate = "MISSING"
    elif "MISMATCH" in verdicts:
        aggregate = "MISMATCH"
    elif "UNEXPECTED_PATH" in verdicts:
        aggregate = "UNEXPECTED_PATH"
    elif verdicts == {"MATCH"}:
        aggregate = "MATCH"
    else:
        aggregate = "MISSING"

    ledger = probe.get("ledger", {}) if isinstance(probe, dict) else {}
    return {
        "verdict": aggregate,
        "modules": classifications,
        "ledger_flag": str(ledger.get("flag") or ""),
        "ledger_enabled": bool(ledger.get("enabled")),
        "ledger_record_event": bool(ledger.get("record_event")),
        "diagnostics": classify_diagnostics(
            probe.get("diagnostics", {}) if isinstance(probe, dict) else {}
        ),
    }


def classify_diagnostics(diagnostics: dict[str, Any]) -> dict[str, Any]:
    """Classify passive Golden parity diagnostics without changing source verdict.

    ``UNKNOWN`` is intentional for older probes or a runtime that could not
    expose a registry.  This is evidence classification, not a claim that
    source presence implies runtime registration.
    """
    if not isinstance(diagnostics, dict) or not diagnostics:
        return {"verdict": "UNKNOWN", "reason": "diagnostics_missing"}

    manifest = diagnostics.get("baked_dependency_manifest")
    sage = diagnostics.get("sage")
    join = diagnostics.get("join_strings")
    reasons: list[str] = []
    states: list[str] = []

    if not isinstance(manifest, dict):
        states.append("UNKNOWN")
        reasons.append("manifest_diagnostic_missing")
    elif manifest.get("status") == "ok":
        states.append("PASS")
    else:
        states.append("FAIL" if manifest.get("status") in {"missing", "unreadable", "invalid", "incomplete"} else "UNKNOWN")
        reasons.append(str(manifest.get("reason") or "manifest_not_verified"))

    if not isinstance(sage, dict):
        states.append("UNKNOWN")
        reasons.append("sage_diagnostic_missing")
    elif sage.get("status") == "available_not_smoke_tested":
        states.append("PASS")
    elif sage.get("status") == "unavailable":
        states.append("FAIL")
        reasons.append(str(sage.get("reason") or "sage_unavailable"))
    else:
        states.append("UNKNOWN")
        reasons.append(str(sage.get("reason") or "sage_status_unknown"))

    if not isinstance(join, dict):
        states.append("UNKNOWN")
        reasons.append("join_strings_diagnostic_missing")
    elif join.get("registered") is True and join.get("classification") in {
        "compatibility_fallback", "real_kjnodes",
    }:
        states.append("PASS")
    elif join.get("registered") is False:
        states.append("FAIL")
        reasons.append(str(join.get("reason") or "join_strings_not_registered"))
    else:
        states.append("UNKNOWN")
        reasons.append(str(join.get("reason") or "join_strings_owner_unknown"))

    if "FAIL" in states:
        verdict = "FAIL"
    elif states and all(state == "PASS" for state in states):
        verdict = "PASS"
    else:
        verdict = "UNKNOWN"
    return {"verdict": verdict, "states": states, "reasons": reasons}


def summarize_probe(probe: dict[str, Any]) -> dict[str, Any]:
    """Extract a sanitized, JSON-safe summary (never dumps secrets).

    Secret-shaped env keys (TOKEN, SECRET, KEY, PASSWORD, CREDENTIAL) are
    redacted even inside ``safe_env`` so a probe response can never leak
    credentials into a report or log.
    """
    import re as _re

    _SECRET_KEY = _re.compile(r"(token|secret|key|password|credential)", _re.IGNORECASE)

    def _redact_env(env: Any) -> dict[str, str]:
        out: dict[str, str] = {}
        if not isinstance(env, dict):
            return out
        for k, v in env.items():
            k = str(k)
            if _SECRET_KEY.search(k):
                out[k] = "***REDACTED***"
            else:
                out[k] = str(v)
        return out

    identity = probe.get("identity", {}) if isinstance(probe, dict) else {}
    py = probe.get("python", {}) if isinstance(probe, dict) else {}
    pkg = probe.get("package", {}) if isinstance(probe, dict) else {}
    diagnostics = probe.get("diagnostics", {}) if isinstance(probe, dict) else {}
    return {
        "app_name": str(identity.get("app_name") or ""),
        "class_name": str(identity.get("class_name") or ""),
        "probe_name": str(identity.get("probe_name") or ""),
        "image_id": str(identity.get("image_id") or ""),
        "container_session_id": str(identity.get("container_session_id") or ""),
        "pid": identity.get("pid"),
        "deployment_combined_hash": str(identity.get("deployment_combined_hash") or ""),
        "python_executable": str(py.get("executable") or ""),
        "python_version": str(py.get("version") or "").splitlines()[0] if py.get("version") else "",
        "cwd": str(py.get("cwd") or ""),
        "sys_path": [str(p) for p in (py.get("sys_path") or [])],
        "comfymodal_runtime_file": str(pkg.get("comfymodal_runtime_file") or ""),
        "comfymodal_runtime_path": [str(p) for p in (pkg.get("comfymodal_runtime_path") or [])],
        "safe_env": _redact_env(probe.get("safe_env") or {}) if isinstance(probe, dict) else {},
        "diagnostics": diagnostics if isinstance(diagnostics, dict) else {},
    }


def call_remote_source_probe(
    repo_root: Path, *, workspace: dict[str, Any], gpu: str
) -> dict[str, Any]:
    """Invoke the deployed class's ``source_identity_probe`` (no generation).

    Returns the probe dict.  Raises RuntimeError on transport/lookup failure.
    """
    import asyncio
    if "id" not in workspace and workspace.get("workspace_id"):
        workspace = {
            **workspace,
            "id": workspace["workspace_id"],
            "label": workspace.get("workspace_label", ""),
        }

    # The CLI may run without the repo root on sys.path; add it so the
    # transport package imports (mirrors tools/benchmark_v2_direct.py).
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    from comfymodal_runtime.modal_transport import ModalTransport

    transport = ModalTransport()

    def _do() -> dict[str, Any]:
        handle = transport._v2_handle(workspace=workspace, gpu=gpu)
        fn = getattr(handle, "source_identity_probe", None)
        if fn is None:
            raise RuntimeError(
                "deployed class has no source_identity_probe method — the "
                "deployed source predates the probe (CASE A)"
            )
        remote = getattr(fn, "remote", None)
        if remote is not None and callable(getattr(remote, "aio", None)):
            return remote.aio(request_id="v2-source-identity-probe")
        if asyncio.iscoroutinefunction(fn):
            return fn(request_id="v2-source-identity-probe")
        return fn(request_id="v2-source-identity-probe")

    @contextmanager
    def _destination_environment():
        original = dict(os.environ)
        try:
            for name in list(os.environ):
                if name.startswith("MODAL_") or name in {"COMFYMODAL_ENVIRONMENT", "COMFYMODAL_V2_ENVIRONMENT", "COMFYMODAL_MODAL_PROFILE"}:
                    os.environ.pop(name, None)
            os.environ["MODAL_TOKEN_ID"] = str(workspace.get("token_id") or "")
            os.environ["MODAL_TOKEN_SECRET"] = str(workspace.get("token_secret") or "")
            environment = str(workspace.get("environment") or "(default)")
            if environment != "(default)":
                os.environ["MODAL_ENVIRONMENT"] = environment
                os.environ["COMFYMODAL_ENVIRONMENT"] = environment
                os.environ["COMFYMODAL_V2_ENVIRONMENT"] = environment
            yield
        finally:
            os.environ.clear()
            os.environ.update(original)

    with _destination_environment():
        result = asyncio.run(asyncio.to_thread(_do))
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    if not isinstance(result, dict):
        raise RuntimeError(f"source_identity_probe returned {type(result).__name__}")
    return result


def run_source_probe(
    repo_root: Path,
    *,
    workspace: dict[str, Any] | None = None,
    gpu: str = "",
    expected: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Execute the full source-identity stop-gate.

    Returns ``(exit_code, report)`` where exit_code is 0 only when every
    required module MATCHes.
    """
    expected = expected if expected is not None else compute_expected_local(repo_root)
    if workspace is None:
        workspace = _load_workspace(repo_root)
    probe = call_remote_source_probe(repo_root, workspace=workspace, gpu=gpu or "rtx-pro-6000")
    result = classify_source_probe(expected, probe)
    report = {
        "expected": expected,
        "remote_summary": summarize_probe(probe),
        "classification": result,
    }
    return (0 if result["verdict"] == "MATCH" else 1), report


def _load_workspace(repo_root: Path) -> dict[str, Any]:
    """Compatibility loader for the immutable config-owned destination."""
    try:
        import modal_workspaces
        destination = modal_workspaces.resolve_modal_destination(repo_root)
        return {
            "id": destination["workspace_id"],
            "label": destination["workspace_label"],
            "environment": destination["environment"],
            "token_id": destination["token_id"],
            "token_secret": destination["token_secret"],
        }
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"Modal destination cannot be resolved: {exc}") from exc
