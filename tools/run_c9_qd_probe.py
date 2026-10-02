#!/usr/bin/env python
"""C9 queue-depth shootout runner (dev machine; invokes the deployed shadow).

Calls ``ModalRuntimeEntrypointV2.run_unet_qd_probe`` on the C9 shadow
deployment (``stable-modal-comfy-v2-c9qd-shadow`` by default) with the exact
ZImage model name, and persists the JSON-safe result locally.

Usage:
    python tools/run_c9_qd_probe.py [--mode structural|evidence]
                                    [--app stable-modal-comfy-v2-c9qd-shadow]
                                    [--model z_image_turbo_bf16.safetensors]
                                    [--out PATH]

Workspace/credential handling mirrors ``tools/record_deployment_identity.py``
(``.modal_workspaces.json`` active workspace -> env credentials).  Handle
acquisition mirrors ``ModalTransport._v2_handle``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_ACTIVE_WORKSPACES_FILE = os.path.join(_REPO_ROOT, ".modal_workspaces.json")
_DEFAULT_APP_NAME = "stable-modal-comfy-v2-c9qd-shadow"
_DEFAULT_MODEL = "z_image_turbo_bf16.safetensors"
_CLASS_NAME = "ModalRuntimeEntrypointV2"
_GPU = "rtx-pro-6000"


def _load_active_workspace() -> dict:
    if not os.path.isfile(_ACTIVE_WORKSPACES_FILE):
        raise RuntimeError(f"workspace file not found: {_ACTIVE_WORKSPACES_FILE}")
    with open(_ACTIVE_WORKSPACES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    active_id = data.get("active_workspace_id")
    if not active_id:
        raise RuntimeError(".modal_workspaces.json has no active_workspace_id")
    workspace = next(
        (w for w in data.get("workspaces", []) if w.get("id") == active_id), None
    )
    if not workspace:
        raise RuntimeError(f"active workspace {active_id!r} not found")
    if not workspace.get("token_id") or not workspace.get("token_secret"):
        raise RuntimeError(f"active workspace {active_id!r} is missing tokens")
    return workspace


async def _call_probe(workspace: dict, app_name: str, model: str, mode: str) -> dict:
    os.environ["COMFYMODAL_V2_APP_NAME"] = app_name
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = _CLASS_NAME
    os.environ["COMFYMODAL_V2_GPU"] = _GPU

    from comfymodal_runtime.modal_transport import ModalTransport

    handle = await asyncio.to_thread(
        ModalTransport()._v2_handle, workspace=workspace, gpu=_GPU,
    )
    fn = handle.run_unet_qd_probe
    remote = getattr(fn, "remote", None)
    if remote is not None and callable(getattr(remote, "aio", None)):
        result = remote.aio(model, mode)
        if asyncio.iscoroutine(result):
            result = await result
    elif asyncio.iscoroutinefunction(fn):
        result = await fn(model, mode)
    else:
        result = await asyncio.to_thread(fn, model, mode)
    if not isinstance(result, dict):
        raise RuntimeError(f"remote returned non-dict: {type(result).__name__}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default="evidence",
                        choices=["structural", "evidence", "external"])
    parser.add_argument("--app", default=_DEFAULT_APP_NAME)
    parser.add_argument("--model", default=_DEFAULT_MODEL)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    try:
        workspace = _load_active_workspace()
        os.environ["MODAL_TOKEN_ID"] = workspace["token_id"]
        os.environ["MODAL_TOKEN_SECRET"] = workspace["token_secret"]
        print(
            f"[v2.c9qd] app={args.app} model={args.model} mode={args.mode}",
            flush=True,
        )
        result = asyncio.run(
            _call_probe(workspace, args.app, args.model, args.mode)
        )
        summary = (result.get("sections") or {}).get("summary") or {}
        status = str(result.get("status") or "")
        print(
            f"[v2.c9qd] status={status} mode={result.get('mode')} "
            f"wall_ms={result.get('_wall_ms')}",
            flush=True,
        )
        if summary:
            print(
                "[v2.c9qd] summary=" + json.dumps(
                    summary, separators=(",", ":"), sort_keys=True,
                    default=str,
                ),
                flush=True,
            )
        out_path = args.out or os.path.join(
            os.environ.get("TEMP", "."), "opencode", f"c9qd_{args.mode}.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1, default=str)
        print(f"[v2.c9qd] result_json={out_path}", flush=True)
        return 0 if status == "ok" else 2
    except Exception as exc:  # noqa: BLE001
        print(f"[v2.c9qd] status=failed error={type(exc).__name__}:{exc}",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
