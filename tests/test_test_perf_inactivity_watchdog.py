"""Harness self-test: a genuine hang must still be caught by the watchdog.

Complements tests/test_test_perf_watchdog.py's unit coverage by exercising the
real subprocess path end to end.
"""

from __future__ import annotations

import pytest

# These spawn real pytest subprocesses and deliberately spend seconds each, so they
# are not FAST_UNIT: they verify the harness itself rather than product code.
pytestmark = pytest.mark.heavy_local


def test_real_hang_is_killed_by_inactivity_watchdog(tmp_path):
    """A sleeping test produces no phase output, so inactivity must fire."""
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    hang = tmp_path / "test_zz_hang.py"
    hang.write_text(
        "import time\n"
        "\n"
        "def test_hangs_forever():\n"
        "    time.sleep(600)\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "tools/test_perf.py",
            "--timeout",
            "3",
            "--stack-interval",
            "60",
            str(hang),
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=180,
    )
    out = proc.stdout + proc.stderr
    assert "inactivity timeout exceeded" in out, out[-3000:]
    # 124 is the existing "timed out" code; it must not read as success.
    assert proc.returncode != 0, out[-2000:]


def test_slow_but_progressing_suite_is_not_killed(tmp_path):
    """Aggregate wall may exceed --timeout as long as progress continues."""
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    slow = tmp_path / "test_zz_slow_but_alive.py"
    # 6 tests x ~1.2s = ~7.2s of aggregate work with a 2s inactivity budget.
    # Each emits progress, so the watchdog must never fire.
    slow.write_text(
        "import time\n"
        "\n"
        "def test_one():\n    time.sleep(1.2)\n"
        "\n"
        "def test_two():\n    time.sleep(1.2)\n"
        "\n"
        "def test_three():\n    time.sleep(1.2)\n"
        "\n"
        "def test_four():\n    time.sleep(1.2)\n"
        "\n"
        "def test_five():\n    time.sleep(1.2)\n"
        "\n"
        "def test_six():\n    time.sleep(1.2)\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "tools/test_perf.py",
            "--timeout",
            "2",
            "--stack-interval",
            "60",
            str(slow),
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = proc.stdout + proc.stderr
    assert "inactivity timeout exceeded" not in out, out[-3000:]
    assert "6 passed" in out, out[-3000:]
    # Aggregate wall legitimately exceeded the 2s inactivity budget.
    assert proc.returncode == 0, out[-3000:]