#!/usr/bin/env python
"""Record the ACTUAL baked deployment identity (container readback).

Deploy-time identity record tool (dev machine, no GPU, no deploy): calls the
deployed V2 app's O(1) ``ModalRuntimeEntrypointV2.get_deployment_identity_static``
Modal method, which reads the ACTUAL image-baked deployment identity from the
running container (the module-level ``_V2_DEPLOYMENT_COMBINED_HASH`` constant
plus the baked custom-node generation and ComfyUI version).  The returned
values are persisted to ``.deployed_state.json`` at the repo root so Step-3
plan validation carries the exact deployed hash instead of a
host-reconstructed value.

Fails closed: exit code 0 and the state file are produced ONLY when the remote
call succeeded AND the returned ``deployment_combined_hash``,
``custom_nodes_generation`` and ``overall_dependency_hash`` are all non-empty;
otherwise prints ``[v2.deploy_identity] status=failed`` and exits 1.

Workspace/credential handling mirrors ``tools/publish_custom_nodes_volume.py``
(``.modal_workspaces.json`` active workspace -> env credentials).  The remote
handle acquisition mirrors ``tools/benchmark_v2_direct.py``
(``ModalTransport._v2_handle`` -> class instance -> method handle).

Usage:
    python tools/record_deployment_identity.py [--manifest-out PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

# Allow import of repo modules (comfymodal_runtime) from tools/.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_ACTIVE_WORKSPACES_FILE = os.path.join(_REPO_ROOT, ".modal_workspaces.json")
_DEPLOYED_STATE_FILE = os.path.join(_REPO_ROOT, ".deployed_state.json")

# Same default as deploy_and_run_v2_single.bat (line 10).
_DEFAULT_APP_NAME = "stable-modal-comfy-v2-restore-only-shadow"
_CLASS_NAME = "ModalRuntimeEntrypointV2"
_METHOD_NAME = "get_deployment_identity_static"

# Host ComfyUI root: explicit env override, else the parent of the repo's
# parent (this file lives at <repo>/tools; the ComfyUI root is
# Path(<repo root>).parents[1]).
_HOST_COMFYUI_ROOT = os.environ.get(
    "COMFYMODAL_V2_COMFYUI_ROOT",
    str(Path(_REPO_ROOT).parents[1]),
)


def _lf_sha256(data: bytes) -> str:
    """sha256 of ``data`` with LF line-ending normalization (CRLF/CR == LF)."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def _file_lf_sha256(path: str) -> str:
    """LF-normalized sha256 of the file at ``path``, or ``""`` if unreadable."""
    try:
        with open(path, "rb") as fh:
            return _lf_sha256(fh.read())
    except Exception:
        return ""


def _resolve_app_name() -> str:
    """Resolve the selected target app, retaining the restore-only fallback."""
    app_name = os.environ.get("COMFYMODAL_V2_APP_NAME", "").strip()
    if app_name:
        return app_name
    return os.environ.get(
        "COMFYMODAL_V2_RESTORE_ONLY_APP_NAME", _DEFAULT_APP_NAME
    ).strip() or _DEFAULT_APP_NAME


def _git_head(repo_root: str) -> str:
    """Best-effort ``git -C <repo_root> rev-parse HEAD`` (guarded, 10s timeout)."""
    if not repo_root:
        return ""
    try:
        import subprocess  # noqa: PLC0415
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return str(proc.stdout or "").strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _load_active_workspace() -> dict:
    """Load the active workspace credentials (same source as the deploy .bat)."""
    if not os.path.isfile(_ACTIVE_WORKSPACES_FILE):
        raise RuntimeError(f"workspace file not found: {_ACTIVE_WORKSPACES_FILE}")
    with open(_ACTIVE_WORKSPACES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    active_id = data.get("active_workspace_id")
    if not active_id:
        raise RuntimeError(".modal_workspaces.json has no active_workspace_id")
    workspace = next((w for w in data.get("workspaces", []) if w.get("id") == active_id), None)
    if not workspace:
        raise RuntimeError(f"active workspace {active_id!r} not found in .modal_workspaces.json")
    if not workspace.get("token_id") or not workspace.get("token_secret"):
        raise RuntimeError(f"active workspace {active_id!r} is missing token_id/token_secret")
    return workspace


async def _call_deployment_identity(workspace: dict, app_name: str, gpu: str) -> dict:
    """Acquire the V2 class handle and invoke ``get_deployment_identity_static``.

    Mirrors ``benchmark_v2_direct._run_snapshot_restore_only`` handle
    acquisition (``ModalTransport._v2_handle`` -> class instance) and its
    remote call dispatch (``remote.aio`` when available, else sync fallback).
    """
    os.environ["COMFYMODAL_V2_APP_NAME"] = app_name
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = _CLASS_NAME
    os.environ["COMFYMODAL_V2_GPU"] = gpu

    from comfymodal_runtime.modal_transport import ModalTransport

    handle = await asyncio.to_thread(
        ModalTransport()._v2_handle, workspace=workspace, gpu=gpu,
    )
    fn = handle.get_deployment_identity_static
    remote = getattr(fn, "remote", None)
    if remote is not None and callable(getattr(remote, "aio", None)):
        result = remote.aio()
        if asyncio.iscoroutine(result):
            result = await result
    elif asyncio.iscoroutinefunction(fn):
        result = await fn()
    else:
        result = await asyncio.to_thread(fn)
    if not isinstance(result, dict):
        raise RuntimeError(f"remote returned non-dict: {type(result).__name__}")
    return result


def _write_state(state: dict) -> None:
    with open(_DEPLOYED_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record the ACTUAL baked deployment identity (container readback)."
    )
    parser.add_argument(
        "--manifest-out",
        default="",
        help="Optional path to additionally write the full registry manifest JSON "
             "(never defaults to writing it).",
    )
    args = parser.parse_args()

    try:
        workspace = _load_active_workspace()

        # Mirror deploy_and_run_v2_single.bat: expose credentials via env for
        # any downstream Modal SDK handle resolution.
        os.environ["MODAL_TOKEN_ID"] = workspace["token_id"]
        os.environ["MODAL_TOKEN_SECRET"] = workspace["token_secret"]

        app_name = _resolve_app_name()
        gpu = os.environ.get("COMFYMODAL_V2_GPU", "rtx-pro-6000").strip() or "rtx-pro-6000"

        print(f"[v2.deploy_identity] app={app_name} class={_CLASS_NAME} method={_METHOD_NAME}")
        result = asyncio.run(_call_deployment_identity(workspace, app_name, gpu))

        requested_atomic_profile = str(
            os.environ.get("COMFYMODAL_V2_ATOMIC_PROFILE", "") or ""
        ).strip()
        deployed_atomic_profile = str(
            result.get("atomic_profile", "") or ""
        ).strip()
        if requested_atomic_profile and deployed_atomic_profile != requested_atomic_profile:
            print(
                "[v2.deploy_identity] status=failed "
                "reason=atomic_profile_mismatch "
                f"requested={requested_atomic_profile} "
                f"deployed={deployed_atomic_profile or '<missing>'}",
                file=sys.stderr,
            )
            return 1

        deployment_combined_hash = str(result.get("deployment_combined_hash") or "")
        custom_nodes_generation = str(result.get("custom_nodes_generation") or "")
        overall_dependency_hash = str(result.get("overall_dependency_hash") or "")
        comfyui_version = str(result.get("comfyui_version") or "")
        manifest = result.get("registry_manifest") or {}
        if not isinstance(manifest, dict):
            manifest = {}
        manifest_classes = manifest.get("classes") or {}
        if not isinstance(manifest_classes, dict):
            manifest_classes = {}
        manifest_class_count = int(
            result.get("registry_manifest_class_count")
            or len(manifest_classes)
            or 0
        )

        # HOST-side ComfyUI core identity for host<->deployed comparison.
        host_comfyui_commit = _git_head(_HOST_COMFYUI_ROOT)
        host_core_module_sha256s = {
            "nodes.py": _file_lf_sha256(os.path.join(_HOST_COMFYUI_ROOT, "nodes.py")),
            "execution.py": _file_lf_sha256(os.path.join(_HOST_COMFYUI_ROOT, "execution.py")),
        }
        deployed_comfyui_commit = str(result.get("comfyui_commit") or "").strip()
        _deployed_core_sha = result.get("core_module_sha256s") or {}
        if not isinstance(_deployed_core_sha, dict):
            _deployed_core_sha = {}
        _deployed_nodes_sha = str(_deployed_core_sha.get("nodes.py") or "")
        _host_nodes_sha = str(host_core_module_sha256s.get("nodes.py") or "")
        if deployed_comfyui_commit and host_comfyui_commit and deployed_comfyui_commit == host_comfyui_commit:
            comfyui_core_match = 1
        elif _deployed_nodes_sha and _host_nodes_sha and _deployed_nodes_sha == _host_nodes_sha:
            comfyui_core_match = 1
        else:
            comfyui_core_match = 0

        if not deployment_combined_hash:
            print("[v2.deploy_identity] status=failed reason=empty_deployment_combined_hash", file=sys.stderr)
            return 1
        if not custom_nodes_generation:
            print("[v2.deploy_identity] status=failed reason=empty_custom_nodes_generation", file=sys.stderr)
            return 1
        if not overall_dependency_hash:
            print("[v2.deploy_identity] status=failed reason=empty_overall_dependency_hash", file=sys.stderr)
            return 1

        # Deployed runtime-shape record (canonical deploy-batch env): computed
        # from the SAME pinned env the deploy launcher sets
        # (COMFYMODAL_V2_CPU_REQUEST=12, COMFYMODAL_V2_MEMORY_MB=32768,
        # THREAD_POLICY=TBASE, SNAPSHOT_MODEL_ORDER=O0), which is also what
        # the container bakes, so the run batch's preflight can compare the
        # planned request shape against the deployment's recorded shape with
        # zero remote calls.  Guarded: shape problems must never fail the
        # identity record itself; the run preflight fails closed when the
        # fields are missing.
        _shape: dict = {}
        try:
            from comfymodal_runtime.runtime_shape import runtime_shape_config
            _shape_cfg = runtime_shape_config()
            _shape = {
                "runtime_shape_fingerprint": _shape_cfg.runtime_shape_fingerprint,
                "runtime_shape_label": _shape_cfg.runtime_shape_label or "",
                "cpu_request": int(_shape_cfg.cpu_request),
                "memory_request": int(_shape_cfg.memory_request),
                "thread_policy": _shape_cfg.thread_policy,
                "snapshot_model_order": _shape_cfg.snapshot_model_order,
            }
        except Exception:  # noqa: BLE001 — guarded; preflight fails closed
            _shape = {}
        _class_name = os.environ.get(
            "COMFYMODAL_V2_CLASS_NAME", _CLASS_NAME
        ).strip() or _CLASS_NAME

        def _env_int(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, "").strip() or default)
            except (TypeError, ValueError):
                return default

        state = {
            "schema_version": 1,
            "source": "container_readback",
            "deployment_combined_hash": deployment_combined_hash,
            "custom_nodes_generation": custom_nodes_generation,
            "overall_dependency_hash": overall_dependency_hash,
            "comfyui_version": comfyui_version,
            "registry_manifest_class_count": manifest_class_count,
            "comfyui_commit": deployed_comfyui_commit,
            "host_comfyui_commit": host_comfyui_commit,
            "comfyui_core_match": comfyui_core_match,
            "deployed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "app_name": app_name,
            "class_name": _class_name,
            "atomic_profile": deployed_atomic_profile or requested_atomic_profile,
            "runtime_shape_recorded": 1 if _shape else 0,
            "runtime_shape_fingerprint": str(
                _shape.get("runtime_shape_fingerprint") or ""
            ),
            "runtime_shape_label": str(_shape.get("runtime_shape_label") or ""),
            "cpu_request": int(_shape.get("cpu_request") or 0),
            "memory_request": int(_shape.get("memory_request") or 0),
            "baseline_cpu_request": _env_int("COMFYMODAL_V2_BASELINE_CPU_REQUEST", 12),
            "baseline_memory_request": _env_int(
                "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST", 32768
            ),
            "thread_policy": str(_shape.get("thread_policy") or ""),
            "snapshot_model_order": str(_shape.get("snapshot_model_order") or ""),
        }
        _write_state(state)
        print(f"[v2.deploy_identity] state_file={_DEPLOYED_STATE_FILE}")

        if args.manifest_out:
            with open(args.manifest_out, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, sort_keys=True)
            print(f"[v2.deploy_identity] manifest_out={args.manifest_out}")

        print(
            f"[v2.deploy_identity] status=ok "
            f"deployment_combined_hash={deployment_combined_hash[:16]} "
            f"custom_nodes_generation={custom_nodes_generation[:16]} "
            f"overall_dependency_hash={overall_dependency_hash[:16]} "
            f"comfyui_version={comfyui_version} "
            f"manifest_classes={manifest_class_count} "
            f"class={_class_name} "
            f"runtime_shape_fingerprint={state.get('runtime_shape_fingerprint')} "
            f"cpu_request={state.get('cpu_request')} "
            f"memory_request={state.get('memory_request')}"
        )
        print(
            f"[v2.deploy_identity] atomic_profile="
            f"{state.get('atomic_profile') or '<none>'}"
        )
        print(
            f"[v2.deploy_identity] "
            f"host_comfyui_identity={host_comfyui_commit[:16] or _host_nodes_sha[:16] or '-'} "
            f"deployed_comfyui_identity={deployed_comfyui_commit[:16] or '-'} "
            f"comfyui_core_match={comfyui_core_match}"
        )
        return 0
    except Exception as exc:  # noqa: BLE001 — never raise silently
        print(f"[v2.deploy_identity] status=failed error={type(exc).__name__}:{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
