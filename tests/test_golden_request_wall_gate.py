"""The Golden request wall gate must not be defeatable by a GIL-holding call.

The gate used to be a single ``threading.Timer`` that called ``os._exit(70)``.
Reaching ``os._exit`` from a Python thread needs the GIL, so a request sitting
in a blocking native call that holds the GIL could starve the timer thread
entirely: the gate never fired and the container kept holding an H100. That was
observed as a Golden request stuck in sampling for minutes with no gate output
at all, while a merely slow request (sampler inside an async wait, which
releases the GIL) tripped the very same gate normally.

These tests pin the out-of-process backstop and prove it kills a parent that is
deliberately holding the GIL.

The GIL-holding child uses catastrophic regex backtracking: ``re.match`` is a
single C-level call that does not release the interpreter lock, so a Python
timer thread in the same process genuinely cannot run. ``hashlib`` is NOT usable
here because it releases the GIL for large buffers.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import time

import pytest

pytestmark = pytest.mark.fast_unit

GATE_S = 0.5
JOIN_TIMEOUT_S = 8.0

_GIL_HOLDING_CHILD = textwrap.dedent(
    """
    import re, sys
    sys.stdout.write("child-ready\\n")
    sys.stdout.flush()
    # Exponential C-level backtracking: seconds of work inside one re.match
    # with the GIL held, exactly like a blocking torch/CUDA call.
    re.match(r"(a+)+$", "a" * 32 + "b")
    sys.stdout.write("child-survived\\n")
    sys.stdout.flush()
    """
)

_GIL_RELEASED_CHILD = textwrap.dedent(
    """
    import sys, time
    sys.stdout.write("child-ready\\n")
    sys.stdout.flush()
    time.sleep(600)
    sys.stdout.write("child-survived\\n")
    sys.stdout.flush()
    """
)


def _arm_watchdog_against(child_src: str):
    """Start `child_src`, wait until it is inside its blocking call, arm the
    real watchdog against it, and report whether the watchdog killed it."""
    from comfymodal_runtime.golden_parallel import _GATE_WATCHDOG_SRC

    child = subprocess.Popen([sys.executable, "-u", "-c", child_src],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    watchdog = None
    try:
        assert child.stdout is not None
        deadline = time.time() + 30
        ready = False
        while time.time() < deadline:
            line = child.stdout.readline().decode("utf-8", "replace")
            if line.strip() == "child-ready":
                ready = True
                break
        assert ready, "child never reached its blocking call"

        watchdog = subprocess.Popen(
            [sys.executable, "-u", "-c", _GATE_WATCHDOG_SRC,
             str(child.pid), repr(GATE_S)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        # Timeout is deliberately far shorter than the child's own blocking
        # work, so the only way out is the watchdog firing.
        try:
            out, _ = child.communicate(timeout=JOIN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            # Surface the watchdog's own output: a watchdog that failed to
            # start or died on a syntax error must be visible, not silent.
            try:
                wout, _ = watchdog.communicate(timeout=10)
            except Exception:
                wout = b""
            raise AssertionError(
                "watchdog did not kill the child within %.1fs; watchdog output=%r"
                % (JOIN_TIMEOUT_S, (wout or b"").decode("utf-8", "replace")[:800])
            )
        return child.returncode, out.decode("utf-8", "replace")
    finally:
        for proc in (watchdog, child):
            if proc is not None and proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    pass


def test_watchdog_kills_a_parent_holding_the_gil():
    """The regression itself: the GIL-held parent must still be killed."""
    rc, out = _arm_watchdog_against(_GIL_HOLDING_CHILD)
    assert "child-survived" not in out, (
        "watchdog failed to kill a parent whose GIL was held by a C call"
    )
    assert rc != 0 and rc is not None, "expected a signal/forced termination, got %r" % (rc,)


def test_watchdog_kills_a_parent_with_the_gil_released():
    rc, out = _arm_watchdog_against(_GIL_RELEASED_CHILD)
    assert "child-survived" not in out
    assert rc == -9 or rc == 15 or rc == 9, (
        "expected forced termination (-9 POSIX / 15 Windows), got %r" % (rc,)
    )


def test_gate_install_arms_a_watchdog_and_cancel_reaps_it():
    from comfymodal_runtime import golden_parallel as gp

    gp._PROGRESS_STATE.pop("gate_watchdog", None)
    gp._install_request_wall_gate(gate_s=600.0)
    watchdog = gp._PROGRESS_STATE.get("gate_watchdog")
    assert watchdog is not None, "install must arm the out-of-process watchdog"
    assert watchdog.poll() is None
    gp._cancel_request_wall_gate()
    assert gp._PROGRESS_STATE.get("gate_watchdog") is None
    deadline = time.time() + 10
    while time.time() < deadline and watchdog.poll() is None:
        time.sleep(0.05)
    assert watchdog.poll() is not None, "cancel must terminate the watchdog process"


def test_watchdog_start_failure_is_non_fatal(monkeypatch):
    """A watchdog that cannot start must never break the request."""
    from comfymodal_runtime import golden_parallel as gp

    def _boom(*_a, **_k):
        raise OSError("cannot spawn")

    monkeypatch.setattr(gp.subprocess, "Popen", _boom)
    assert gp._start_request_wall_gate_watchdog(1.0) is None
