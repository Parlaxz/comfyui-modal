import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from comfymodal_runtime.source_race_oracle import percentile, run_race_oracle, sample_stdev


pytestmark = pytest.mark.fast_unit


def _file(tmp_path, size=200):
    path = tmp_path / "source.bin"
    path.write_bytes(bytes(range(size)))
    return str(path)


def _run(path, *, race_width, logical_qd=1, read_bytes=64, opener=None, read=None, fd_mode="independent", **kwargs):
    opened = []

    def default_opener(_path):
        fd = 100 + len(opened)
        opened.append(fd)
        return fd

    report = run_race_oracle(
        file_path=path,
        race_width=race_width,
        logical_qd=logical_qd,
        read_bytes=read_bytes,
        fd_mode=fd_mode,
        fd_opener=opener or default_opener,
        read_syscall=read,
        fd_closer=lambda _fd: None,
        **kwargs,
    )
    return report, opened


def test_statistics_and_winner_selection_use_only_valid_attempts(tmp_path):
    path = _file(tmp_path)

    def read(fd, target, offset):
        racer = fd - 100
        if racer == 0:
            return len(target) - 1
        if racer == 1:
            time.sleep(0.002)
        if racer == 2:
            target[:] = bytes(range(offset, offset + len(target)))
            return len(target)
        raise OSError("scripted failure")

    report, opened = _run(path, race_width=4, read=read)
    block = report["blocks"][0]
    assert block["winner_racer_index"] == 2
    assert block["fighters"][0]["status"] == "short"
    assert block["fighters"][3]["status"] == "error"
    assert report["accepted"]["count"] == report["config"]["block_count"]
    assert report["physical"]["count"] == report["amplification"]["attempts_launched"]
    assert len(opened) == 4


def test_wave_release_accepted_wall_and_drain_fields(tmp_path):
    path = _file(tmp_path, 130)
    events = []

    def read(fd, target, offset):
        events.append(offset)
        if offset == 0 and fd == 101:
            time.sleep(0.012)
        target[:] = bytes(range(offset, offset + len(target)))
        return len(target)

    report, opened = _run(path, race_width=2, logical_qd=2, read=read)
    assert len(opened) == 4
    assert report["waves"][0]["wave_release_ns"] == report["blocks"][0]["wave_release_ns"]
    assert report["blocks"][0]["wave_release_ns"] == report["blocks"][1]["wave_release_ns"]
    assert report["blocks"][2]["offset"] == 128
    assert report["blocks"][2]["length"] == 2
    assert all(block["attempts_alive_after_drain"] == 0 for block in report["blocks"])
    assert all("winner_to_loser_end_delta_ms" in block for block in report["blocks"])
    assert report["blocks"][0]["cumulative_attempts_before_block"] == 0
    assert report["blocks"][1]["cumulative_attempts_before_block"] == 2
    assert report["blocks"][2]["cumulative_physical_bytes_before_block"] == 256
    expected = sum(
        max(block["accepted_preadv_ms"] for block in report["blocks"] if block["wave_index"] == wave["wave_index"])
        for wave in report["waves"]
    )
    assert report["wall"]["accepted_wave_wall_ms"] == pytest.approx(expected)
    assert report["wall"]["total_wall_ms"] > report["wall"]["accepted_wave_wall_ms"]
    assert events.index(128) > 1


def test_qd2_width4_opens_one_fd_per_lane_and_shared_lseek_fails(tmp_path, monkeypatch):
    path = _file(tmp_path)
    report, opened = _run(path, race_width=4, logical_qd=2, read=lambda _fd, target, _offset: len(target))
    assert len(opened) == 8
    assert {
        fighter["fd_id"]
        for block in report["blocks"]
        for fighter in block["fighters"]
    } == set(opened)

    monkeypatch.setattr(os, "preadv", None, raising=False)
    monkeypatch.setattr(os, "pread", None, raising=False)
    with pytest.raises(RuntimeError, match="lseek"):
        run_race_oracle(
            file_path=path,
            race_width=2,
            fd_mode="shared",
            read_syscall=None,
            fd_opener=lambda _path: 1,
            fd_closer=lambda _fd: None,
        )


def test_hash_modes_are_in_memory_and_amplification_is_explicit(tmp_path, monkeypatch):
    path = _file(tmp_path, 130)
    expected = hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def read(_fd, target, offset):
        target[:] = bytes(range(offset, offset + len(target)))
        return len(target)

    report, _ = _run(path, race_width=2, read=read, hash_mode="none")
    assert report["integrity"]["sha256_checked"] is False
    assert report["amplification"]["attempts_launched"] == 6
    assert report["amplification"]["accepted_bytes"] == 130
    assert report["amplification"]["speculative_byte_amplification_ratio"] == pytest.approx(2.0)

    monkeypatch.setattr("builtins.open", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("file read")))
    report2, _ = _run(path, race_width=2, read=read, hash_mode="winners_in_order")
    assert report2["integrity"]["winner_sha256"] == expected


def test_torch_guard_is_transition_based_and_import_is_sterile(tmp_path):
    path = _file(tmp_path)
    code = (
        "import sys; "
        "from comfymodal_runtime.source_race_oracle import run_race_oracle; "
        f"run_race_oracle(file_path={path!r}, race_width=1, read_bytes=8, "
        "fd_opener=lambda p: 1, read_syscall=lambda fd, target, off: len(target), "
        "fd_closer=lambda fd: None); "
        "assert 'torch' not in sys.modules"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    subprocess.run([sys.executable, "-c", code], check=True, env=env)


def test_percentiles_and_sample_stdev():
    values = [1.0, 2.0, 3.0, 4.0]
    assert percentile(values, 50) == 2.5
    assert percentile(values, 95) == pytest.approx(3.85)
    assert sample_stdev(values) == pytest.approx(1.2909944487)
