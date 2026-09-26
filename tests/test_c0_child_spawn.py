"""FAST_UNIT: C0 child program is spawnable independently of its size."""

from __future__ import annotations

import os
import py_compile

import pytest

from comfymodal_runtime import golden_io_process_v2 as c0


pytestmark = pytest.mark.fast_unit


def test_child_source_materializes_to_compilable_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    path = c0.write_c0_child_source_file(c0._C0_CHILD_SOURCE)

    assert path.endswith(".py")
    assert open(path, "rb").read() == c0._C0_CHILD_SOURCE.encode("utf-8")
    py_compile.compile(path, doraise=True)


def test_child_source_file_is_content_hashed_and_reused(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    first = c0.write_c0_child_source_file("print('a')")
    second = c0.write_c0_child_source_file("print('a')")
    other = c0.write_c0_child_source_file("print('b')")

    assert first == second
    assert other != first
    assert open(other, "rb").read() == b"print('b')"


def test_child_program_exceeds_argv_spawn_but_file_spawn_has_no_argv():
    # Regression pin: the child program outgrew the kernel single-argument
    # limit (131072 bytes), which broke `python -c` spawn at restore.
    # File spawn carries only a short path in argv.
    size = len(c0._C0_CHILD_SOURCE.encode("utf-8"))
    assert size > 131072
    argv = ["python", "<child-file>", "shm-name", "1", "2", "3", "4"]
    assert max(len(part) for part in argv) < 4096
    assert os.path.basename(c0.__file__) == "golden_io_process_v2.py"
