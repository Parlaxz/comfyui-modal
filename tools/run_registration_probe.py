from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from comfymodal_runtime.modal_transport import ModalTransport
from tools.v2_control.source_probe import _load_workspace


async def _run(args: argparse.Namespace) -> None:
    workspace = _load_workspace(Path.cwd())
    if "id" not in workspace and workspace.get("workspace_id"):
        workspace = {
            **workspace,
            "id": workspace["workspace_id"],
            "label": workspace.get("workspace_label", ""),
        }
    for name in list(os.environ):
        if name.startswith("MODAL_") or name in {
            "COMFYMODAL_ENVIRONMENT",
            "COMFYMODAL_V2_ENVIRONMENT",
            "COMFYMODAL_MODAL_PROFILE",
        }:
            os.environ.pop(name, None)
    os.environ["MODAL_TOKEN_ID"] = str(workspace.get("token_id") or "")
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace.get("token_secret") or "")
    environment = str(workspace.get("environment") or "(default)")
    if environment != "(default)":
        os.environ["MODAL_ENVIRONMENT"] = environment
        os.environ["COMFYMODAL_ENVIRONMENT"] = environment
        os.environ["COMFYMODAL_V2_ENVIRONMENT"] = environment
    os.environ["COMFYMODAL_V2_APP_NAME"] = args.app
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = "ModalRuntimeEntrypointV2"
    os.environ["COMFYMODAL_V2_GPU"] = "H100!"
    handle = await asyncio.to_thread(
        ModalTransport()._v2_handle,
        workspace=workspace,
        gpu="H100!",
    )
    result = handle.run_registration_probe.remote.aio(
        mapping_kind=args.mapping,
        size_mib=args.size_mib,
        device_index=0,
    )
    if asyncio.iscoroutine(result):
        result = await result
    print(json.dumps(result, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True)
    parser.add_argument("--mapping", required=True, choices=("posix_shm", "anonymous_shared", "anonymous_private", "historical_m2"))
    parser.add_argument("--size-mib", type=int, default=320)
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
