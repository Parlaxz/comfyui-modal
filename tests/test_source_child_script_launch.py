"""The source owner is launched as a standalone script, so it must import cleanly.

``SourceThreadProcess.spawn`` runs::

    python .../golden_source_threads.py --source-child ARENA CONTROL LOCK KIND

In that process the file is ``__main__`` with **no parent package**, so any
relative import inside it raises ``ImportError: attempted relative import with
no known parent package``.  The child's ``stderr`` is a pipe that nobody drains,
so such a failure surfaces only as a silent ``source_process_exited_before_ready``
during restore, with no traceback anywhere in the container logs.

These tests execute the file the same way production does, so that class of
import regression fails loudly in CI instead of on an H100.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "comfymodal_runtime" / "golden_source_threads.py"


def _run_as_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), *args],
        capture_output=True, text=True, timeout=120,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="source child is POSIX-only")
def test_module_declares_no_module_level_relative_imports() -> None:
    """The invariant that makes the script launch work, asserted structurally.

    A relative import anywhere at module scope breaks ``__main__`` execution,
    so this guards the whole file rather than one known call site.
    """
    offenders = [
        f"{number}: {line.strip()}"
        for number, line in enumerate(MODULE_PATH.read_text(encoding="utf-8").splitlines(), 1)
        if line.startswith("from .") or line.startswith("import .")
    ]
    assert not offenders, "module-level relative imports break script launch:\n" + "\n".join(offenders)


def test_help_runs_as_a_script_without_import_error() -> None:
    """Proves the file imports cleanly when it is ``__main__``.

    ``--help`` exits 0 through argparse before touching any POSIX-only setup,
    which is exactly enough to execute every module-level import.
    """
    result = _run_as_script("--help")
    combined = f"{result.stdout}\n{result.stderr}"
    assert "attempted relative import" not in combined, combined
    assert "ImportError" not in combined, combined
    assert result.returncode == 0, combined


def test_source_child_startup_emits_ready_or_a_readable_error() -> None:
    """A child that cannot start must fail loudly, never silently.

    Missing attachments make this exit non-zero, but the traceback must reach
    stderr so the failure is diagnosable.  Silent death is the bug this guards.
    """
    result = _run_as_script(
        "--source-child", "no-such-arena", "no-such-control", "/tmp/no-such-lock", "thread",
    )
    combined = f"{result.stdout}\n{result.stderr}"
    assert "attempted relative import" not in combined, combined
    if result.returncode != 0:
        # Non-zero is acceptable here (the attachments do not exist); silence is not.
        assert combined.strip(), "child failed without writing anything to stderr"


def test_probe_module_loads_under_main_package_conditions() -> None:
    """``_load_probe_module`` must not depend on being inside a package.

    Reproduces the two hostile facts of the source child at once: the module is
    ``__main__`` with an empty ``__package__``, and the repository root is not
    on ``sys.path``.  It also asserts the hazard is real by showing that a
    relative import genuinely fails under those conditions, so this test cannot
    pass vacuously.
    """
    repo_root = MODULE_PATH.parents[1]
    harness = textwrap.dedent(
        f"""
        import importlib.util, os, sys
        sys.path.insert(0, os.path.dirname(sys.argv[1]))
        sys.path = [p for p in sys.path
                    if os.path.abspath(p or ".") != os.path.abspath(sys.argv[2])]
        spec = importlib.util.spec_from_file_location("child_like", sys.argv[1])
        module = importlib.util.module_from_spec(spec)
        module.__package__ = ""
        sys.modules["child_like"] = module
        spec.loader.exec_module(module)

        try:
            exec("from .source_copy_probe import sentinel_record", module.__dict__)
            print("RELATIVE_IMPORT=unexpectedly_succeeded")
        except ImportError as exc:
            print("RELATIVE_IMPORT=failed_as_expected:" + type(exc).__name__)

        probe_module = module._load_probe_module()
        record = probe_module.sentinel_record()
        print("LOAD_PROBE_MODULE=ok")
        print("SENTINEL_OK=" + str(record["majflt_delta"] == (1 << 64) - 1))
        """
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(harness)
        harness_path = handle.name
    try:
        result = subprocess.run(
            [sys.executable, harness_path, str(MODULE_PATH), str(repo_root)],
            capture_output=True, text=True, timeout=120,
        )
    finally:
        os.unlink(harness_path)

    combined = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 0, combined
    assert "RELATIVE_IMPORT=failed_as_expected:ImportError" in combined, combined
    assert "LOAD_PROBE_MODULE=ok" in combined, combined
    assert "SENTINEL_OK=True" in combined, combined