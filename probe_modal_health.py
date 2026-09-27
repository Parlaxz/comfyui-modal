"""Real Modal verification probe — minimum end-to-end call.

Invokes the deployed ``health_cpu`` function via modal_client against
the active workspace and reports success/failure. Used as evidence
that the freshly-deployed app is reachable from this Windows host.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Read the active workspace from .modal_workspaces.json
WORKSPACES_FILE = ROOT / ".modal_workspaces.json"
WORKSPACES = json.loads(WORKSPACES_FILE.read_text(encoding="utf-8"))
ACTIVE_ID = WORKSPACES["active_workspace_id"]
WORKSPACE = next(w for w in WORKSPACES["workspaces"] if w["id"] == ACTIVE_ID)

print(f"[probe] active workspace: {WORKSPACE['label']} ({ACTIVE_ID})")
print(f"[probe] token_id: {WORKSPACE['token_id'][:12]}...")

# Set env for any subprocess modal calls
os.environ["MODAL_TOKEN_ID"] = WORKSPACE["token_id"]
os.environ["MODAL_TOKEN_SECRET"] = WORKSPACE["token_secret"]

import modal_client

start = time.time()
try:
    result = asyncio.run(modal_client.health_check(workspace=WORKSPACE))
    elapsed = time.time() - start
    print(f"[probe] health_check returned in {elapsed:.2f}s")
    print(f"[probe] result: {json.dumps(result, default=str)[:500]}")
    sys.exit(0 if isinstance(result, dict) and result.get("status") == "ok" else 1)
except Exception as e:
    elapsed = time.time() - start
    print(f"[probe] health_check FAILED after {elapsed:.2f}s: {type(e).__name__}: {e}")
    sys.exit(2)
