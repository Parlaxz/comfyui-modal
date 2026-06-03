"""Quick local test: Start ComfyUI, submit a prompt, check diagnostics.

Usage: python_embeded\python.exe -s custom_nodes\comfyui-modal\_quick_test.py
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib import request, error

COMFYUI_ROOT = Path(__file__).resolve().parents[2]
EMBEDDED_PYTHON = COMFYUI_ROOT / "python_embeded" / "python.exe"
NODE_DIR = Path(__file__).resolve().parent

BASE_URL = "http://127.0.0.1:8188"


def _json_request(url: str, method: str = "GET", payload: dict | None = None, timeout: int = 30) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


# 1. Start ComfyUI
log_file = NODE_DIR / "_quick_test_comfyui.log"
proc = subprocess.Popen(
    [str(EMBEDDED_PYTHON), "-s", "ComfyUI\\main.py", "--windows-standalone-build"],
    cwd=str(COMFYUI_ROOT),
    stdout=open(log_file, "wb"),
    stderr=subprocess.STDOUT,
)
print(f"ComfyUI started (PID={proc.pid}), log at {log_file}")

# 2. Wait for health
deadline = time.time() + 120
while time.time() < deadline:
    try:
        _json_request(f"{BASE_URL}/system_stats", timeout=5)
        print("ComfyUI is healthy!")
        break
    except Exception as e:
        print(f"  waiting... ({e})")
        time.sleep(2)
else:
    print("ComfyUI failed to start within 120s")
    proc.kill()
    sys.exit(1)

# 3. Check if there's a benchmark workflow snapshot
try:
    snap = _json_request(f"{BASE_URL}/comfymodal/benchmark/workflow", timeout=5)
    print(f"Benchmark snapshot: {snap.get('status', 'none')}")
except Exception as e:
    print(f"No benchmark snapshot available: {e}")
    # Try to load a saved workflow
    saved_wf = COMFYUI_ROOT / "saved workflows" / "flux_2-klein-9b(2).json"
    if saved_wf.exists():
        print(f"Found saved workflow: {saved_wf}")
        with open(saved_wf) as f:
            workflow_data = json.load(f)
        snap = {"payload": workflow_data}

# 4. Submit a prompt
if not snap or "payload" not in snap:
    print("No workflow available to submit")
    proc.kill()
    sys.exit(1)

payload = dict(snap["payload"])
payload["client_id"] = f"quick-test-{time.time()}"
print(f"Submitting prompt...")
resp = _json_request(f"{BASE_URL}/comfymodal/prompt", method="POST", payload=payload, timeout=30)
prompt_id = resp.get("prompt_id", "")
print(f"Prompt submitted: {prompt_id}")

# 5. Poll history
deadline = time.time() + 1800  # 30 min max
entry = None
while time.time() < deadline:
    try:
        data = _json_request(f"{BASE_URL}/history/{prompt_id}", timeout=30)
        if isinstance(data, dict) and prompt_id in data:
            entry = data[prompt_id]
            break
    except Exception:
        pass
    print("  waiting for prompt to complete...")
    time.sleep(5)

if entry is None:
    print("Prompt did not complete within timeout")
else:
    meta = entry.get("meta", {})
    print(f"\n=== RESULTS ===")
    print(f"Meta keys: {list(meta.keys())}")
    print(f"Has 'restore_timing': {'restore_timing' in meta}")
    print(f"restore_timing value: {meta.get('restore_timing', 'NOT FOUND')}")
    trace = meta.get("trace", {})
    print(f"Trace keys: {list(trace.keys())}")
    print(f"Has 'restore' in trace: {'restore' in trace if isinstance(trace, dict) else 'N/A'}")

    # Check diagnostic files
    diag1 = NODE_DIR / "_finish_job_meta_keys.log"
    diag2 = NODE_DIR / "_finish_job_debug.log"
    if diag1.exists():
        print(f"\n=== {diag1.name} ===")
        with open(diag1) as f:
            print(f.read())
    if diag2.exists():
        print(f"\n=== {diag2.name} ===")
        with open(diag2) as f:
            print(f.read())

# 6. Cleanup
print("\nShutting down ComfyUI...")
proc.kill()
proc.wait()
print("Done.")
