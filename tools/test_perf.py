"""Run pytest with a small, permanent RX9P-T slow-test diagnostic guard.

The wrapper keeps the normal pytest command line intact while adding phase
timings and a hard wall clock.  It is intentionally stdlib-only apart from
pytest itself (which is the command being run)::

    python tools/test_perf.py tests/test_production_baseline.py::test_name
    python tools/test_perf.py --fast -m fast_unit tests/test_production_baseline.py

    Fast verification (lightweight, no heavy or remote tests)::

    python tools/test_perf.py --fast -m "not heavy_local and not remote" tests
    # pytest -m alone may still collect heavy modules for a broad selection.

Heavy-local verification::

    python tools/test_perf.py -m heavy_local tests
    pytest -m heavy_local

``--fast`` sets ``COMFYUI_MODAL_LIGHTWEIGHT_TEST=1`` and fails when any
measured test exceeds the FAST_UNIT budget (two seconds by default).  Stack
requests are sent periodically and shortly before the hard timeout.  On
Windows this uses CTRL_BREAK only when faulthandler signal registration
succeeds; otherwise the child uses faulthandler's periodic dump fallback.
On POSIX it uses SIGUSR1.  Stack output is kept in the command output rather
than creating diagnostic artifacts.
"""

from __future__ import annotations

import argparse
import ast
import faulthandler
import json
import os
import signal
import subprocess
import sys
import threading
import time
import tokenize
from pathlib import Path
from typing import Any, Iterator

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHASE_PREFIX = "RX9P_T_PHASE "
HEAVY_IMPORT_ROOTS = frozenset(
    {
        "torch",
        "modal",
        "comfyapp",
        "comfy",
        "folder_paths",
        "nodes",
        "execution",
        # These local runtime facades import the heavy roots during collection.
        "comfymodal_runtime.modal_transport",
        "comfymodal_runtime.modal_app",
        "comfymodal_runtime.clip_fast_hydration",
        "comfymodal_runtime.clip_fast_hydration_wiring",
        "comfymodal_runtime.clip_fp32_cast_once",
        "comfymodal_runtime.clip_qd_reader",
        "comfymodal_runtime.golden_serial",
        "comfymodal_runtime.gpu_snapshot_shadow",
        "comfymodal_runtime.runtime_executor",
        "comfymodal_runtime.speculative_clip_hydration",
        "canonical_execution",
        "modal_client",
        "tools.benchmark_v2_direct",
    }
)


def _is_heavy_import(module: str | None) -> bool:
    """Return whether an imported module belongs to the heavy-local set."""
    return bool(
        module
        and any(
            module == root or module.startswith(root + ".")
            for root in HEAVY_IMPORT_ROOTS
        )
    )


class _TopLevelImportScanner(ast.NodeVisitor):
    """Find imports that execute during module/class definition."""

    heavy = False

    def visit_Import(self, node: ast.Import) -> None:
        if any(_is_heavy_import(alias.name) for alias in node.names):
            self.heavy = True

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        imported_names = (
            [node.module]
            if node.module
            else []
        )
        if node.module:
            imported_names.extend(
                f"{node.module}.{alias.name}" for alias in node.names
            )
        if any(_is_heavy_import(module) for module in imported_names):
            self.heavy = True

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Imports inside tests/helpers do not run during module collection.
        return

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Class bodies execute while the module is imported.  Traverse them,
        # while visit_FunctionDef continues to exclude method bodies.
        for statement in node.body:
            self.visit(statement)


def _has_heavy_dynamic_loader(tree: ast.AST) -> bool:
    """Catch top-level importlib loaders for named heavy modules."""
    has_file_loader = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "spec_from_file_location"
        for node in ast.walk(tree)
    )
    if not has_file_loader:
        return False
    heavy_filenames = tuple(
        f"{module.rsplit('.', 1)[-1]}.py" for module in HEAVY_IMPORT_ROOTS
    )
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.endswith(heavy_filenames)
        for node in ast.walk(tree)
    )


def _scan_heavy_test_files() -> tuple[list[str], list[tuple[str, str]]]:
    """Return heavy test paths and readable AST-scan errors."""
    tests_root = PROJECT_ROOT / "tests"
    try:
        test_files = sorted(tests_root.rglob("*.py"), key=lambda path: path.as_posix())
    except (OSError, RuntimeError) as exc:
        return [], [("tests", f"{type(exc).__name__}: {exc}")]

    heavy_files: list[str] = []
    errors: list[tuple[str, str]] = []
    for path in test_files:
        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        try:
            # tokenize.open honors a source file's declared encoding.
            with tokenize.open(path) as source_file:
                tree = ast.parse(source_file.read(), filename=str(path))
            scanner = _TopLevelImportScanner()
            scanner.visit(tree)
        except Exception as exc:
            errors.append((relative_path, f"{type(exc).__name__}: {exc}"))
            continue
        if scanner.heavy or _has_heavy_dynamic_loader(tree):
            heavy_files.append(relative_path)
    return heavy_files, errors


def _is_broad_tests_selection(pytest_args: list[str]) -> bool:
    """Recognize a tests-directory target, but not an individual test file."""
    value_options = {
        "-c",
        "-k",
        "-m",
        "--basetemp",
        "--confcutdir",
        "--deselect",
        "--ignore",
        "--ignore-glob",
        "--override-ini",
        "--pyargs",
        "--rootdir",
    }
    broad = False
    explicit_test_target = False
    for index, argument in enumerate(pytest_args):
        if argument.startswith("-"):
            continue
        if index and pytest_args[index - 1] in value_options:
            continue
        target = argument.split("::", 1)[0].replace("\\", "/").rstrip("/")
        if target in {"tests", "./tests"}:
            broad = True
            continue
        try:
            raw_path = Path(argument.split("::", 1)[0])
            candidate = raw_path if raw_path.is_absolute() else PROJECT_ROOT / raw_path
            resolved = candidate.resolve()
            tests_root = (PROJECT_ROOT / "tests").resolve()
            if resolved == tests_root:
                broad = True
            elif tests_root in resolved.parents:
                explicit_test_target = True
        except (OSError, RuntimeError):
            continue
    return broad and not explicit_test_target


def _isolate_fast_collection(pytest_args: list[str]) -> list[str]:
    """Exclude heavy-local modules only for a broad fast-tier collection."""
    if not _is_broad_tests_selection(pytest_args):
        return pytest_args

    heavy_files, errors = _scan_heavy_test_files()
    for path, message in errors:
        print(f"FAST_COLLECTION_SCAN_ERROR path={path} error={message}", flush=True)
    paths = ",".join(heavy_files) if heavy_files else "(none)"
    print(f"FAST_COLLECTION_IGNORED count={len(heavy_files)} paths={paths}", flush=True)
    ignored_args = [argument for path in heavy_files for argument in ("--ignore", path)]
    return [*pytest_args, *ignored_args]


def _clock() -> float:
    return time.perf_counter()


def _emit_phase(phase: str, duration: float, **extra: object) -> None:
    """Emit one machine-readable phase record without hiding pytest output."""
    record = {
        "phase": phase,
        "duration_ms": round(duration * 1000, 3),
        **extra,
    }
    print(PHASE_PREFIX + json.dumps(record, sort_keys=True), flush=True)


class _PhasePlugin:
    """Pytest hooks whose boundaries are explicit and future-agent friendly."""

    def _time_hook(self, phase: str, item: Any, outcome: Any, started: float) -> None:
        try:
            outcome.get_result()
        finally:
            _emit_phase(phase, _clock() - started, nodeid=item.nodeid)

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_collection(self, session: Any) -> Iterator[None]:
        started = _clock()
        outcome = yield
        try:
            outcome.get_result()
        finally:
            _emit_phase("COLLECTION", _clock() - started, collected=len(session.items))

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_setup(self, item: Any) -> Iterator[None]:
        started = _clock()
        outcome = yield
        self._time_hook("SETUP", item, outcome, started)

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_call(self, item: Any) -> Iterator[None]:
        started = _clock()
        outcome = yield
        self._time_hook("CALL", item, outcome, started)

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_teardown(self, item: Any) -> Iterator[None]:
        started = _clock()
        outcome = yield
        self._time_hook("TEARDOWN", item, outcome, started)


_STACK_SIGNAL_REGISTERED = False
_STACK_DUMP_FALLBACK_ACTIVE = False


def _enable_child_stack_capture() -> None:
    """Install signal or periodic stack capture for the pytest child."""
    global _STACK_SIGNAL_REGISTERED, _STACK_DUMP_FALLBACK_ACTIVE
    _STACK_SIGNAL_REGISTERED = False
    _STACK_DUMP_FALLBACK_ACTIVE = False
    faulthandler.enable(file=sys.stderr, all_threads=True)
    # Some Windows Python builds expose faulthandler.enable() but not
    # faulthandler.register().  CTRL_BREAK_EVENT is unsafe for those builds,
    # so let faulthandler collect stacks without requiring signal delivery.
    if not hasattr(faulthandler, "register"):
        faulthandler.dump_traceback_later(5.0, repeat=True, file=sys.stderr)
        _STACK_DUMP_FALLBACK_ACTIVE = True
        return
    stack_signals = [
        value
        for name in ("SIGUSR1", "SIGBREAK")
        if (value := getattr(signal, name, None)) is not None
    ]
    for stack_signal in stack_signals:
        try:
            faulthandler.register(
                stack_signal, file=sys.stderr, all_threads=True, chain=False
            )
            _STACK_SIGNAL_REGISTERED = True
        except (OSError, RuntimeError, ValueError):
            # faulthandler.enable remains useful when signal registration is
            # unavailable in an embedded or restricted interpreter.
            continue
    if not _STACK_SIGNAL_REGISTERED:
        faulthandler.dump_traceback_later(5.0, repeat=True, file=sys.stderr)
        _STACK_DUMP_FALLBACK_ACTIVE = True


def _probe_parent_stack_signal() -> bool:
    """Check whether this interpreter can safely use Windows CTRL_BREAK.

    The parent and pytest child have separate module globals.  A successful
    registration probe gives the parent an equivalent capability check before
    it starts sending requests; the child still performs its own registration
    and enables the periodic fallback when that registration fails.
    """
    if os.name != "nt" or not hasattr(faulthandler, "register"):
        return False
    stack_signal = getattr(signal, "SIGBREAK", None)
    if stack_signal is None:
        return False
    registered = False
    try:
        faulthandler.register(
            stack_signal, file=sys.stderr, all_threads=True, chain=False
        )
        registered = True
    except (OSError, RuntimeError, ValueError):
        return False
    finally:
        if registered:
            try:
                unregister = getattr(faulthandler, "unregister")
                unregister(stack_signal)
            except (AttributeError, OSError, RuntimeError, ValueError):
                registered = False
    return registered


def pytest_configure(config: Any) -> None:
    """Register the plugin when this file is loaded by the child pytest."""
    _enable_child_stack_capture()
    plugin = _PhasePlugin()
    config.pluginmanager.register(plugin, "rx9p-t-test-perf-phases")


def _request_stack(proc: subprocess.Popen[bytes], kind: str) -> None:
    """Ask the child to dump all Python stacks, without creating a file."""
    print(f"RX9P_T_STACK_REQUEST kind={kind} pid={proc.pid}", flush=True)
    try:
        if os.name == "nt":
            if not _STACK_SIGNAL_REGISTERED:
                print(
                    "RX9P_T_STACK_NOTE no faulthandler signal registration "
                    "succeeded; periodic dump_traceback_later is active; "
                    "skipping CTRL_BREAK_EVENT",
                    flush=True,
                )
                return
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        elif hasattr(signal, "SIGUSR1"):
            proc.send_signal(signal.SIGUSR1)
    except (AttributeError, OSError, ValueError):
        # The process may have exited between poll() and send_signal().
        pass


def _watch_stacks(
    proc: subprocess.Popen[bytes],
    started: float,
    timeout: float,
    interval: float,
    stop: threading.Event,
) -> None:
    """Send periodic and pre-timeout stack requests while pytest is running."""
    interval = max(interval, 0.1)
    # A very short timeout can fire before pytest has imported this plugin.
    # CTRL_BREAK is then treated as an ordinary console interrupt on Windows
    # instead of a faulthandler request.  Let the parent own those short hard
    # deadlines and request the stack at the deadline itself.
    warning_at = (
        started + max(timeout - min(0.5, timeout / 4), 0.0)
        if timeout >= 2.0
        else float("inf")
    )
    next_periodic = started + interval
    timeout_sent = False
    while not stop.is_set() and proc.poll() is None:
        now = _clock()
        if not timeout_sent and now >= warning_at:
            _request_stack(proc, "timeout-warning")
            timeout_sent = True
        if now >= next_periodic:
            _request_stack(proc, "periodic")
            next_periodic += interval
        wait_for = min(
            max(next_periodic - now, 0.01),
            max(warning_at - now, 0.01) if not timeout_sent else interval,
        )
        stop.wait(wait_for)


def _parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        usage="%(prog)s [options] <pytest args>",
        description="Run python -m pytest with phase timings, stack capture, and a hard wall timeout.",
        epilog=(
            "Examples: python tools/test_perf.py tests/foo.py::test_bar; "
            "python tools/test_perf.py --fast -m \"not heavy_local and not remote\" tests; "
            "python tools/test_perf.py -m heavy_local tests; "
            "Use the wrapper for fast runs: pytest -m alone may still collect "
            "heavy modules with a broad selection."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--timeout", type=float, default=15.0, metavar="SECONDS",
        help="hard wall timeout for the pytest subprocess (default: 15)",
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="enable lightweight mode and enforce the FAST_UNIT budget",
    )
    parser.add_argument(
        "--budget", type=float, default=2.0, metavar="SECONDS",
        help="maximum measured wall time for any test in --fast (default: 2)",
    )
    parser.add_argument(
        "--stack-interval", type=float, default=5.0, metavar="SECONDS",
        help="periodic stack dump interval (default: 5)",
    )
    args, pytest_args = parser.parse_known_args(argv)
    # ``parse_known_args`` lets wrapper options appear before or after the
    # pytest target.  Unknown options and positional targets are forwarded in
    # their original order as far as argparse exposes them.
    pytest_args = list(pytest_args)
    if pytest_args[:1] == ["--"]:
        pytest_args.pop(0)
    return args, pytest_args


def _print_summary(
    process_start_wall: float,
    total_wall: float,
    phases: list[dict[str, object]],
    exit_code: int,
    timed_out: bool,
    budget_exceeded: bool,
    budget_wall: float,
    measured_test_count: int,
) -> None:
    print("\nRX9P_T_PHASE_SUMMARY", flush=True)
    print(
        f"PROCESS_START: {process_start_wall * 1000:.3f} ms "
        "(wrapper start -> pytest subprocess)",
        flush=True,
    )
    for phase in ("COLLECTION", "SETUP", "CALL", "TEARDOWN"):
        records = [item for item in phases if item.get("phase") == phase]
        total_ms = sum(float(item.get("duration_ms", 0.0)) for item in records)
        detail = f"count={len(records)} total_ms={total_ms:.3f}"
        if phase == "COLLECTION" and records:
            detail += f" collected={records[-1].get('collected', '?')}"
        print(f"{phase}: {detail}", flush=True)
    print(f"TOTAL_WALL: {total_wall * 1000:.3f} ms", flush=True)
    print(
        f"MEASURED_MAX_TEST_WALL: {budget_wall * 1000:.3f} ms "
        f"(tests={measured_test_count})",
        flush=True,
    )
    if timed_out:
        print(f"FAILURE: hard timeout exceeded ({total_wall:.3f}s)", flush=True)
    if budget_exceeded:
        print(
            f"FAILURE: FAST_UNIT budget exceeded "
            f"({budget_wall:.3f}s max test wall)",
            flush=True,
        )
    print(f"EXIT_CODE: {exit_code}", flush=True)


def main(argv: list[str] | None = None) -> int:
    args, pytest_args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than zero")
    if args.budget <= 0:
        raise SystemExit("--budget must be greater than zero")
    if args.stack_interval <= 0:
        raise SystemExit("--stack-interval must be greater than zero")

    if not pytest_args:
        pytest_args = ["tests"]
    if args.fast:
        pytest_args = _isolate_fast_collection(pytest_args)

    process_started = _clock()
    print("PROCESS_START", flush=True)
    env = os.environ.copy()
    env["PYTHONFAULTHANDLER"] = "1"
    if args.fast:
        env["COMFYUI_MODAL_LIGHTWEIGHT_TEST"] = "1"
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(PROJECT_ROOT), existing_pythonpath) if part
    )

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "tools.test_perf",
        *pytest_args,
    ]
    global _STACK_SIGNAL_REGISTERED
    _STACK_SIGNAL_REGISTERED = _probe_parent_stack_signal()
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    process_start_wall = _clock() - process_started
    _emit_phase("PROCESS_START", process_start_wall, scope="wrapper-to-pytest")
    stop = threading.Event()
    watcher = threading.Thread(
        target=_watch_stacks,
        args=(proc, process_started, args.timeout, args.stack_interval, stop),
        daemon=True,
    )
    watcher.start()

    timed_out = False
    try:
        output, _ = proc.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        _request_stack(proc, "timeout")
        proc.kill()
        output, _ = proc.communicate()
        if exc.output:
            output = exc.output + (output or b"")
    finally:
        stop.set()
        watcher.join(timeout=1.0)

    if output:
        sys.stdout.buffer.write(output)
        sys.stdout.flush()

    total_wall = _clock() - process_started
    phases: list[dict[str, object]] = []
    for line in output.decode("utf-8", errors="replace").splitlines() if output else []:
        # With ``-s`` pytest prints the progress dot without a newline, so a
        # teardown record can appear as ``.RX9P_T_PHASE ...``.
        marker = line.find(PHASE_PREFIX)
        if marker >= 0:
            try:
                phases.append(json.loads(line[marker + len(PHASE_PREFIX):]))
            except json.JSONDecodeError:
                pass

    exit_code = 124 if timed_out else (proc.returncode or 0)
    # Interpreter/plugin startup and collection are reported separately, but
    # are not part of the FAST_UNIT budget.  Measure each test independently
    # so a broad suite is not rejected solely because its tests add up to more
    # than the per-test budget.
    test_walls: dict[str, float] = {}
    for item in phases:
        nodeid = item.get("nodeid")
        if not isinstance(nodeid, str) or item.get("phase") not in {
            "SETUP",
            "CALL",
            "TEARDOWN",
        }:
            continue
        test_walls[nodeid] = test_walls.get(nodeid, 0.0) + (
            float(item.get("duration_ms", 0.0)) / 1000
        )
    budget_wall = max(test_walls.values(), default=0.0)
    budget_exceeded = bool(args.fast and budget_wall > args.budget)
    _print_summary(
        process_start_wall, total_wall, phases, exit_code, timed_out, budget_exceeded,
        budget_wall, len(test_walls),
    )
    if timed_out or budget_exceeded:
        return 124 if timed_out else 125
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
