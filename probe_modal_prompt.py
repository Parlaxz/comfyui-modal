"""Real Modal prompt-stream probe — minimal t2i.

Streams a known-good workflow (latest_benchmark_workflow.json) against
the deployed GPU container, counts events, and reports the first
``result`` / ``error`` event.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

WORKSPACES = json.loads((ROOT / ".modal_workspaces.json").read_text(encoding="utf-8"))
ACTIVE_ID = WORKSPACES["active_workspace_id"]
WORKSPACE = next(w for w in WORKSPACES["workspaces"] if w["id"] == ACTIVE_ID)
os.environ["MODAL_TOKEN_ID"] = WORKSPACE["token_id"]
os.environ["MODAL_TOKEN_SECRET"] = WORKSPACE["token_secret"]
print(f"[probe] workspace: {WORKSPACE['label']} ({ACTIVE_ID})")

import modal_client

WORKFLOW_PATH = ROOT / "clean_workflow.json"
if not WORKFLOW_PATH.exists():
    print(f"[probe] no workflow at {WORKFLOW_PATH}; aborting")
    sys.exit(2)
workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
print(f"[probe] workflow loaded: {len(json.dumps(workflow))} bytes")

state = {"count": 0, "last": None, "status": [], "progress": [], "result": None, "error": None}
start = time.time()


async def _stream():
    gen = modal_client.run_prompt_stream(
        workflow=workflow,
        input_images={},
        trace={},
        gpu="rtx-pro-6000",
        modal_options={},
        workspace=WORKSPACE,
    )
    async for msg in gen:
        state["count"] += 1
        state["last"] = msg
        mtype = msg.get("type", "?") if isinstance(msg, dict) else "?"
        if mtype == "status":
            state["status"].append(str(msg.get("message", ""))[:200])
        elif mtype == "progress":
            state["progress"].append(str(msg.get("event", ""))[:60])
        elif mtype == "result":
            state["result"] = msg
            return
        elif mtype == "error":
            state["error"] = msg
            return
        if state["count"] > 600:
            print("[probe] too many events; breaking")
            return


try:
    asyncio.run(_stream())
except Exception as e:
    elapsed = time.time() - start
    print(f"[probe] EXCEPTION after {elapsed:.2f}s ({state['count']} events): {type(e).__name__}: {e}")
    sys.exit(3)

elapsed = time.time() - start
print(f"[probe] elapsed: {elapsed:.2f}s, events: {state['count']}")
print(f"[probe] status msgs: {len(state['status'])}")
for s in state["status"][:10]:
    print(f"  status: {s[:160]}")
print(f"[probe] progress events (first 8): {state['progress'][:8]}")
if state["result"] is not None:
    r = state["result"]
    print(f"[probe] RESULT keys: {list(r.keys()) if isinstance(r, dict) else type(r)}")
    if isinstance(r, dict):
        data = r.get("data", r)
        if isinstance(data, dict):
            print(f"[probe] result.data keys: {list(data.keys())[:8]}")
        for k in ("status", "ok", "outputs", "images"):
            if k in r:
                print(f"  result.{k}: {str(r[k])[:200]}")
if state["error"] is not None:
    print(f"[probe] ERROR: {json.dumps(state['error'], default=str)[:500]}")
if state["last"] is not None and state["result"] is None and state["error"] is None:
    last_str = json.dumps(state["last"], default=str)
    print(f"[probe] last_msg: {last_str[:400]}")
