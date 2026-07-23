#!/usr/bin/env python
"""Extract a warmup profile from ``latest_benchmark_workflow.json``.

Loads the benchmark workflow, derives a warmup profile using the existing
``workflow_metadata.extract_warmup_stack`` and ``stack_to_warmup_profile``
helpers, validates that the profile is a ``mode=split`` profile with all
required fields populated, and prints ``COMFYMODAL_WARMUP_*`` environment
variables as ``KEY=VALUE`` lines suitable for shell consumption.

Exit codes:
    0 — profile derived and emitted successfully.
    1 — workflow file missing, prompt empty, or profile validation failed.

Usage:
    python tools/extract_warmup_profile.py > warmup_env.txt
    for /f "delims=" %%a in (warmup_env.txt) do set "%%a"
"""

from __future__ import annotations

import json
import os
import sys

# Allow import from parent directory.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_THIS_DIR)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from workflow_metadata import extract_warmup_stack, stack_to_warmup_profile

WORKFLOW_PATH = os.path.join(_PARENT, "latest_benchmark_workflow.json")

# Required fields for a valid split warmup profile.
_REQUIRED_SPLIT_FIELDS = ("unet", "clip1", "clip2", "vae", "clip_type")


def _fail(msg: str, *, detail: object = None) -> None:
    """Print an error message to stderr and exit with code 1."""
    print(f"ERROR: {msg}", file=sys.stderr)
    if detail is not None:
        print(f"  detail={detail}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if not os.path.isfile(WORKFLOW_PATH):
        _fail(f"benchmark workflow not found at {WORKFLOW_PATH}")

    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    prompt = data.get("payload", {}).get("prompt", {})
    if not isinstance(prompt, dict) or not prompt:
        _fail("payload.prompt is empty or missing")

    stack = extract_warmup_stack(prompt)
    profile = stack_to_warmup_profile(stack)

    if not profile:
        _fail(
            "benchmark workflow produced an empty warmup profile",
            detail={"stack": stack},
        )
    if profile.get("mode") != "split":
        _fail(
            f"benchmark workflow profile mode is '{profile.get('mode')}', "
            "expected 'split'",
            detail={"stack": stack, "profile": profile},
        )

    for key in _REQUIRED_SPLIT_FIELDS:
        val = profile.get(key)
        if not isinstance(val, str) or not val.strip():
            _fail(
                f"warmup profile missing required field '{key}'",
                detail={"profile": profile},
            )

    # ── Emit COMFYMODAL_WARMUP_* KEY=VALUE lines ──────────────────────
    print(f"COMFYMODAL_WARMUP_PROFILE=split")
    print(f"COMFYMODAL_WARMUP_UNET={profile['unet']}")
    print(f"COMFYMODAL_WARMUP_CLIP1={profile['clip1']}")
    print(f"COMFYMODAL_WARMUP_CLIP2={profile['clip2']}")
    print(f"COMFYMODAL_WARMUP_VAE={profile['vae']}")
    print(f"COMFYMODAL_WARMUP_CLIP_TYPE={profile['clip_type']}")
    print(f"COMFYMODAL_WARMUP_TEXT=warmup")


if __name__ == "__main__":
    main()
