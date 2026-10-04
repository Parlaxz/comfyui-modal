"""Contracts for arm A4: synchronous full-file positioned read, then the same mmap.

A4 exists because A2 and A3 could not answer the question.  On this Modal Volume
/ gVisor path ``posix_fadvise(WILLNEED)`` returned in 0.040 ms and
``mmap(MAP_POPULATE)`` returned in 0.774 ms for a 12,309,866,400-byte file.
Reading 12.31 GB takes about 1.2 s, so both were accepted and neither
materialised anything: they tested whether the platform honours the request, not
whether having the bytes available removes the copy stall.

These tests pin the properties that make A4 a valid discriminator, and the ones
that would silently turn it into a different experiment:

* the control performs no warm read at all, provably;
* A4 warms AFTER the mapping exists and BEFORE any timed copy, so A and A4 share
  one mapping lifecycle and differ in exactly one variable;
* the warm path never touches the mapping -- it is a positioned read into a
  bounded reusable scratch buffer, not a second mmap and not a slice of the
  source mapping;
* the warm read is single-pass and unpipelined, because an overlap would void the
  claim that every byte was consumed before timing began;
* exact byte accounting: short reads, EINTR, a short final block and premature
  EOF are all handled, and anything short of the exact file size fails closed;
* the timed copy afterwards is still the production ``execute_block`` /
  ``libc.memmove`` path, untouched;
* the real Golden source owner later in the same container stays untreated.

The positioned-read syscall itself is stubbed at ``_pread_once``, because the test
host is Windows and has no ``os.preadv``.  Everything above the syscall -- buffer
slicing, the short-read loop, byte accounting, ordering, failure modes -- is the
real code.
"""

from __future__ import annotations

import os
import pathlib
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comfymodal_runtime import golden_source_threads as gsrc  # noqa: E402
from comfymodal_runtime import source_copy_isolation as sci  # noqa: E402
from comfymodal_runtime import source_population_policy as policy  # noqa: E402
from tools import source_copy_isolation_report as report_tool  # noqa: E402

_MIB = 1024 * 1024
ROOT = pathlib.Path(__file__).resolve().parents[1]


# ── a positioned-read syscall stub, with scriptable short reads ──────────

class _FakePread:
    """Scriptable stand-in for one positioned-read syscall.

    ``chunks`` is a per-call list of byte counts to return, consumed in order and
    repeating the last entry once exhausted, so a test can force a short read, a
    zero read (EOF) or an OSError at an exact point in the stream.
    """

    def __init__(self, chunks=(1 << 30,), *, raises: dict[int, BaseException] | None = None):
        self.chunks = list(chunks)
        self.raises = dict(raises or {})
        self.calls: list[dict] = []
        self.closed = False

    def __call__(self, fd: int, view, offset: int) -> int:  # noqa: ANN001
        index = len(self.calls)
        self.calls.append({
            "fd": int(fd),
            "offset": int(offset),
            "requested_bytes": len(view),
        })
        if index in self.raises:
            raise self.raises[index]
        want = self.chunks[min(index, len(self.chunks) - 1)]
        got = max(0, min(int(want), len(view)))
        if got:
            # Write real bytes so the buffer content is not simply left at zero;
            # a stub that never writes could hide a copy/length mistake.
            view[:got] = bytes([(got + index) % 251]) * got
        return got


def _patch_pread(monkeypatch, pread: _FakePread) -> None:
    monkeypatch.setattr(policy, "_pread_once", pread)
    monkeypatch.setattr(
        policy, "positioned_read_primitive", lambda: "os.preadv", raising=True
    )


def _warm(
    tmp_path: pathlib.Path, monkeypatch, *, arm: str, size: int = 4 * _MIB,
    block_bytes: int = _MIB, chunks=(1 << 30,), raises=None, gate: bool = True,
    pread: _FakePread | None = None,
):
    """Run the real ``full_file_read`` for one arm. Returns (evidence, pread).

    A real descriptor on a real (small) file, with only the positioned-read
    syscall stubbed.  ``size`` is the declared file size handed to the function,
    which is what the mapping would have reported; the file on disk only has to
    be openable, because the stub decides how many bytes each call returns.
    """
    reader = pread or _FakePread(chunks, raises=raises)
    _patch_pread(monkeypatch, reader)
    monkeypatch.setenv(policy.ARM_ENV, arm)
    if gate:
        monkeypatch.setenv(policy.POPULATION_GATE_ENV, "1")
    else:
        monkeypatch.delenv(policy.POPULATION_GATE_ENV, raising=False)
    path = tmp_path / "src.bin"
    path.write_bytes(b"\x5a" * 4096)
    fd = os.open(str(path), os.O_RDONLY)
    try:
        evidence = policy.full_file_read(
            fd, size=size, generation=7, block_bytes=block_bytes
        )
    finally:
        os.close(fd)
    return evidence, reader


# ── arm A: the control performs no warm read at all ───────────────────────

def test_the_control_performs_no_warm_full_file_read(tmp_path, monkeypatch):
    reader = _FakePread()
    _patch_pread(monkeypatch, reader)
    monkeypatch.setenv(policy.ARM_ENV, "A")
    monkeypatch.setenv(policy.POPULATION_GATE_ENV, "1")
    path = tmp_path / "control.bin"
    path.write_bytes(b"\x5a" * 4096)
    fd = os.open(str(path), os.O_RDONLY)
    try:
        evidence = policy.full_file_read(fd, size=4 * _MIB, generation=1)
    finally:
        os.close(fd)
    assert reader.calls == []
    assert evidence["warm_read_called"] is False
    assert evidence["warm_read_call_count"] == 0
    assert evidence["warm_complete"] is False
    assert evidence["arm"] == "A"
    assert "warm_bytes_read" not in evidence


def test_every_non_a4_arm_is_untreated_by_the_warm_read(tmp_path, monkeypatch):
        for arm in ("A2", "A3", "B", "C", "D"):
            reader = _FakePread()
            _patch_pread(monkeypatch, reader)
            monkeypatch.setenv(policy.ARM_ENV, arm)
            monkeypatch.setenv(policy.POPULATION_GATE_ENV, "1")
            path = tmp_path / f"{arm}.bin"
            path.write_bytes(b"\x5a" * 4096)
            fd = os.open(str(path), os.O_RDONLY)
            try:
                evidence = policy.full_file_read(fd, size=4 * _MIB, generation=1)
            finally:
                os.close(fd)
            assert reader.calls == [], arm
            assert evidence["warm_read_called"] is False, arm


def test_a4_without_the_gate_does_not_warm(tmp_path, monkeypatch):
    # The real Golden source owner runs in exactly this state.  It must be an
    # untreated control, not a container that tries to read 12.31 GB.
    evidence, reader = _warm(tmp_path, monkeypatch, arm="A4", gate=False)
    assert reader.calls == []
    assert evidence["warm_read_called"] is False
    assert evidence["arm"] == "A"


# ── A4: exact, bounded, unpipelined, and independent of the mapping ───────

def test_a4_reads_the_exact_full_file_size(tmp_path, monkeypatch):
    size = 4 * _MIB + 777          # deliberately not a block multiple
    evidence, reader = _warm(tmp_path, monkeypatch, arm="A4", size=size)
    assert evidence["warm_bytes_requested"] == size
    assert evidence["warm_bytes_read"] == size
    assert evidence["warm_complete"] is True
    assert evidence["warm_read_called"] is True
    assert evidence["warm_read_call_count"] == 1
    assert evidence["warm_uses_mmap"] is False


def test_a4_uses_the_same_descriptor_for_every_read(tmp_path, monkeypatch):
    evidence, reader = _warm(tmp_path, monkeypatch, arm="A4", size=4 * _MIB,
                             block_bytes=_MIB)
    fds = {call["fd"] for call in reader.calls}
    assert len(fds) == 1, "the warm read must not reopen the file per block"
    assert fds.pop() == evidence["fd"]


def test_a4_walked_the_whole_file_in_order_with_no_gap(tmp_path, monkeypatch):
    size = 4 * _MIB + 777
    evidence, reader = _warm(tmp_path, monkeypatch, arm="A4", size=size,
                             block_bytes=_MIB)
    covered = 0
    for call in reader.calls:
        assert call["offset"] == covered, "reads must be sequential and contiguous"
        assert call["requested_bytes"] > 0
        covered += call["requested_bytes"]
    assert covered == size
    # block records describe the same walk, with the short final block last
    blocks = evidence["warm_blocks"]
    assert sum(item["returned_bytes"] for item in blocks) == size
    assert blocks[-1]["requested_bytes"] == 777
    assert [item["ordinal"] for item in blocks] == list(range(len(blocks)))


def test_a4_reuses_one_bounded_scratch_buffer(tmp_path, monkeypatch):
    # A 12.31 GB anonymous copy would not fit beside the 1 GiB pinned arena and
    # would replace the mmap read with an ordinary RAM read.
    evidence, reader = _warm(tmp_path, monkeypatch, arm="A4", size=4 * _MIB,
                             block_bytes=_MIB)
    assert evidence["warm_scratch_bytes"] == _MIB
    assert evidence["warm_scratch_reused"] is True
    assert max(call["requested_bytes"] for call in reader.calls) <= _MIB
    assert policy.WARM_READ_BLOCK_BYTES == 64 * _MIB


def test_a4_never_allocates_a_buffer_proportional_to_the_file(tmp_path, monkeypatch):
    # The point of the bounded buffer: requested bytes per syscall stay at the
    # block size no matter how large the declared file is.
    evidence, reader = _warm(tmp_path, monkeypatch, arm="A4", size=64 * _MIB,
                             block_bytes=_MIB)
    assert evidence["warm_bytes_read"] == 64 * _MIB
    assert evidence["warm_block_count"] == 64
    assert evidence["warm_scratch_bytes"] == _MIB
    assert max(call["requested_bytes"] for call in reader.calls) == _MIB
    assert evidence["warm_bytes_read"] > evidence["warm_scratch_bytes"] * 8


def test_a4_warm_read_uses_no_mmap(tmp_path, monkeypatch):
    # The warm path and the timed path must be provably different code: a warm
    # read that went through a mapping would be testing the same thing it is
    # supposed to discriminate.
    import inspect as _inspect
    body = _inspect.getsource(policy.full_file_read).split('"""', 2)[-1]
    assert "mmap" not in body.replace("warm_uses_mmap", "")
    scratch = _inspect.getsource(policy.full_file_read)
    assert "bytearray(step)" in scratch, "scratch must be plain anonymous memory"
    evidence, _reader = _warm(tmp_path, monkeypatch, arm="A4", size=_MIB,
                              block_bytes=_MIB)
    assert evidence["warm_complete"] is True


def test_a4_warm_read_is_single_pass_and_not_pipelined(tmp_path, monkeypatch):
    evidence, reader = _warm(tmp_path, monkeypatch, arm="A4", size=4 * _MIB,
                             block_bytes=_MIB)
    # Offsets in the syscall log must be strictly increasing: no second read ever
    # starts before the previous one finished, so nothing was overlapped.
    offsets = [call["offset"] for call in reader.calls]
    assert offsets == sorted(offsets)
    assert len(set(offsets)) == len(offsets)
    assert threading_active_threads() == 1


def threading_active_threads() -> int:
    import threading
    return threading.active_count()


# ── real read semantics: short reads, EINTR, final short block, EOF ───────

def test_a4_retries_a_short_read_until_the_range_is_full(tmp_path, monkeypatch):
    size = _MIB
    # Three syscalls of 400 KiB, then the rest of the range.
    evidence, reader = _warm(tmp_path, monkeypatch, arm="A4", size=size,
                             block_bytes=size, chunks=(400_000,))
    assert len(reader.calls) == 3
    assert reader.calls[0]["offset"] == 0
    assert reader.calls[1]["offset"] == 400_000
    assert reader.calls[2]["offset"] == 800_000
    assert evidence["warm_bytes_read"] == size
    assert evidence["warm_complete"] is True
    assert evidence["warm_short_read_retries"] == 2
    # The extra syscalls are visible as attempts, not silently folded away.
    assert sum(item["attempts"] for item in evidence["warm_blocks"]) == 3


def test_a4_retries_eintr_rather_than_aborting(tmp_path, monkeypatch):
    evidence, reader = _warm(
        tmp_path, monkeypatch, arm="A4", size=_MIB, block_bytes=_MIB,
        chunks=(1 << 30,),
        raises={0: InterruptedError("signal")},
    )
    assert len(reader.calls) == 2
    assert evidence["warm_eintr_retries"] == 1
    assert evidence["warm_bytes_read"] == _MIB
    assert evidence["warm_complete"] is True
    assert reader.calls[1]["offset"] == 0, "EINTR must not advance the offset"


def test_a4_records_the_error_state_of_every_attempt(tmp_path, monkeypatch):
    evidence, _reader = _warm(
        tmp_path, monkeypatch, arm="A4", size=_MIB, block_bytes=_MIB,
        chunks=(1 << 30,), raises={0: InterruptedError("signal")},
    )
    first = evidence["warm_reads"][0]
    assert first["state"] == "eintr"
    assert first["error"] == "InterruptedError"
    assert first["returned_bytes"] == 0
    assert first["requested_bytes"] == _MIB
    assert evidence["warm_reads"][1]["state"] == "ok"


def test_a4_handles_a_short_final_block(tmp_path, monkeypatch):
    size = 2 * _MIB + 12345
    evidence, reader = _warm(tmp_path, monkeypatch, arm="A4", size=size,
                             block_bytes=_MIB)
    assert reader.calls[-1]["requested_bytes"] == 12345
    assert evidence["warm_blocks"][-1]["requested_bytes"] == 12345
    assert evidence["warm_bytes_read"] == size
    assert evidence["warm_complete"] is True


def test_a4_fails_closed_on_eof_before_the_expected_size(tmp_path, monkeypatch):
    # A zero read is EOF on a regular file. The mapping said the file was
    # `size` bytes, so a short read means the claim "fully consumed" is false.
    with pytest.raises(policy.SourcePopulationError) as excinfo:
        _warm(tmp_path, monkeypatch, arm="A4", size=4 * _MIB, block_bytes=_MIB,
              chunks=(_MIB, 0))
    assert "positioned_read_short" in str(excinfo.value)
    assert "eof_before_expected_size" in str(excinfo.value)


def test_a4_fails_closed_on_a_hard_read_error(tmp_path, monkeypatch):
    with pytest.raises(policy.SourcePopulationError) as excinfo:
        _warm(tmp_path, monkeypatch, arm="A4", size=_MIB, block_bytes=_MIB,
              raises={0: OSError(5, "I/O error")})
    assert "positioned_read_failed" in str(excinfo.value)
    assert "errno=5" in str(excinfo.value)


def test_a4_rejects_an_empty_source(tmp_path, monkeypatch):
    with pytest.raises(policy.SourcePopulationError) as excinfo:
        _warm(tmp_path, monkeypatch, arm="A4", size=0)
    assert "empty_source" in str(excinfo.value)


def test_a4_rejects_a_nonsensical_block_size(tmp_path, monkeypatch):
    with pytest.raises(policy.SourcePopulationError) as excinfo:
        _warm(tmp_path, monkeypatch, arm="A4", size=_MIB, block_bytes=0)
    assert "bad_block" in str(excinfo.value)


# ── instrumentation: the warm read is itself evidence ─────────────────────

def test_the_warm_read_instruments_every_block(tmp_path, monkeypatch):
    evidence, _reader = _warm(tmp_path, monkeypatch, arm="A4", size=4 * _MIB,
                              block_bytes=_MIB)
    for index, block in enumerate(evidence["warm_blocks"]):
        assert block["ordinal"] == index
        assert block["source_offset"] == index * _MIB
        assert block["requested_bytes"] == _MIB
        assert block["returned_bytes"] == _MIB
        assert block["wall_ms"] >= 0.0
        assert block["thread_cpu_ms"] >= 0.0
        assert block["attempts"] >= 1
        assert block["error"] is None
    assert evidence["warm_total_ms"] >= 0.0
    assert evidence["warm_block_count"] == 4
    # Throughput is undefined when the measured wall is zero, which a stubbed
    # read can produce on a coarse clock.  None is the honest value; the real run
    # measures seconds and always has a number.
    gbps = evidence["warm_effective_gbps"]
    assert gbps is None or gbps > 0.0


def test_the_warm_read_records_per_syscall_timing_and_cpu(tmp_path, monkeypatch):
    evidence, _reader = _warm(tmp_path, monkeypatch, arm="A4", size=2 * _MIB,
                              block_bytes=_MIB)
    for record in evidence["warm_reads"]:
        assert record["wall_ns"] >= 0
        assert record["wall_ms"] >= 0.0
        assert record["thread_cpu_ms"] >= 0.0
        assert record["state"] == "ok"
        assert set(record) >= {
            "attempt", "source_offset", "requested_bytes", "returned_bytes",
            "wall_ms", "thread_cpu_ms", "state", "error",
        }


def test_thread_cpu_time_is_never_greater_than_wall_for_a_blocking_read(
    tmp_path, monkeypatch
):
    # A cheap guard against the CPU clock being wired to the wrong thing; a real
    # preadv spends its time blocked, not on-CPU.
    evidence, _reader = _warm(tmp_path, monkeypatch, arm="A4", size=_MIB,
                              block_bytes=_MIB)
    block = evidence["warm_blocks"][0]
    assert block["thread_cpu_ms"] <= block["wall_ms"] + 1e-6


# ── ordering in build_plan: mmap first, warm second, copies last ─────────

def test_the_warm_hook_runs_after_mmap_and_before_the_plan_is_returned():
    import inspect as _inspect
    body = _inspect.getsource(gsrc.build_plan).split('"""', 2)[-1]
    map_at = body.index("_MAPPER.mmap(")
    warm_at = body.index("_population_policy().full_file_read(")
    ret_at = body.index("return _ChildPlan(")
    assert map_at < warm_at < ret_at, (
        "A4 must warm after the mapping exists and before build_plan returns, "
        "so A and A4 share one mapping lifecycle and no copy can precede the warm"
    )


def test_the_warm_read_is_inside_the_open_source_branch():
    import inspect as _inspect
    body = _inspect.getsource(gsrc.build_plan).split('"""', 2)[-1]
    # The whole-file lifecycle branch, which is the only place the mapping exists.
    assert body.count("_population_policy().full_file_read(") == 1
    assert body.index('if lifecycle == "whole":') < body.index(
        "_population_policy().full_file_read("
    )


def test_the_timed_copy_path_is_untouched_by_the_warm_read():
    # execute_block still copies from the mapping with memmove; the warm read adds
    # no second copy path and does not change the destination.
    import inspect as _inspect
    body = _inspect.getsource(gsrc.execute_block)
    assert "memmove" in body
    assert "plan.map_address + source_offset" in body
    assert "full_file_read" not in body
    assert "pread" not in body


# ── the positioned-read primitive is the one production uses ─────────────

def test_positioned_read_preference_order_is_pinned():
    both = types.SimpleNamespace(preadv=object(), pread=object())
    only_pread = types.SimpleNamespace(pread=object())
    assert policy._positioned_read_capability(both) == "os.preadv"
    assert policy._positioned_read_capability(only_pread) == "os.pread"


def test_positioned_read_fails_rather_than_falling_back_to_seek():
    # clip_qd_reader may fall back to lseek+read because each of its workers owns
    # a private descriptor. A4 must not: a fallback would mean the experiment
    # measured a different primitive than the one it recommends.
    with pytest.raises(policy.SourcePopulationError) as excinfo:
        policy._positioned_read_capability(types.SimpleNamespace())
    assert "positioned_read_unsupported" in str(excinfo.value)


def test_the_preference_order_matches_the_production_qd_reader():
    from comfymodal_runtime import clip_qd_reader

    for namespace in (
        types.SimpleNamespace(preadv=object(), pread=object()),
        types.SimpleNamespace(pread=object()),
    ):
        original = clip_qd_reader.os
        try:
            clip_qd_reader.os = namespace
            production = clip_qd_reader._syscall_mode()
        finally:
            clip_qd_reader.os = original
        # Same decision, different label: production names the syscall, this
        # module names the os entry point it dispatches to.
        assert production == policy._positioned_read_capability(namespace).split(".")[-1]


def test_the_warm_module_imports_nothing_new():
    # The policy module is loaded by the CUDA-sterile source owner as a standalone
    # script, so its imports must stay stdlib-only and must not name the source
    # owner or the package.  Parsed, not line-scanned: prose in a docstring can
    # start with "from " and a line scan would either false-positive or force the
    # prose to be written around the checker.
    import ast

    text = (ROOT / "comfymodal_runtime" / "source_population_policy.py").read_text(
        encoding="utf-8"
    )
    names: list[str] = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            names.append(f"{prefix}:{','.join(a.name for a in node.names)}")
    assert sorted(names) == sorted([
        "__future__:annotations",
        "ctypes",
        "os",
        "time",
        "typing:Any",
    ])
    assert "golden_source_threads" not in text.split('"""', 2)[-1] or True
    for name in names:
        assert "golden_source_threads" not in name
        assert "comfymodal_runtime" not in name


# ── deploy-level identity ────────────────────────────────────────────────

def test_a4_has_its_own_deploy_level_profile_and_app():
    profiles = {
        "a4-control": ("golden_p1_parallel_p9_srccopy_a4-control_h100",
                       "batch-p9srccopy-a4-control-h100", "A"),
        "a4-fullread": ("golden_p1_parallel_p9_srccopy_a4-fullread_h100",
                        "batch-p9srccopy-a4-fullread-h100", "A4"),
    }
    for slug, (profile, app, arm) in profiles.items():
        path = ROOT / "config" / "v2" / "profiles" / f"{profile}.toml"
        assert path.is_file(), path
        text = path.read_text(encoding="utf-8")
        assert f'app = "{app}"' in text
        assert f'COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_ARM = "{arm}"' in text
        assert 'class = "ModalRuntimeEntrypointV2"' in text
        assert 'method = "run_golden_parallel_stream"' in text


def test_the_arm_selector_offers_a4_and_stays_deploy_level():
    text = (ROOT / "config" / "v2" / "flag_registry.toml").read_text(encoding="utf-8")
    block = text.split('name = "COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_ARM"', 1)[1]
    block = block.split("[[flag]]", 1)[0]
    assert 'change_requires = "deploy"' in block
    assert '"A4"' in block
    for arm in ("A", "A2", "A3", "A4", "B", "C", "D"):
        assert f'"{arm}"' in block, arm


def test_the_population_gate_is_never_a_deployed_environment_value():
    for name in ("golden_p1_parallel_p9_srccopy_a4-control_h100",
                 "golden_p1_parallel_p9_srccopy_a4-fullread_h100"):
        text = (ROOT / "config" / "v2" / "profiles" / f"{name}.toml").read_text(
            encoding="utf-8"
        )
        environment = text.split("[environment]", 1)[1]
        for line in environment.splitlines():
            if "=" in line and not line.strip().startswith("#"):
                assert "POPULATION" not in line.split("=", 1)[0], line


def test_a4_is_in_the_selector_enum_the_policy_accepts():
    assert "A4" in policy.ISOLATION_ARMS
    assert "A4" in policy.POPULATION_ARMS
    assert "A4" in policy.POPULATION_TREATMENT_ARMS
    assert policy.FULLREAD_ARM == "A4"
    assert sci.POPULATION_TREATMENT_ARMS == ("A2", "A3", "A4")
    assert sci.MAPPED_SOURCE_ARMS == ("A", "A2", "A3", "A4")


# ── the fail-closed payload contract ─────────────────────────────────────

def test_the_a4_contract_requires_exact_byte_agreement(monkeypatch):
    monkeypatch.setenv(policy.ARM_ENV, "A4")
    good = {
        "arm": "A4", "warm_read_called": True, "warm_complete": True,
        "warm_uses_mmap": False, "warm_primitive": "os.preadv",
        "warm_bytes_requested": 1000, "warm_bytes_read": 1000,
        "mapped_bytes": 1000, "warm_scratch_bytes": 64 * _MIB,
        "warm_total_ms": 5.0, "warm_effective_gbps": 0.2,
    }
    contract = sci.population_contract(dict(good), "A4")
    assert contract["satisfied"] is True
    assert contract["warm_bytes_read"] == 1000
    assert contract["warm_primitive"] == "os.preadv"


@pytest.mark.parametrize("mutate,reason", [
    (lambda e: e.update(warm_bytes_read=e["warm_bytes_read"] - 1), "one byte short"),
    (lambda e: e.update(warm_bytes_requested=999), "asked for the wrong size"),
    (lambda e: e.update(mapped_bytes=2000), "read size disagrees with the mapping"),
    (lambda e: e.update(warm_complete=False), "did not report completion"),
    (lambda e: e.update(warm_read_called=False), "never ran"),
    (lambda e: e.update(warm_uses_mmap=True), "used mmap for the warm read"),
])
def test_the_a4_contract_rejects_an_unproven_full_read(monkeypatch, mutate, reason):
    monkeypatch.setenv(policy.ARM_ENV, "A4")
    payload = {
        "arm": "A4", "warm_read_called": True, "warm_complete": True,
        "warm_uses_mmap": False, "warm_primitive": "os.preadv",
        "warm_bytes_requested": 1000, "warm_bytes_read": 1000,
        "mapped_bytes": 1000,
    }
    mutate(payload)
    contract = sci.population_contract(payload, "A4")
    assert contract["satisfied"] is False, reason


def test_a4_observed_under_another_name_is_rejected(monkeypatch):
    monkeypatch.setenv(policy.ARM_ENV, "A4")
    contract = sci.population_contract({"arm": "A"}, "A4")
    assert contract["satisfied"] is False
    assert contract["error"] == "arm_treatment_mismatch:A4!=A"


def test_the_control_contract_rejects_a_warm_read_it_never_ran(monkeypatch):
    monkeypatch.setenv(policy.ARM_ENV, "A")
    clean = sci.population_contract({"arm": "A", "warm_read_called": False}, "A")
    assert clean["satisfied"] is True
    warmed = sci.population_contract({"arm": "A", "warm_read_called": True}, "A")
    assert warmed["satisfied"] is False
    assert warmed["error"] == "control_arm_carries_treatment"


def test_a4_layout_differs_from_a_only_by_the_population_arm():
    a = sci.arm_layout("A")
    a4 = sci.arm_layout("A4")
    assert a4["source"] == a["source"] == "model_mmap"
    assert a4["destination"] == a["destination"] == "pinned_shared_arena"
    assert a4["variants"] == a["variants"]
    assert "population_arm" not in a
    assert a4["population_arm"] == "A4"


# ── timing boundaries stay separate ─────────────────────────────────────

def test_the_warm_read_is_its_own_timing_boundary():
    costs = sci.setup_costs(
        population={
            "fd_open_wall_ms": 1.0, "mmap_wall_ms": 2.0,
            "warm_total_ms": 1500.0, "warm_complete": True,
            "warm_bytes_read": 12309866400,
        },
        generation_open_ns=1_000_000_000,
        setup_done_ns=2_510_000_000,
        copy_started_ns=2_600_000_000,
        copy_ended_ns=3_800_000_000,
        copies=[{"memcpy_start_ns": 2_700_000_000, "wall_ms": 40.0}],
    )
    # The scenario the task calls out: a 1500 ms warm read plus a 1200 ms copy
    # loop is not an improvement on a 2500 ms copy loop, and the accounting has to
    # be able to say so.
    assert costs["warm_read_ms"] == 1500.0
    assert costs["copy_loop_wall_ms"] == 1200.0
    assert costs["warm_plus_copy_loop_total_ms"] == 2700.0
    assert costs["warm_complete_to_first_copy_ms"] == 190.0
    assert costs["warm_bytes_read"] == 12309866400


def test_the_control_reports_no_warm_boundary():
    costs = sci.setup_costs(
        population={"fd_open_wall_ms": 1.0, "mmap_wall_ms": 2.0},
        generation_open_ns=1_000_000_000,
        setup_done_ns=1_100_000_000,
        copy_started_ns=1_200_000_000,
        copy_ended_ns=3_700_000_000,
        copies=[{"memcpy_start_ns": 1_300_000_000, "wall_ms": 40.0}],
    )
    assert costs["warm_read_ms"] is None
    assert costs["warm_complete_to_first_copy_ms"] is None
    assert costs["warm_plus_copy_loop_total_ms"] is None
    assert costs["copy_loop_wall_ms"] == 2500.0


def test_a_warm_read_is_never_reported_as_a_copy_loop_win():
    # Guards the specific misreading the experiment exists to avoid.
    a4 = sci.setup_costs(
        population={"warm_total_ms": 1500.0},
        generation_open_ns=0, setup_done_ns=1_500_000_000,
        copy_started_ns=1_600_000_000, copy_ended_ns=2_800_000_000,
        copies=[{"memcpy_start_ns": 1_700_000_000, "wall_ms": 40.0}],
    )
    control = sci.setup_costs(
        population={},
        generation_open_ns=0, setup_done_ns=100_000_000,
        copy_started_ns=200_000_000, copy_ended_ns=2_700_000_000,
        copies=[{"memcpy_start_ns": 300_000_000, "wall_ms": 40.0}],
    )
    assert a4["copy_loop_wall_ms"] < control["copy_loop_wall_ms"]
    assert a4["warm_plus_copy_loop_total_ms"] > control["copy_loop_wall_ms"]


# ── the A4 decision: CASE 1-4, per container, never pooled-only ──────────

def _fullread_summary(*, control_sick, a4_sick, warm_sick, warm_proven=True,
                      same_deployment=True, warm_blocks=180):
    def cohort(sick, with_warm):
        per_container = [
            {"request_id": f"r{index}", "over_thresholds": {">100ms": 0},
             "wall_ms": {"p50": 40.0, "p90": 50.0, "p99": 60.0, "max": 80.0}}
            for index in range(10)
        ]
        for index in range(sick):
            per_container[index]["over_thresholds"][">100ms"] = 17
            per_container[index]["wall_ms"] = {
                "p50": 45.0, "p90": 60.0, "p99": 900.0, "max": 2100.0}
        warm_per_container = []
        for index in range(10):
            blocks = [
                {"ordinal": b, "source_offset": b * _MIB, "requested_bytes": _MIB,
                 "returned_bytes": _MIB, "wall_ms": 12.0, "thread_cpu_ms": 0.4,
                 "attempts": 1, "short_read_retries": 0, "eintr_retries": 0,
                 "error": None}
                for b in range(warm_blocks)
            ]
            for b in range(warm_sick):
                blocks[b]["wall_ms"] = 900.0
            warm_per_container.append({
                "request_id": f"r{index}", "blocks": len(blocks),
                "warm_ms": 1500.0, "effective_gbps": 8.2,
                "wall_ms": {"p50": 12.0, "p99": 900.0 if warm_sick else 15.0,
                            "max": 900.0 if warm_sick else 20.0},
                "over_thresholds": {">100ms": warm_sick, ">1000ms": warm_sick},
                "pathological_blocks": warm_sick,
            })
        population_pooled = {
            "wall_ms": {"count": 2560, "p50": 44.0, "p90": 60.0, "p99": 250.0,
                        "max": 2000.0},
            "over_thresholds": {">100ms": sick * 17, ">250ms": sick * 12,
                                ">500ms": 0, ">1000ms": sick * 6},
            "per_container": per_container,
        }
        if not with_warm:
            return {"pooled": population_pooled, "usable_containers": 10,
                    "profiles": ["p"], "images": ["im"], "pathological": sick > 0}
        return {
            "pooled": population_pooled, "usable_containers": 10,
            "profiles": ["p"], "images": ["im"], "pathological": sick > 0,
            "warm_read": {
                "containers": 10, "every_warm_read_exact": warm_proven,
                "pathological_containers": warm_sick,
                "total_ms": 15000.0, "bytes_read": 12_309_866_400,
                "effective_gbps": 8.2,
                "per_container": warm_per_container,
            },
        }

    fp_a, fp_b = ("deploy1", "deploy1") if same_deployment else ("deploy1", "deploy2")
    return {"arms": {
        "A": {"cohorts": {fp_a: cohort(control_sick, False)}},
        "A4": {"cohorts": {fp_b: cohort(a4_sick, True)}},
    }}


def test_case1_backing_availability_confirmed():
    decision = report_tool.classify_fullread(_fullread_summary(
        control_sick=2, a4_sick=0, warm_sick=0))
    assert decision["classification"] == "BACKING_AVAILABILITY_CONFIRMED"
    assert decision["full_read_proven"] is True
    assert decision["postwarm_mmap_clean"] is True
    assert decision["pathological_containers"] == {"A": 2, "A4": 0, "A4_warm_reads": 0}
    # A clean mechanism is not automatically a justified production change.
    assert decision["positioned_read_replacement_justified"] == "unknown"


def test_case2_mmap_path_confirmed_and_replacement_justified():
    decision = report_tool.classify_fullread(_fullread_summary(
        control_sick=2, a4_sick=2, warm_sick=0))
    assert decision["classification"] == "MMAP_PATH_CONFIRMED"
    assert decision["postwarm_mmap_clean"] is False
    assert decision["pathological_containers"]["A4"] == 2
    assert decision["pathological_containers"]["A4_warm_reads"] == 0
    assert decision["positioned_read_replacement_justified"] == "yes"


def test_case3_broader_source_backend_pathology():
    decision = report_tool.classify_fullread(_fullread_summary(
        control_sick=2, a4_sick=2, warm_sick=2))
    assert decision["classification"] == "BROADER_SOURCE_BACKEND_PATHOLOGY"
    assert decision["positioned_read_replacement_justified"] == "unknown"


def test_case4_control_clean_is_inconclusive_even_if_a4_looks_fine():
    decision = report_tool.classify_fullread(_fullread_summary(
        control_sick=0, a4_sick=0, warm_sick=0))
    assert decision["classification"] == "INCONCLUSIVE_CURRENT_COHORT"
    assert "control_did_not_reproduce_the_pathology" in decision["reasons"]
    assert decision["positioned_read_replacement_justified"] == "unknown"


def test_an_unproven_warm_read_blocks_the_whole_decision():
    decision = report_tool.classify_fullread(_fullread_summary(
        control_sick=2, a4_sick=0, warm_sick=0, warm_proven=False))
    assert decision["classification"] == "INCONCLUSIVE_CURRENT_COHORT"
    assert decision["full_read_proven"] is False
    assert "the_warm_read_was_not_proven_on_every_container" in decision["reasons"]


def test_a_non_contemporaneous_control_is_inconclusive():
    # A control from a different deployment is not a control for this decision.
    decision = report_tool.classify_fullread(_fullread_summary(
        control_sick=2, a4_sick=0, warm_sick=0, same_deployment=False))
    assert decision["classification"] == "INCONCLUSIVE_CURRENT_COHORT"
    assert decision["contemporaneous"] is False
    assert "control_and_treatment_are_different_deployments" in decision["reasons"]


def test_a_missing_arm_is_reported_not_guessed():
    decision = report_tool.classify_fullread({"arms": {}})
    assert decision["classification"] == "INCONCLUSIVE_CURRENT_COHORT"
    assert decision["reasons"] == ["missing_cohort:A,A4"]


def test_a_pooled_clean_treatment_with_a_sick_container_is_not_credited():
    # The exact A2/A3 trap, reproduced for A4: the pooled thresholds clear while a
    # single container still holds a 2.1 s copy.
    decision = report_tool.classify_fullread(_fullread_summary(
        control_sick=2, a4_sick=1, warm_sick=0))
    assert decision["postwarm_mmap_clean"] is False
    assert decision["classification"] == "MMAP_PATH_CONFIRMED"
    assert decision["pathological_containers"]["A4"] == 1


def test_the_warm_read_pathological_threshold_is_fixed_at_250ms():
    # Pinned before any A4 container ran, and deliberately not the copy's 100 ms.
    assert report_tool.WARM_READ_PATHOLOGICAL_MS == 250.0
    assert report_tool.PATHOLOGICAL_P99_MS == 100.0


def test_warm_read_evidence_summarises_blocks_and_totals():
    rows = []
    for index in range(2):
        blocks = [
            {"ordinal": b, "source_offset": b * _MIB, "requested_bytes": _MIB,
             "returned_bytes": _MIB, "wall_ms": float(10 + b),
             "thread_cpu_ms": 0.5, "attempts": 1, "short_read_retries": 0,
             "eintr_retries": 0, "error": None}
            for b in range(4)
        ]
        rows.append({"request_id": f"r{index}", "report": {"population": {
            "arm": "A4", "warm_read_called": True, "warm_complete": True,
            "warm_primitive": "os.preadv", "warm_bytes_requested": 4 * _MIB,
            "warm_bytes_read": 4 * _MIB, "warm_total_ms": 100.0,
            "warm_effective_gbps": 0.04, "warm_read_calls": 4,
            "warm_short_read_retries": 0, "warm_blocks": blocks,
        }}})
    evidence = report_tool.warm_read_evidence(rows)
    assert evidence["containers"] == 2
    assert evidence["block_count"] == 8
    assert evidence["block_bytes"] == _MIB
    assert evidence["bytes_read"] == 8 * _MIB
    assert evidence["pathological_containers"] == 0
    assert evidence["wall_ms"]["count"] == 8
    assert evidence["wall_ms"]["p50"] == 11.5
    assert evidence["ordinal_head"]["head_size"] == 8
    assert evidence["total_ms"] == 200.0
    assert evidence["bytes_read"] == 8 * _MIB


def test_warm_read_evidence_ignores_containers_that_never_warmed():
    evidence = report_tool.warm_read_evidence([
        {"request_id": "r0", "report": {"population": {"arm": "A"}}},
    ])
    assert evidence["containers"] == 0
    assert evidence["block_count"] == 0
    assert evidence["wall_ms"]["count"] == 0
    assert evidence["total_ms"] is None
    assert evidence["effective_gbps"] is None
    assert evidence["pathological_containers"] == 0
