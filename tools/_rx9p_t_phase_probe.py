"""Bounded import, collection, and test-call timing probe."""

from __future__ import annotations

import argparse
import builtins
import json
import sys
import time
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("node", help="pytest node id")
    parser.add_argument("--json", dest="json_path", type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    events: list[dict[str, object]] = [{"event": "PROCESS_START", "elapsed_ms": 0.0}]
    print("PROCESS_START", flush=True)
    original_import = builtins.__import__
    targets = ("comfyapp", "modal", "torch", "canonical_execution", "modal_client")

    class ProbePlugin:
        def _event(self, name: str, **extra: object) -> None:
            event = {"event": name, "elapsed_ms": round((time.perf_counter() - started) * 1000, 3), **extra}
            events.append(event)
            print(json.dumps(event, sort_keys=True), flush=True)

        def pytest_collection_finish(self, session) -> None:
            self._event("COLLECTION_FINISH", collected=len(session.items))

        def pytest_runtest_call(self, item) -> None:
            self._event("TEST_CALL_START", nodeid=item.nodeid)

    def traced_import(name, globals=None, locals=None, fromlist=(), level=0):
        matched = next((target for target in targets if name == target or name.startswith(target + ".")), None)
        import_started = time.perf_counter() if matched else 0.0
        if matched:
            print(json.dumps({"event": "IMPORT_START", "module": matched}), flush=True)
        try:
            return original_import(name, globals, locals, fromlist, level)
        finally:
            if matched:
                event = {
                    "event": "IMPORT_END",
                    "module": matched,
                    "elapsed_ms": round((time.perf_counter() - import_started) * 1000, 3),
                }
                events.append(event)
                print(json.dumps(event, sort_keys=True), flush=True)

    builtins.__import__ = traced_import
    try:
        result_code = pytest.main(["-s", args.node], plugins=[ProbePlugin()])
    finally:
        builtins.__import__ = original_import
    events.append({
        "event": "PROCESS_END",
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "returncode": int(result_code),
    })
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(events, indent=2), encoding="utf-8")
    return int(result_code)


if __name__ == "__main__":
    raise SystemExit(main())
