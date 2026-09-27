"""Record a V2 teardown timeline and poll the exact Modal container."""

from __future__ import annotations

import argparse
import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


PREFIX = "[v2.teardown] "


def _now_ns() -> int:
    return time.time_ns()


def _read_events(lines: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    events: dict[str, Any] = {}
    identity: dict[str, Any] = {}
    for line in lines:
        if PREFIX in line:
            raw = line.split(PREFIX, 1)[1].strip()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            event = str(payload.get("event", ""))
            if event:
                events[event] = payload
            for key in ("modal_container_id", "modal_input_id", "modal_task_id", "container_session_id"):
                if payload.get(key):
                    identity[key] = payload[key]
        if "[v2.remote_request_origin.remote]" in line:
            fields: dict[str, str] = {}
            for part in line.split("]", 1)[-1].split():
                if "=" in part:
                    key, value = part.split("=", 1)
                    fields[key] = value
            if fields.get("modal_container_id"):
                identity["modal_container_id"] = fields["modal_container_id"]
            if fields.get("modal_input_id"):
                identity["modal_input_id"] = fields["modal_input_id"]
            if fields.get("modal_task_id"):
                identity["modal_task_id"] = fields["modal_task_id"]
            if fields.get("modal_method_entry_unix_ns"):
                events["remote_request_entry"] = {
                    "wall_unix_ns": int(fields["modal_method_entry_unix_ns"]),
                    "modal_input_id": fields.get("modal_input_id", ""),
                    "modal_task_id": fields.get("modal_task_id", ""),
                }
    return events, identity


def _contains_container(value: Any, container_id: str) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"id", "container_id", "containerId"} and str(item) == container_id:
                return True
            if _contains_container(item, container_id):
                return True
    elif isinstance(value, list):
        return any(_contains_container(item, container_id) for item in value)
    return False


def _container_present(container_id: str) -> bool:
    try:
        completed = subprocess.run(
            ["modal", "container", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            return True
        payload = json.loads(completed.stdout or "[]")
        return _contains_container(payload, container_id)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return True


def _run_command(
    command: list[str],
    output_path: Path,
    *,
    poll_interval: float,
    timeout: float,
) -> tuple[list[str], int, int, int | None]:
    started_ns = _now_ns()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    line_queue: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            line_queue.put(line)
        line_queue.put(None)

    reader = threading.Thread(target=read_output, name="v2-measure-output", daemon=True)
    reader.start()
    container_id = ""
    disappeared_ns: int | None = None
    done_reading = False
    deadline = time.monotonic() + max(0.0, float(timeout))
    with output_path.open("w", encoding="utf-8") as output:
        while process.poll() is None or not done_reading:
            try:
                while True:
                    line = line_queue.get_nowait()
                    if line is None:
                        done_reading = True
                        break
                    lines.append(line)
                    output.write(line)
                    output.flush()
                    _, identity = _read_events([line])
                    container_id = container_id or str(identity.get("modal_container_id", ""))
                    print(line, end="")
            except queue.Empty:
                pass
            if container_id and disappeared_ns is None:
                if not _container_present(container_id):
                    disappeared_ns = _now_ns()
            if process.poll() is None or not done_reading:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    process.terminate()
                    break
                time.sleep(min(max(0.1, float(poll_interval)), remaining))
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    return lines, process.returncode or 0, started_ns, disappeared_ns


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("v2_teardown_timeline.json"))
    parser.add_argument("--container-id", default="")
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--invoke", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    lines: list[str]
    local_start_ns: int | None = None
    local_output_ns: int | None = None
    disappearance_ns: int | None = None
    return_code: int | None = None
    if args.invoke:
        capture_path = args.log_file or Path("v2_teardown_command.log")
        lines, return_code, local_start_ns, disappearance_ns = _run_command(
            args.invoke,
            capture_path,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
        )
        local_output_ns = _now_ns()
    elif args.log_file:
        lines = args.log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    else:
        parser.error("provide --invoke or --log-file")

    events, identity = _read_events(lines)
    container_id = args.container_id or str(identity.get("modal_container_id", ""))
    if container_id and disappearance_ns is None:
        deadline = time.monotonic() + max(0.0, float(args.timeout))
        while time.monotonic() < deadline:
            if not _container_present(container_id):
                disappearance_ns = _now_ns()
                break
            time.sleep(max(0.1, float(args.poll_interval)))

    timestamps = {
        "local_invocation_start": local_start_ns,
        "remote_request_entry": (events.get("remote_request_entry") or {}).get("wall_unix_ns"),
        "remote_final_output": (events.get("request_terminal_start") or {}).get("wall_unix_ns"),
        "local_output_received": local_output_ns,
        "request_terminal": (events.get("request_terminal_end") or {}).get("wall_unix_ns"),
        "exit_hook_start": (events.get("exit_hook_start") or {}).get("wall_unix_ns"),
        "exit_hook_end": (events.get("exit_hook_end") or {}).get("wall_unix_ns"),
        "python_atexit": (events.get("python_atexit") or {}).get("wall_unix_ns"),
        "container_disappeared": disappearance_ns,
    }
    report = {
        "container_id": container_id or None,
        "identity": identity,
        "return_code": return_code,
        "timestamps": timestamps,
        "events": events,
        "measurement_status": "container_polled" if disappearance_ns is not None else "container_unmeasured",
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "measurement_status": report["measurement_status"], "container_id": container_id or None}))
    return 0 if return_code in (None, 0) else return_code


if __name__ == "__main__":
    raise SystemExit(main())
