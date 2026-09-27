#!/usr/bin/env python
"""Retry selected full-file cells with a bounded 25 s remote timeout.

Writes ``<cell>-retry.json`` so the original artifacts are preserved.

Raw measurements only.  No tuning.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_APP = "sept-clip-source-race-oracle"
_TIMEOUT_S = 25
_CELLS = (("h100", 256, 2), ("h100", 256, 4))


def _workspace() -> dict[str, Any]:
    import tomllib

    target = tomllib.loads((_ROOT / "config" / "v2" / "modal_target.toml").read_text("utf-8"))
    wanted = str((target.get("modal") or {}).get("workspace_id") or "").strip()
    for registry in (
        _ROOT / ".git" / "comfymodal" / "modal_workspaces.json",
        _ROOT / ".modal_workspaces.json",
    ):
        if not registry.is_file():
            continue
        data = json.loads(registry.read_text("utf-8"))
        workspace = next(
            (w for w in data.get("workspaces", []) if str(w.get("id") or "") == wanted), None
        )
        if workspace and workspace.get("token_id") and workspace.get("token_secret"):
            return workspace
    raise RuntimeError(f"no credentials for destination workspace {wanted}")


def main() -> int:
    workspace = _workspace()
    os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])

    import modal

    out_dir = _ROOT / "source_fullfile_runs"
    out_dir.mkdir(exist_ok=True)
    for family, read_mib, qd in _CELLS:
        attempt = f"{family}-r{read_mib}-qd{qd}-retry"
        fn = modal.Function.from_name(_APP, f"run_fullfile_{family}")
        try:
            handle = fn.with_options(timeout=_TIMEOUT_S)
            timeout_applied = True
        except Exception:
            handle = fn
            timeout_applied = False
        print(f"[retry] {attempt} timeout_s={_TIMEOUT_S} applied={timeout_applied}", flush=True)
        try:
            result = handle.remote(read_mib=read_mib, qd=qd, attempt_id=attempt)
            if not isinstance(result, dict):
                raise RuntimeError(f"returned {type(result).__name__}")
        except Exception as exc:
            result = {
                "status": "error",
                "error": f"{type(exc).__name__}:{exc}"[:500],
                "attempt_id": attempt,
                "timeout_s": _TIMEOUT_S,
            }
        result["retry_timeout_s"] = _TIMEOUT_S
        (out_dir / f"{attempt}.json").write_text(
            json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )
        print(f"[retry] {attempt} status={result.get('status')} "
              f"wall_ms={result.get('full_file_wall_ms')} "
              f"gbps={result.get('full_file_decimal_gbps')} "
              f"error={result.get('error')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
