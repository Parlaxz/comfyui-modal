"""Test A — Tiny image Blackwell platform restore lower bound.

Minimal Modal app, tiny image, RTX PRO 6000, memory snapshot enabled.
No ComfyUI, no volumes, no custom nodes, no model paths.

Goal: establish the lower bound for Blackwell platform_restore.
"""

import os
import time

import modal

APP_NAME = "comfyui-platform-a"

app = modal.App(APP_NAME)

_tiny_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch==2.7.0")
)


@app.cls(
    gpu="rtx-pro-6000",
    enable_memory_snapshot=True,
    image=_tiny_image,
    secrets=[modal.Secret.from_name("comfyui-warmup-dev")],
    cpu=4,
    memory=32768,
    timeout=120,
    min_containers=0,
    scaledown_window=4,
)
class TinyBlackwell:
    """Minimal Blackwell app — just count to measure restore."""

    @modal.enter(snap=True)
    def startup(self):
        self._call_count = 0
        self._startup_t = time.time()
        self._restore_count = 0

    @modal.enter(snap=False)
    def restore(self):
        self._restore_count += 1
        self._restore_start = time.time()

    @modal.method()
    def ping(self) -> dict:
        self._call_count += 1
        now = time.time()
        return {
            "restore_start_unix_s": getattr(self, "_restore_start", 0.0),
            "restore_end_unix_s": now,
            "call_count": self._call_count,
            "restore_count": self._restore_count,
        }


if __name__ == "__main__":
    # Deploy and run 5 cold restore measurements
    n_runs = int(os.environ.get("N_RUNS", "5"))
    gap_s = int(os.environ.get("GAP_S", "20"))

    print(f"Deploying {APP_NAME}...")
    # Deploy by running modal deploy on this file
    print(f"Run: modal deploy {__file__}")
    print(f"Then run this script with N_RUNS={n_runs} and GAP_S={gap_s}")
    print()
    print(f"Manual steps:")
    print(f"  1. modal deploy {__file__}")
    print(f"  2. python {__file__} --run")
    print()
    print("---")
    import sys
    if "--run" not in sys.argv:
        print("Skipping benchmark. Use --run flag after deploying.")
        raise SystemExit(0)

    cls = modal.Cls.from_name(APP_NAME, "TinyBlackwell")()
    results = []
    for i in range(n_runs):
        t0 = time.time()
        result = cls.ping.remote()
        t1 = time.time()

        rss = result.get("restore_start_unix_s", 0)
        rse = result.get("restore_end_unix_s", 0)
        platform_restore_ms = round((rss - t0) * 1000, 1) if rss else -1
        wall_ms = round((t1 - t0) * 1000, 1)
        app_res_ms = round((rse - rss) * 1000, 1) if rss and rse else -1

        entry = {
            "run": f"RUN-{i+1}",
            "platform_restore_ms": platform_restore_ms,
            "app_restore_ms": app_res_ms,
            "wall_ms": wall_ms,
            "call_count": result.get("call_count", 0),
        }
        results.append(entry)
        print(f"[RUN-{i+1}] platform_restore={platform_restore_ms}ms "
              f"app_restore={app_res_ms}ms wall={wall_ms}ms "
              f"call_count={result.get('call_count',0)}")

        if i < n_runs - 1:
            print(f"  → waiting {gap_s}s...")
            time.sleep(gap_s)

    print(f"\n{'='*60}")
    print(f"Tiny Blackwell — {n_runs} cold restore measurements")
    print(f"{'='*60}")
    for r in results:
        status = "cold_blob" if r["platform_restore_ms"] > 30000 else "cached"
        print(f"  {r['run']}: platform={r['platform_restore_ms']:>7.0f}ms "
              f"app={r['app_restore_ms']:>7.0f}ms "
              f"wall={r['wall_ms']:>7.0f}ms [{status}]")
