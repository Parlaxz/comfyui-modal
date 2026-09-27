"""Unwrap a benchmark-wrapper workflow into a clean API prompt.

The exported ``latest_benchmark_workflow.json`` has the shape::

    {
        "captured_at": <float>,
        "payload": {
            "client_id": "<uuid>",
            "extra_data": {...},
            "modal_options": {...},
            "prompt": {"<node_id>": {"class_type": "...", "inputs": {...}}, ...},
            ...
        },
        "workflow_hash": "...",
    }

We peel both wrappers (outer ``payload``, then inner ``prompt``) to
get the real ComfyUI API-prompt dict.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
src = ROOT / "latest_benchmark_workflow.json"
dst = ROOT / "clean_workflow.json"

data = json.loads(src.read_text(encoding="utf-8"))


def looks_like_api_prompt(d):
    if not isinstance(d, dict) or not d:
        return False
    sample = next(iter(d.values()))
    return isinstance(sample, dict) and "class_type" in sample


# Peel outer wrapper: drop keys that are not part of the API prompt.
if isinstance(data, dict) and "payload" in data and isinstance(data["payload"], dict):
    data = data["payload"]
    print(f"[clean] peeled outer wrapper; remaining keys: {list(data.keys())[:8]}")

# Peel session wrapper: drop metadata keys, keep the "prompt" dict.
if isinstance(data, dict) and "prompt" in data and isinstance(data["prompt"], dict):
    if looks_like_api_prompt(data["prompt"]):
        data = data["prompt"]
        print(f"[clean] peeled session wrapper; prompt has {len(data)} nodes")

# Validate final shape
if not looks_like_api_prompt(data):
    raise SystemExit(
        f"[clean] final shape is not an API prompt: keys={list(data.keys())[:6]}"
    )

dst.write_text(json.dumps(data, indent=2), encoding="utf-8")
print(f"[clean] wrote {dst} ({dst.stat().st_size} bytes)")
