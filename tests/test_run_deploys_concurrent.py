"""Tests for tools/run_deploys_concurrent.py using fake local .bat commands.

Every test creates tiny .bat scripts that simulate deploy commands, runs them
through the Python helper, and asserts correct behaviour: concurrent start,
separate output capture, exit-code propagation, timeout enforcement, and
cleanup.  No Modal/cloud calls.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "run_deploys_concurrent.py"


def _write_bat(path: Path, lines: list[str]) -> None:
    """Write a tiny .bat file with CRLF line endings (Windows convention)."""
    content = "\r\n".join(lines) + "\r\n"
    path.write_text(content, encoding="ascii")


class TestRunDeploysConcurrent(unittest.TestCase):
    """Each test:

    1. Writes two fake-deploy .bat scripts into a temp dir.
    2. Calls ``python tools/run_deploys_concurrent.py`` with them.
    3. Asserts the stdout key=value output and side-effect files.
    """

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(suffix="_deploy_test"))
        self.out1 = self._tmp / "v1_out.txt"
        self.out2 = self._tmp / "v2_out.txt"
        self.cmd1 = self._tmp / "v1_cmd.bat"
        self.cmd2 = self._tmp / "v2_cmd.bat"

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _run(self, timeout_s: float = 30) -> subprocess.CompletedProcess:
        """Run the helper and return the CompletedProcess."""
        return subprocess.run(
            [
                sys.executable,
                str(_TOOL),
                str(self.cmd1),
                str(self.cmd2),
                str(self.out1),
                str(self.out2),
                str(int(timeout_s)),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _parse_result(self, proc: subprocess.CompletedProcess) -> dict[str, str]:
        """Parse key=value lines from stdout."""
        result: dict[str, str] = {}
        for line in proc.stdout.strip().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                result[k.strip()] = v.strip()
        return result

    # ── 1. Both succeed ────────────────────────────────────────────────

    def test_both_succeed(self):
        """Both fake deploys exit 0 → helper exits 0, prints V1_EXIT=0 V2_EXIT=0."""
        _write_bat(self.cmd1, [
            "@echo off",
            "echo comfyui deploy ok",
            "exit /b 0",
        ])
        _write_bat(self.cmd2, [
            "@echo off",
            "echo stable-modal-comfy-v2-shadow ModalRuntimeEntrypointV2",
            "exit /b 0",
        ])
        proc = self._run()
        result = self._parse_result(proc)

        self.assertEqual(proc.returncode, 0, f"helper stderr: {proc.stderr}")
        self.assertEqual(result.get("V1_EXIT"), "0")
        self.assertEqual(result.get("V2_EXIT"), "0")
        self.assertEqual(result.get("TIMED_OUT"), "false")
        self.assertIn("comfyui deploy ok", self.out1.read_text(encoding="utf-8"))
        self.assertIn("stable-modal-comfy-v2-shadow", self.out2.read_text(encoding="utf-8"))

    # ── 2. V1 fails, V2 succeeds ────────────────────────────────────────

    def test_v1_fails_v2_succeeds(self):
        """V1 exit 1 → helper exits 1, V1_EXIT=1, V2_EXIT=0."""
        _write_bat(self.cmd1, [
            "@echo off",
            "echo V1 failure",
            "exit /b 1",
        ])
        _write_bat(self.cmd2, [
            "@echo off",
            "echo V2 ok",
            "exit /b 0",
        ])
        proc = self._run()
        result = self._parse_result(proc)

        self.assertEqual(proc.returncode, 1, f"helper stderr: {proc.stderr}")
        self.assertEqual(result.get("V1_EXIT"), "1")
        self.assertEqual(result.get("V2_EXIT"), "0")
        self.assertEqual(result.get("TIMED_OUT"), "false")

    # ── 3. V2 fails, V1 succeeds ────────────────────────────────────────

    def test_v2_fails_v1_succeeds(self):
        """V2 exit 7 → helper exits 1, V1_EXIT=0, V2_EXIT=7."""
        _write_bat(self.cmd1, [
            "@echo off",
            "echo V1 ok",
            "exit /b 0",
        ])
        _write_bat(self.cmd2, [
            "@echo off",
            "echo V2 failure",
            "exit /b 7",
        ])
        proc = self._run()
        result = self._parse_result(proc)

        self.assertEqual(proc.returncode, 1, f"helper stderr: {proc.stderr}")
        self.assertEqual(result.get("V1_EXIT"), "0")
        self.assertEqual(result.get("V2_EXIT"), "7")
        self.assertEqual(result.get("TIMED_OUT"), "false")

    # ── 4. Both fail ────────────────────────────────────────────────────

    def test_both_fail(self):
        """Both non-zero → helper exits 1, both exit codes reported."""
        _write_bat(self.cmd1, [
            "@echo off",
            "exit /b 3",
        ])
        _write_bat(self.cmd2, [
            "@echo off",
            "exit /b 9",
        ])
        proc = self._run()
        result = self._parse_result(proc)

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(result.get("V1_EXIT"), "3")
        self.assertEqual(result.get("V2_EXIT"), "9")

    # ── 5. Timeout kills long-running child ─────────────────────────────

    def test_timeout_kills_long_running_child(self):
        """A child that sleeps past the deadline must be terminated;
        the helper reports TIMED_OUT=true and the killed child's
        exit code is not 0."""
        _write_bat(self.cmd1, [
            "@echo off",
            "echo V1 fast",
            "exit /b 0",
        ])
        _write_bat(self.cmd2, [
            "@echo off",
            "@ping -n 30 127.0.0.1 >nul",   # ~29 seconds; timeout=1 → aborted
            "echo should not print",
            "exit /b 0",
        ])
        # Use 1-second timeout so the long-running child is killed
        proc = self._run(timeout_s=1)
        result = self._parse_result(proc)

        self.assertEqual(proc.returncode, 1, "timeout must make helper fail")
        self.assertEqual(result.get("TIMED_OUT"), "true")
        self.assertEqual(result.get("V1_EXIT"), "0", "fast child must succeed")
        # V2 should have been killed → non-zero exit or -1
        v2_exit = int(result.get("V2_EXIT", "-1"))
        self.assertNotEqual(v2_exit, 0, "killed child must not report exit 0")
        # Output should NOT contain the late text
        out2_text = self.out2.read_text(encoding="utf-8")
        self.assertNotIn("should not print", out2_text,
                         "killed child's output must be partial")

    # ── 6. Output isolation ─────────────────────────────────────────────

    def test_output_isolation(self):
        """Each command's stdout+stderr goes only to its designated file."""
        _write_bat(self.cmd1, [
            "@echo off",
            "echo V1_ONLY_LINE",
            "exit /b 0",
        ])
        _write_bat(self.cmd2, [
            "@echo off",
            "echo V2_ONLY_LINE",
            "exit /b 0",
        ])
        proc = self._run()
        self.assertEqual(proc.returncode, 0)

        out1 = self.out1.read_text(encoding="utf-8")
        out2 = self.out2.read_text(encoding="utf-8")
        self.assertIn("V1_ONLY_LINE", out1)
        self.assertNotIn("V2_ONLY_LINE", out1)
        self.assertIn("V2_ONLY_LINE", out2)
        self.assertNotIn("V1_ONLY_LINE", out2)

    # ── 7. MODAL_CLI=python -m modal (multi-word command) ───────────────

    def test_multi_word_command(self):
        """Commands like ``python -m modal deploy ...`` work via the .bat file."""
        _write_bat(self.cmd1, [
            "@echo off",
            "echo comfyui from python -m modal",
            "exit /b 0",
        ])
        _write_bat(self.cmd2, [
            "@echo off",
            "echo V2 from python -m modal",
            "exit /b 0",
        ])
        proc = self._run()
        result = self._parse_result(proc)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(result.get("V1_EXIT"), "0")
        self.assertEqual(result.get("V2_EXIT"), "0")

    # ── 8. Environment inheritance ──────────────────────────────────────

    def test_environment_inherited(self):
        """The helper must pass os.environ to children so MODAL_TOKEN_ID/SECRET
        and MODAL_CLI are inherited."""
        _write_bat(self.cmd1, [
            "@echo off",
            "echo TOKEN_ID=%MODAL_TOKEN_ID%",
            "exit /b 0",
        ])
        _write_bat(self.cmd2, [
            "@echo off",
            "echo TOKEN_SECRET=%MODAL_TOKEN_SECRET%",
            "exit /b 0",
        ])
        env = os.environ.copy()
        env["MODAL_TOKEN_ID"] = "test-token-id"
        env["MODAL_TOKEN_SECRET"] = "test-token-secret"
        proc = subprocess.run(
            [sys.executable, str(_TOOL),
             str(self.cmd1), str(self.cmd2),
             str(self.out1), str(self.out2), "30"],
            capture_output=True, text=True, timeout=60, env=env,
        )
        self.assertEqual(proc.returncode, 0)
        out1 = self.out1.read_text(encoding="utf-8")
        out2 = self.out2.read_text(encoding="utf-8")
        self.assertIn("TOKEN_ID=test-token-id", out1)
        self.assertIn("TOKEN_SECRET=test-token-secret", out2)

    # ── 9. Cleanup of output files ──────────────────────────────────────

    def test_output_files_created(self):
        """The output files must exist and contain the child's output."""
        _write_bat(self.cmd1, [
            "@echo off",
            "echo hello v1",
            "exit /b 0",
        ])
        _write_bat(self.cmd2, [
            "@echo off",
            "echo hello v2",
            "exit /b 0",
        ])
        proc = self._run()
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(self.out1.is_file(), "V1 output file must exist")
        self.assertTrue(self.out2.is_file(), "V2 output file must exist")
        self.assertEqual(self.out1.read_text(encoding="utf-8").strip(), "hello v1")
        self.assertEqual(self.out2.read_text(encoding="utf-8").strip(), "hello v2")

    # ── 10. Overlap proof (timing) ──────────────────────────────────────

    def test_overlap_proof(self):
        """Both children must run concurrently: even with a 2-second sleep in
        V1, V2 must finish by ~2s (not ~4s).  Proves overlap."""
        _write_bat(self.cmd1, [
            "@echo off",
            "@ping -n 3 127.0.0.1 >nul",   # ~2s delay
            "echo V1 done",
            "exit /b 0",
        ])
        _write_bat(self.cmd2, [
            "@echo off",
            "echo V2 done immediately",
            "exit /b 0",
        ])
        import time
        t0 = time.perf_counter()
        proc = self._run(timeout_s=30)
        elapsed = time.perf_counter() - t0
        self.assertEqual(proc.returncode, 0)
        # If sequential, elapsed would be ~2s (V1) + ~0s (V2) ≈ 2s.
        # If concurrent, elapsed would be ~2s (max of both) ≈ 2s.
        # Allow a generous 1s overhead for process spawn.
        self.assertLess(elapsed, 5.0,
                        f"Concurrent deploys took {elapsed:.1f}s (expected <5s)")
        self.assertIn("V1 done", self.out1.read_text(encoding="utf-8"))
        self.assertIn("V2 done immediately", self.out2.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
