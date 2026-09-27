"""E27 Follow-Up A: run_snapshot_restore_only_probe against the fresh shadow app."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WORKSPACE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".modal_workspaces.json")


def _load_workspace():
    with open(WORKSPACE_FILE, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    active_id = data["active_workspace_id"]
    ws = next(w for w in data["workspaces"] if w["id"] == active_id)
    return ws


async def _main():
    ws = _load_workspace()
    os.environ["MODAL_TOKEN_ID"] = ws["token_id"]
    os.environ["MODAL_TOKEN_SECRET"] = ws["token_secret"]
    os.environ["COMFYMODAL_V2_APP_NAME"] = "e27-followup-a-shadow"
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = "ModalRuntimeEntrypointV2"
    os.environ["COMFYMODAL_V2_GPU"] = "rtx-pro-6000"
    from comfymodal_runtime.modal_transport import ModalTransport

    handle = await asyncio.to_thread(
        ModalTransport()._v2_handle, workspace=ws, gpu="rtx-pro-6000",
    )
    fn = handle.run_snapshot_restore_only_probe
    result = fn.remote.aio(request_id="e27-followup-a-snapshot-probe-1")
    if asyncio.iscoroutine(result):
        result = await result
    print(json.dumps(result, indent=1, default=str))


if __name__ == "__main__":
    asyncio.run(_main())
