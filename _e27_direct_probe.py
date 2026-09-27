"""E27 Follow-Up A: direct SDK probe (no ModalTransport) against a shadow app."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
APP = sys.argv[1] if len(sys.argv) > 1 else "e27-followup-b-shadow"
KIND = sys.argv[2] if len(sys.argv) > 2 else "env"

ws_data = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".modal_workspaces.json"), encoding="utf-8"))
ws = next((w for w in ws_data["workspaces"] if w["id"] == ws_data["active_workspace_id"]), None)
os.environ["MODAL_TOKEN_ID"] = ws["token_id"]
os.environ["MODAL_TOKEN_SECRET"] = ws["token_secret"]

import modal

client = modal.Client.from_credentials(ws["token_id"], ws["token_secret"])
cls_handle = modal.Cls.from_name(APP, "ModalRuntimeEntrypointV2", client=client, environment_name=None)
inst = cls_handle()


async def main():
    if KIND == "env":
        r = await inst.run_env_probe.remote.aio()
    else:
        r = await inst.run_snapshot_restore_only_probe.remote.aio(request_id=f"{APP}-direct-probe")
    print("RESULT_OK")
    print(json.dumps(r, indent=1, default=str))


asyncio.run(main())
print("DONE")
