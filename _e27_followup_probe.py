"""E27 Follow-Up A: run_e27_followup_probe battery against a shadow app."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
APP = sys.argv[1] if len(sys.argv) > 1 else "stable-modal-comfy-v2-restore-only-shadow"
KIND = sys.argv[2] if len(sys.argv) > 2 else "enumerate_dtypes"
MODEL = sys.argv[3] if len(sys.argv) > 3 else "qwen_3_4b.safetensors"

ws_data = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".modal_workspaces.json"), encoding="utf-8"))
ws = next((w for w in ws_data["workspaces"] if w["id"] == ws_data["active_workspace_id"]), None)
os.environ["MODAL_TOKEN_ID"] = ws["token_id"]
os.environ["MODAL_TOKEN_SECRET"] = ws["token_secret"]
os.environ["COMFYMODAL_V2_APP_NAME"] = APP
os.environ["COMFYMODAL_V2_CLASS_NAME"] = "ModalRuntimeEntrypointV2"
os.environ["COMFYMODAL_V2_GPU"] = "rtx-pro-6000"

from comfymodal_runtime.modal_transport import ModalTransport


async def _main():
    handle = await asyncio.to_thread(
        ModalTransport()._v2_handle, workspace=ws, gpu="rtx-pro-6000",
    )
    fn = handle.run_e27_followup_probe
    if KIND == "fastsafe_screen":
        result = fn.remote.aio(KIND, MODEL)
    else:
        result = fn.remote.aio(KIND, MODEL)
    if asyncio.iscoroutine(result):
        result = await result
    print(json.dumps(result, indent=1, default=str))


if __name__ == "__main__":
    asyncio.run(_main())
