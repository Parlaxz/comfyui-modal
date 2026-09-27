"""Fetch the restore-matrix stage lines + build evidence from the four arm apps' Modal logs."""
import asyncio, json, sys, re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARMS = {
    "cpu-aws": ("stable-modal-comfy-v2-cpu-restore-matrix-aws", "cpu"),
    "cpu-gcp": ("stable-modal-comfy-v2-cpu-restore-matrix-gcp", "cpu"),
    "gpu-aws": ("stable-modal-comfy-v2-gpu-restore-matrix-aws", "gpu"),
    "gpu-gcp": ("stable-modal-comfy-v2-gpu-restore-matrix-gcp", "gpu"),
}
# --evict swaps in the corrected-CPU arm apps (eviction enabled).
_EVICT_ARMS = {
    "cpu-aws": ("stable-modal-comfy-v2-cpu-evict-restore-matrix-aws", "cpu"),
    "cpu-gcp": ("stable-modal-comfy-v2-cpu-evict-restore-matrix-gcp", "cpu"),
}


async def fetch_logs(app_name: str, max_lines: int = 3000) -> list[tuple[float, str]]:
    ws = json.loads((ROOT / ".modal_workspaces.json").read_text(encoding="utf-8"))
    aid = ws["active_workspace_id"]
    entry = next(w for w in ws["workspaces"] if w.get("id") == aid)
    import modal
    from modal.cli.app import resolve_app_identifier
    from modal._logs import tail_logs
    from modal.client import _Client
    client = await _Client.from_credentials(entry["token_id"], entry["token_secret"])
    app_id, _, _ = await resolve_app_identifier(app_name, None, client)
    entries: list[tuple[float, str]] = []
    async for batch in tail_logs(client, app_id, max_lines):
        for item in batch.items:
            ts = getattr(item, "timestamp", None)
            if ts is None:
                continue
            raw = getattr(item, "data", b"")
            text = raw if isinstance(raw, str) else (raw or b"").decode("utf-8", "replace")
            entries.append((float(ts), text))
    return entries


async def main() -> None:
    import sys as _sys
    out: dict[str, Any] = {}
    arms = dict(ARMS)
    if "--evict" in _sys.argv:
        arms.update(_EVICT_ARMS)
    out_dir = ROOT / "matrix_runs"
    if "--dir" in _sys.argv:
        out_dir = ROOT / "matrix_runs" / _sys.argv[_sys.argv.index("--dir") + 1]
    for arm_key, (app_name, kind) in arms.items():
        entries = await fetch_logs(app_name)
        lines = [t for _, t in entries]
        stage_lines = [l.strip() for l in lines if "snapshot_size] stage=" in l]
        evict_lines = [l.strip() for l in lines if "[v2.snapshot_model_eviction]" in l]
        lifecycle = [l.strip() for l in lines if "method=startup snap=True" in l]
        enter_start = [l.strip() for l in lines if f"{kind}_snapshot_enter_start" in l]
        restored = [l.strip() for l in lines if f"{kind}_snapshot_size] stage=restored" in l]
        build_fp = {}
        for l in lines:
            m = re.search(r"\[v2\.snapshot_runtime\]\s+image_id=(\S+)\s+cloud=(\S+)\s+region=(\S+)", l)
            if m:
                build_fp = {"image_id": m.group(1), "cloud": m.group(2), "region": m.group(3)}
        out[arm_key] = {
            "app": app_name, "kind": kind,
            "enter_start_count": len(enter_start),
            "restored_line_count": len(restored),
            "stage_lines": stage_lines,
            "evict_lines": evict_lines,
            "lifecycle": lifecycle,
            "build_runtime_identity": build_fp,
        }
        print(f"===== {arm_key} ({app_name}) enter_start={len(enter_start)} restored={len(restored)} =====")
        for l in stage_lines:
            print("  " + l)
        for l in evict_lines:
            print("  " + l)
        for l in lifecycle[:3]:
            print("  " + l)
    (out_dir / "arm_log_stage_lines.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())
