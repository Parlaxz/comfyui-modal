"""Run one diagnostic command with a hard timeout and stack evidence."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import threading
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--stack", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command[:1] == ["--"]:
        command.pop(0)
    if not command:
        parser.error("command is required after --")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.stack.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONFAULTHANDLER"] = "1"
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    started = time.perf_counter()
    with args.output.open("w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=creationflags,
        )
        timed_out = False

        def interrupt() -> None:
            nonlocal timed_out
            timed_out = True
            args.stack.write_text(
                f"TIMEOUT_THRESHOLD_SECONDS=15\nPID={proc.pid}\nLABEL={args.label}\n",
                encoding="utf-8",
            )
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            except (AttributeError, OSError, ValueError):
                proc.terminate()

        timer = threading.Timer(14.0, interrupt)
        timer.start()
        try:
            proc.wait(timeout=15.0)
        except subprocess.TimeoutExpired:
            interrupt()
            proc.kill()
            proc.wait()
        finally:
            timer.cancel()
        log.write(
            f"\nDIAGNOSTIC_WRAPPER_END elapsed_ms={(time.perf_counter() - started) * 1000:.3f} "
            f"exit_code={proc.returncode} timed_out={timed_out}\n"
        )
    return 124 if timed_out else (proc.returncode or 0)


if __name__ == "__main__":
    raise SystemExit(main())
