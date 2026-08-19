"""E30 container-side env probe: call run_env_probe on the deployed app.

Proves whether the E30 CLIP_QD gates reached the container env (the
deploy script alone is not proof — run_env_probe exists for this exact
purpose).  Read-only; no graph, no spend.
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.benchmark_v2_direct import _load_workspace  # noqa: E402
from comfymodal_runtime.modal_transport import ModalTransport  # noqa: E402


def main() -> int:
    os.environ["COMFYMODAL_V2_APP_NAME"] = (
        os.environ.get("COMFYMODAL_V2_APP_NAME", "")
        or "stable-modal-comfy-v2-restore-only-shadow"
    )
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = (
        os.environ.get("COMFYMODAL_V2_CLASS_NAME", "") or "ModalRuntimeEntrypointV2"
    )
    workspace = _load_workspace()
    transport = ModalTransport()
    handle = asyncio.run(
        asyncio.to_thread(transport._v2_handle, workspace=workspace, gpu="rtx-pro-6000")
    )
    fn = getattr(handle, "run_env_probe", None)
    if fn is None:
        print("run_env_probe unavailable on deployed handle")
        return 1
    remote = getattr(fn, "remote", None)
    if remote is not None and callable(getattr(remote, "aio", None)):
        probe = asyncio.run(remote.aio(request_id="e30-env-probe"))
    else:
        probe = asyncio.run(asyncio.to_thread(fn, request_id="e30-env-probe"))
    if asyncio.iscoroutine(probe):
        probe = asyncio.run(probe)
    env = probe.get("env", {}) if isinstance(probe, dict) else {}
    keys = (
        "COMFYMODAL_V2_CLIP_QD_READER",
        "COMFYMODAL_V2_CLIP_QD_QD",
        "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB",
        "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY",
        "COMFYMODAL_V2_CLIP_QD_ARTIFACT",
        "COMFYMODAL_V2_CLIP_FAST_HYDRATION",
        "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION",
        "COMFYMODAL_V2_ATOMIC_PROFILE",
        "COMFYMODAL_V2_APP_NAME",
    )
    print("=== E30 env probe ===", flush=True)
    for key in keys:
        print(f"{key}={env.get(key, '<missing>')}", flush=True)
    print(f"probe_status={probe.get('status')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
