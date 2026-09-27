"""Launch two deploy commands concurrently, wait with timeout, report exit codes.

The parent batch script writes each deploy command into a tiny ``.bat`` file so
the command arguments are already shell-resolved and the Python helper only needs
``subprocess.Popen(cmd_file, shell=True)`` — no argument quoting risk.

Key=value lines printed to stdout are consumed by the batch via ``for /f``.

Exit code from this script:
    0  → both child processes exited 0 within the timeout.
    1  → at least one child failed (non-zero exit) or timed out.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time


def main() -> int:
    if len(sys.argv) != 6:
        print(__doc__, file=sys.stderr)
        print(f"Got {len(sys.argv) - 1} arg(s), expected 5.", file=sys.stderr)
        return 2

    cmd1_path = os.path.normpath(sys.argv[1])
    cmd2_path = os.path.normpath(sys.argv[2])
    out1_path = os.path.normpath(sys.argv[3])
    out2_path = os.path.normpath(sys.argv[4])
    timeout_s_str = sys.argv[5].strip()

    if not os.path.isfile(cmd1_path):
        print(f"V1_CMD_FILE not found: {cmd1_path}", file=sys.stderr)
        return 2
    if not os.path.isfile(cmd2_path):
        print(f"V2_CMD_FILE not found: {cmd2_path}", file=sys.stderr)
        return 2

    try:
        timeout_s = float(timeout_s_str)
    except ValueError:
        timeout_s = 3600.0
    if timeout_s <= 0:
        timeout_s = 3600.0

    # ── Open both output files before starting children ────────────────
    try:
        f1 = open(out1_path, "wb", buffering=0)
        f2 = open(out2_path, "wb", buffering=0)
    except OSError as exc:
        print(f"Cannot open output files: {exc}", file=sys.stderr)
        return 2

    deadline = time.monotonic() + timeout_s
    timed_out = False

    try:
        # Launch both children concurrently
        p1 = subprocess.Popen(
            [cmd1_path],
            shell=True,
            stdout=f1,
            stderr=subprocess.STDOUT,
            env=os.environ,
        )
        p2 = subprocess.Popen(
            [cmd2_path],
            shell=True,
            stdout=f2,
            stderr=subprocess.STDOUT,
            env=os.environ,
        )

        remaining = deadline - time.monotonic()
        # ── Wait for both, polling so we can enforce a hard deadline ──
        while remaining > 0 and (p1.poll() is None or p2.poll() is None):
            try:
                p1.wait(timeout=min(1.0, remaining))
            except subprocess.TimeoutExpired:
                pass
            try:
                p2.wait(timeout=min(1.0, remaining))
            except subprocess.TimeoutExpired:
                pass
            remaining = deadline - time.monotonic()

        # ── Force-terminate any still-running child ────────────────────
        if p1.poll() is None:
            timed_out = True
            _try_terminate(p1)
        if p2.poll() is None:
            timed_out = True
            _try_terminate(p2)

        # If either was killed by us, treat as failure
        exit1 = p1.returncode if p1.returncode is not None else -1
        exit2 = p2.returncode if p2.returncode is not None else -1

    finally:
        f1.close()
        f2.close()

    # ── Print key=value results for the batch to parse ─────────────────
    # These MUST be the only stdout output (stderr is free for diagnostics).
    print(f"V1_EXIT={exit1}")
    print(f"V2_EXIT={exit2}")
    print(f"TIMED_OUT={str(timed_out).lower()}")

    overall_ok = not timed_out and exit1 == 0 and exit2 == 0
    return 0 if overall_ok else 1


def _try_terminate(proc: subprocess.Popen) -> None:
    """Best-effort terminate—no exception propagates."""
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
