from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from comfymodal_runtime.modal_transport import ModalTransport
from tools.v2_control.source_probe import _load_workspace


async def _call(args: argparse.Namespace) -> dict:
    workspace = _load_workspace(Path.cwd())
    for name in list(os.environ):
        if name.startswith("MODAL_") or name in {
            "COMFYMODAL_ENVIRONMENT", "COMFYMODAL_V2_ENVIRONMENT",
        }:
            os.environ.pop(name, None)
    os.environ["MODAL_TOKEN_ID"] = str(workspace.get("token_id") or "")
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace.get("token_secret") or "")
    environment = str(workspace.get("environment") or "")
    if args.environment:
        environment = args.environment
    if environment:
        os.environ["MODAL_ENVIRONMENT"] = environment
        os.environ["COMFYMODAL_ENVIRONMENT"] = environment
        os.environ["COMFYMODAL_V2_ENVIRONMENT"] = environment
    os.environ["COMFYMODAL_V2_APP_NAME"] = args.app
    os.environ["COMFYMODAL_V2_CLASS_NAME"] = "ModalRuntimeEntrypointV2"
    os.environ["COMFYMODAL_V2_GPU"] = "H100!"
    handle = await asyncio.to_thread(ModalTransport()._v2_handle, workspace=workspace, gpu="H100!")
    result = handle.run_testing8_gds_instanttensor_probe.remote.aio(
        operation=args.operation,
        model_path=args.model,
        backend=args.backend,
        copy_mode=args.copy,
        validate=args.validate,
    )
    if asyncio.iscoroutine(result):
        result = await result
    if not isinstance(result, dict):
        raise RuntimeError(f"remote returned {type(result).__name__}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", default="batch-testing8-gds-instanttensor-sep28")
    parser.add_argument("--environment", default="main")
    parser.add_argument("--operation", choices=("gds", "inspect", "instanttensor"), required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--backend", choices=("AIO", "URING"), default="")
    parser.add_argument("--copy", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    async def _bounded_call() -> dict:
        task = asyncio.create_task(_call(args))
        started = time.monotonic()
        while True:
            done, _ = await asyncio.wait({task}, timeout=15.0)
            if done:
                return task.result()
            elapsed = time.monotonic() - started
            print(f"[testing8.probe] waiting operation={args.operation} model={args.model or '-'} elapsed_s={elapsed:.0f}", flush=True)
            if elapsed >= args.timeout:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise TimeoutError(f"probe watchdog expired after {args.timeout:.0f}s")

    try:
        result = asyncio.run(_bounded_call())
    except TimeoutError as exc:
        print(f"[testing8.probe] status=timeout error={exc}", file=sys.stderr)
        return 124
    payload = json.dumps(result, indent=2, sort_keys=True, default=str)
    print(payload)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    return 0 if result.get("status") in {"yes", "ok"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
