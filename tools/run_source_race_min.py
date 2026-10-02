#!/usr/bin/env python
"""Minimal direct runner for the source race oracle (no v2ctl receipt binding).

Invokes an already-deployed dedicated app function directly:

    run_source_race_h100 / run_source_race_rtx

on the ``sept-clip-source-race-oracle`` app.  Deployment is out of scope here;
this only invokes a deployed method.  It owns the deterministic Latin-square
width interleave and per-run artifact collection, and it runs strictly
serially (one invocation at a time) so each call lands on its own fresh
container (single_use_containers=True).

This collects raw results only.  No classification, no causal inference.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]

_DEFAULT_APP = "sept-clip-source-race-oracle"
_DEFAULT_WIDTHS = (1, 2, 4, 8, 16)
_FAMILIES = ("h100", "rtx")

# Deterministic Latin-square width order, applied independently per GPU family.
_LATIN = (
    (1, 2, 4, 8, 16),
    (16, 8, 4, 2, 1),
    (2, 8, 1, 16, 4),
    (4, 1, 16, 2, 8),
    (8, 16, 2, 4, 1),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def campaign_schedule(
    family: str, rounds: int, widths: tuple[int, ...], start_round: int = 1
) -> list[dict[str, Any]]:
    """Round-major Latin-square schedule; pure and unit-testable."""
    schedule: list[dict[str, Any]] = []
    for round_index in range(start_round, start_round + rounds):
        order = _LATIN[(round_index - 1) % len(_LATIN)]
        for width_index, width in enumerate(order):
            if width not in widths:
                continue
            schedule.append({
                "family": family,
                "round": round_index,
                "width_index": width_index,
                "race_width": width,
                "attempt_id": f"{family}-r{round_index}-w{width}",
            })
    return schedule


def _workspace_credentials() -> dict[str, Any]:
    """Credentials for the config-owned destination workspace (v2ctl authority)."""
    import tomllib

    target = tomllib.loads((_ROOT / "config" / "v2" / "modal_target.toml").read_text("utf-8"))
    wanted = str((target.get("modal") or {}).get("workspace_id") or "").strip()
    if not wanted:
        raise RuntimeError("no [modal].workspace_id in config/v2/modal_target.toml")
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


def _compact(result: dict[str, Any]) -> dict[str, Any]:
    """Small, non-secret summary for the console."""
    accepted = result.get("accepted") or {}
    physical = result.get("physical") or {}
    wall = result.get("wall") or {}
    integrity = result.get("integrity") or {}
    env = result.get("env") or {}
    blocks = result.get("blocks") or []
    alive = [b.get("attempts_alive_after_drain") for b in blocks]
    return {
        "status": result.get("status"),
        "error": result.get("error"),
        "resolved_path": result.get("resolved_path"),
        "requested_gpu": result.get("requested_gpu"),
        "observed_gpu": result.get("observed_gpu"),
        "provider": result.get("provider"),
        "region": result.get("region"),
        "container_session_id": result.get("container_session_id"),
        "syscall_impl": env.get("syscall_impl"),
        "preadv_available": env.get("preadv_available"),
        "blocks": len(blocks),
        "accepted_count": accepted.get("count"),
        "accepted_mean_ms": accepted.get("mean_ms"),
        "accepted_median_ms": accepted.get("median_ms"),
        "accepted_p95_ms": accepted.get("p95_ms"),
        "accepted_max_ms": accepted.get("max_ms"),
        "physical_count": physical.get("count"),
        "physical_median_ms": physical.get("median_ms"),
        "physical_max_ms": physical.get("max_ms"),
        "accepted_wave_wall_ms": wall.get("accepted_wave_wall_ms"),
        "total_wall_ms": wall.get("total_wall_ms"),
        "amplification_ratio": (result.get("amplification") or {}).get("speculative_byte_amplification_ratio"),
        "attempts_alive_after_drain_max": max([a for a in alive if isinstance(a, int)] or [0]),
        "errors": integrity.get("errors"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", default=_DEFAULT_APP)
    parser.add_argument("--gpu-family", choices=_FAMILIES, default="h100")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--start-round", type=int, default=1)
    parser.add_argument("--widths", default=",".join(map(str, _DEFAULT_WIDTHS)))
    parser.add_argument("--logical-qd", type=int, default=2)
    parser.add_argument("--read-bytes", type=int, default=134217728)
    parser.add_argument("--role", default="clip")
    parser.add_argument("--model-name", default="qwen_3_4b.safetensors")
    parser.add_argument("--fd-mode", default="independent")
    parser.add_argument("--hash-mode", default="winners_in_order")
    parser.add_argument("--max-blocks", type=int, default=0)
    parser.add_argument("--out", default=str(_ROOT / "source_race_runs"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    widths = tuple(int(w) for w in str(args.widths).split(",") if w.strip())
    schedule = campaign_schedule(args.gpu_family, args.rounds, widths, start_round=args.start_round)
    if args.dry_run:
        for item in schedule:
            print(f"{item['family']} round={item['round']} width={item['race_width']}")
        return 0

    workspace = _workspace_credentials()
    os.environ["MODAL_TOKEN_ID"] = str(workspace["token_id"])
    os.environ["MODAL_TOKEN_SECRET"] = str(workspace["token_secret"])
    environment = str(workspace.get("environment") or "")
    if environment:
        os.environ["MODAL_ENVIRONMENT"] = environment

    import modal

    function_name = f"run_source_race_{args.gpu_family}"
    fn = modal.Function.from_name(args.app, function_name)

    out_dir = Path(args.out)
    results: list[dict[str, Any]] = []
    previous_container: str | None = None
    for item in schedule:
        artifact = out_dir / f"{item['attempt_id']}.json"
        if artifact.exists():
            print(f"[race] skip {item['attempt_id']} (artifact exists)", flush=True)
            continue
        print(f"[race] start {item['attempt_id']} width={item['race_width']}", flush=True)
        result: dict[str, Any]
        try:
            result = fn.remote(
                role=args.role,
                model_name=args.model_name,
                race_width=int(item["race_width"]),
                logical_qd=int(args.logical_qd),
                read_bytes=int(args.read_bytes),
                max_blocks=int(args.max_blocks),
                fd_mode=args.fd_mode,
                hash_mode=args.hash_mode,
                attempt_id=item["attempt_id"],
            )
            if not isinstance(result, dict):
                raise RuntimeError(f"returned {type(result).__name__}")
        except Exception as exc:
            result = {"status": "error", "error": f"{type(exc).__name__}:{exc}"}
        container = str(result.get("container_session_id") or "")
        result["_attempt"] = {
            **item,
            "finished_at": _now(),
            "fresh_container_vs_previous": (
                None if previous_container is None else container != previous_container
            ),
        }
        previous_container = container or previous_container
        _atomic_write_json(artifact, result)
        results.append(result)
        print("[race] " + json.dumps(_compact(result), sort_keys=True), flush=True)

    ok = sum(1 for r in results if r.get("status") == "ok")
    print(f"[race] done ok={ok}/{len(results)} out={out_dir}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
