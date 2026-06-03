"""Test: submit prompt, poll history, check meta for restore_timing."""
import json
import time
import uuid
import sys
from urllib import request, error

BASE_URL = "http://127.0.0.1:8188"


def json_req(url, method="GET", payload=None, timeout=30):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main():
    # 1. Get snapshot
    snap = json_req(f"{BASE_URL}/comfymodal/benchmark/workflow", timeout=10)
    print(f"Got snapshot, hash={snap.get('workflow_hash', '')[:12]}")
    
    # 2. Submit
    payload = dict(snap["payload"])
    client_id = f"flow-test-{uuid.uuid4().hex[:8]}"
    payload["client_id"] = client_id
    payload["t0_client_press_ms"] = int(time.time() * 1000)
    
    result = json_req(f"{BASE_URL}/comfymodal/prompt", method="POST", 
                      payload=payload, timeout=30)
    prompt_id = result.get("prompt_id", "")
    if not prompt_id:
        print(f"ERROR: no prompt_id in response: {result}")
        sys.exit(1)
    print(f"Submitted, prompt_id={prompt_id}")
    
    # 3. Poll
    deadline = time.time() + 600  # 10 min max
    while time.time() < deadline:
        try:
            data = json_req(f"{BASE_URL}/history/{prompt_id}", timeout=30)
            if isinstance(data, dict) and prompt_id in data:
                entry = data[prompt_id]
                meta = entry.get("meta", {})
                print(f"\n=== META ===")
                print(f"Keys: {list(meta.keys())}")
                print(f"Has 'restore_timing': {'restore_timing' in meta}")
                rt = meta.get("restore_timing", "MISSING")
                print(f"restore_timing: {json.dumps(rt, indent=2)[:300]}")
                trace = meta.get("trace", {})
                if isinstance(trace, dict):
                    print(f"Trace keys: {list(trace.keys())}")
                    print(f"Has 'restore': {'restore' in trace}")
                    if "restore" in trace:
                        print(f"Restore data: {json.dumps(trace['restore'], indent=2)[:300]}")
                
                # Check diagnostic files
                import os
                node_dir = os.path.dirname(os.path.abspath(__file__))
                for diag_name in ["_finish_job_meta_keys.log", "_finish_job_debug.log"]:
                    diag_path = os.path.join(node_dir, diag_name)
                    if os.path.exists(diag_path):
                        print(f"\n=== {diag_name} ===")
                        with open(diag_path) as f:
                            print(f.read())
                return
            print(".", end="", flush=True)
            time.sleep(3)
        except KeyboardInterrupt:
            print("\nInterrupted")
            return
        except Exception as e:
            print(f"\nPoll error: {e}", flush=True)
            time.sleep(5)
    
    print(f"\nTimeout after 600s")


if __name__ == "__main__":
    main()
