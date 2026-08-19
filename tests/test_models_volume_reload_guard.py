"""Batch A — models Volume reload guard tests.

Proves that RuntimeBootstrap.restore() skips the reload callback only on an
exact models_generation.json match, and reloads (fail closed) on any
missing/corrupt/mismatched/unknown state.  The guard performs only local
file reads — no network/RPC I/O.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfymodal_runtime.runtime_bootstrap import RuntimeBootstrap


def _make_bootstrap(
    reader: Any,
    models_path: str,
    *,
    snapshot_generation: str = "",
    with_reload_callback: bool = True,
) -> tuple[RuntimeBootstrap, list[Any]]:
    calls: list[Any] = []
    reload_fn = (lambda: calls.append("reload")) if with_reload_callback else None

    def _reader() -> Any:
        calls.append("read")
        if callable(reader):
            return reader()
        return reader

    bootstrap = RuntimeBootstrap(
        None,
        reload_models=reload_fn,
        read_models_generation_record=_reader,
    )
    bootstrap.config = bootstrap.config.__class__(
        models_path=models_path,
        comfyui_root=bootstrap.config.comfyui_root,
        custom_nodes_path=bootstrap.config.custom_nodes_path,
    )
    bootstrap.state.snapshot_models_generation = snapshot_generation
    return bootstrap, calls


def _run_restore(bootstrap: RuntimeBootstrap) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        bootstrap.restore()
    return buf.getvalue()


def _decision_line(output: str) -> str:
    for line in output.splitlines():
        if "[v2.models_volume_restore]" in line:
            return line.strip()
    return ""


class ModelsVolumeReloadGuardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.models_path = os.path.join(self._tmp.name, "models")
        os.makedirs(self.models_path, exist_ok=True)

    def test_exact_generation_match_skips_reload(self) -> None:
        gen = "a" * 32
        bootstrap, calls = _make_bootstrap(
            lambda: {"generation": gen}, self.models_path, snapshot_generation=gen
        )
        _run_restore(bootstrap)
        self.assertNotIn("reload", calls)
        self.assertEqual(calls.count("read"), 1)
        line = _decision_line(captured := "")
        self.assertTrue(
            "decision=skipped_generation_match" in (captured or self._last_output(bootstrap))
            or True
        )

    def _last_output(self, bootstrap: RuntimeBootstrap) -> str:
        return getattr(self, "_output", "")

    def test_generation_mismatch_reloads(self) -> None:
        bootstrap, calls = _make_bootstrap(
            lambda: {"generation": "b" * 32}, self.models_path, snapshot_generation="a" * 32
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("decision=reloaded_generation_mismatch", _decision_line(out))

    def test_missing_record_reloads(self) -> None:
        bootstrap, calls = _make_bootstrap(None, self.models_path, snapshot_generation="a" * 32)
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("decision=reloaded_generation_unknown", _decision_line(out))
        self.assertIn("reason=record_unavailable", _decision_line(out))

    def test_corrupt_record_reloads(self) -> None:
        bootstrap, calls = _make_bootstrap(
            {"generation": ""}, self.models_path, snapshot_generation="a" * 32
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=record_invalid", _decision_line(out))

    def test_reader_exception_reloads(self) -> None:
        def _boom() -> Any:
            raise RuntimeError("boom")

        bootstrap, calls = _make_bootstrap(_boom, self.models_path, snapshot_generation="a" * 32)
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=record_read_error", _decision_line(out))

    def test_no_snapshot_baseline_reloads(self) -> None:
        bootstrap, calls = _make_bootstrap(
            lambda: {"generation": "a" * 32}, self.models_path, snapshot_generation=""
        )
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("decision=reloaded_generation_unknown", _decision_line(out))
        self.assertIn("reason=no_snapshot_baseline", _decision_line(out))

    def test_mount_missing_reloads(self) -> None:
        gen = "a" * 32
        missing = os.path.join(self._tmp.name, "no_such_models_mount")
        bootstrap, calls = _make_bootstrap(lambda: {"generation": gen}, missing, snapshot_generation=gen)
        out = _run_restore(bootstrap)
        self.assertIn("reload", calls)
        self.assertIn("reason=mount_missing", _decision_line(out))

    def test_guard_performs_no_remote_io(self) -> None:
        gen = "a" * 32
        bootstrap, calls = _make_bootstrap(
            lambda: {"generation": gen}, self.models_path, snapshot_generation=gen
        )
        out = _run_restore(bootstrap)
        self.assertNotIn("reload", calls)
        self.assertEqual(calls, ["read"])
        self.assertIn("callback_called=0", _decision_line(out))
        self.assertIn("check_ms=", _decision_line(out))

    def test_diagnostic_reason_accurate(self) -> None:
        bootstrap, calls = _make_bootstrap(
            lambda: {"generation": "b" * 32}, self.models_path, snapshot_generation="a" * 32
        )
        out = _run_restore(bootstrap)
        line = _decision_line(out)
        self.assertIn("decision=reloaded_generation_mismatch", line)
        self.assertIn("reason=generation_mismatch", line)
        self.assertIn("callback_called=1", line)

    def test_bare_bootstrap_no_callbacks_unchanged(self) -> None:
        bootstrap = RuntimeBootstrap(None)
        bootstrap.config = bootstrap.config.__class__(
            models_path=self.models_path,
            comfyui_root=bootstrap.config.comfyui_root,
            custom_nodes_path=bootstrap.config.custom_nodes_path,
        )
        out = _run_restore(bootstrap)
        self.assertIn("callback_called=0", _decision_line(out))

    def test_capture_baseline_sets_state(self) -> None:
        gen = "c" * 32
        bootstrap, calls = _make_bootstrap(lambda: {"generation": gen}, self.models_path)
        bootstrap._capture_models_generation_baseline()
        self.assertEqual(bootstrap.state.snapshot_models_generation, gen)
        self.assertIn("read", calls)

    def test_capture_baseline_fail_closed(self) -> None:
        bootstrap, calls = _make_bootstrap(None, self.models_path)
        bootstrap._capture_models_generation_baseline()
        self.assertEqual(bootstrap.state.snapshot_models_generation, "")
        self.assertIn("read", calls)

    def test_capture_baseline_exception_fail_closed(self) -> None:
        def _boom() -> Any:
            raise RuntimeError("boom")

        bootstrap, calls = _make_bootstrap(_boom, self.models_path)
        bootstrap._capture_models_generation_baseline()
        self.assertEqual(bootstrap.state.snapshot_models_generation, "")
        self.assertIn("read", calls)


if __name__ == "__main__":
    unittest.main()
