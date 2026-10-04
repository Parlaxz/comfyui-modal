"""Opt-in source population policy for the mapped 64 MiB copy path.

The A/B/C/D source-copy isolation experiment established ``SOURCE_SIDE``: the
pathological 64 MiB ``libc.memmove`` needs the whole-file ``MAP_PRIVATE``
mapping of the Volume-backed checkpoint, and is completely absent when the
source is resident anonymous RAM. The pinned arena was exonerated.

That narrows the remaining question to two families:

    (a) the backing pages are not sufficiently materialised before each copy, in
        which case asking the Volume to stage the file
        (``posix_fadvise(POSIX_FADV_WILLNEED)``, once per generation) or forcing
        population inside the mapping syscall (``MAP_POPULATE``) removes the
        tail;
    (b) the mapped-page access path itself is slow in this environment, in which
        case neither does and the read primitive has to change.

A2 and A3 answered neither.  Measured on Modal through this Volume, ``WILLNEED``
returned in 0.040 ms and ``mmap(MAP_POPULATE)`` returned in 0.774 ms for a
12.31 GB file.  Both were accepted and neither materialised anything, so they
tested whether the platform honours the request, not whether materialising the
backing data fixes the copy.  ``A4`` (:func:`full_file_read`) removes the
platform from the experiment by consuming every byte through an ordinary
positioned read before any copy is timed, which is the only way to separate (a)
from (b) here.

This module is the one place that decides, and it is deliberately inert by
default:

* the gate ``COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_POPULATION`` must be set
  before any call here does anything at all;
* the arm comes from ``COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_ARM``, which is
  a DEPLOY-baked flag, so the arm cannot be requested differently from what was
  deployed;
* with the gate off, or with arm ``A``, :func:`fadvise_willneed` is not called
  and :func:`mapping_flags` returns the caller's flags unchanged.  That is one
  boolean test per generation and one integer compare per mapping, and it is the
  production path byte-for-byte.

Both actions fail closed.  If the experiment selects ``A2`` or ``A3`` and the
corresponding action did not actually happen -- ``posix_fadvise`` returned
non-zero, or the mapping was not created with ``MAP_POPULATE`` -- the caller
raises :class:`SourcePopulationError` rather than continuing with an arm that
does not match its name.  A named arm that silently did not happen is the
failure mode that produced fifteen wrong containers in the previous phase.

This module is standard-library only and has no import of
``golden_source_threads``, because ``golden_source_threads`` is launched as a
standalone ``__main__`` script in the CUDA-sterile source owner and a module
level relative import there raises with no parent package.
"""

from __future__ import annotations

import ctypes
import os
import time
from typing import Any

# Process-local gate.  Deliberately NOT part of the deployed container
# environment: the real Golden source owner is a separate process spawned later
# in the same container, and MAP_POPULATE on a 12 GiB mapping next to a 1 GiB
# pinned arena in a 24 GiB container is a real OOM risk.  Scoping the treatment
# to the experiment's own mapping keeps the primary discriminator clean and keeps
# the subsequent real Golden request an untreated control.
POPULATION_GATE_ENV = "COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_POPULATION"
ARM_ENV = "COMFYMODAL_GOLDEN_SOURCE_COPY_ISOLATION_ARM"

CONTROL_ARM = "A"
WILLNEED_ARM = "A2"
POPULATE_ARM = "A3"
FULLREAD_ARM = "A4"
POPULATION_ARMS = (CONTROL_ARM, WILLNEED_ARM, POPULATE_ARM, FULLREAD_ARM)
# The arms that carry a population treatment at all.  ``A`` is the untreated
# control that shares the mapped source with them.
POPULATION_TREATMENT_ARMS = (WILLNEED_ARM, POPULATE_ARM, FULLREAD_ARM)
# Every arm the isolation selector accepts, mirrored from the registry enum.  The
# prior B/C/D arms carry no population arm and must stay runnable.
ISOLATION_ARMS = ("A", "A2", "A3", "A4", "B", "C", "D")

# Linux mmap / fadvise constants, spelled out rather than imported so the values
# the experiment asserts on are visible in one place.
PROT_READ = 1
MAP_PRIVATE = 2
MAP_ANONYMOUS = 0x20
MAP_POPULATE = 0x8000
POSIX_FADV_WILLNEED = 3

# A4's warm read.  One 64 MiB scratch buffer, reused for every positioned read:
# a 12.31 GB anonymous copy would not fit beside the 1 GiB pinned arena in a
# 24 GiB container, and would also stop being a diagnostic by becoming the thing
# being measured.
WARM_READ_BLOCK_BYTES = 64 * 1024 * 1024

_TRUE = {"1", "true", "yes", "on"}


class SourcePopulationError(RuntimeError):
    """A declared population arm did not happen. Callers must fail closed."""


def population_enabled(value: Any = None) -> bool:
    selected = os.environ.get(POPULATION_GATE_ENV) if value is None else value
    return str(selected or "").strip().lower() in _TRUE


def declared_arm(value: Any = None) -> str:
    """The arm the deployment asked for, validated even when gated off.

    Validated unconditionally so a typo is a hard error instead of a silent
    "treated this as the control".

    The accepted set is the whole isolation arm selector, not just the arms that
    carry a population treatment: ``B``/``C``/``D`` deploy with this same
    selector and have no population arm at all, so rejecting them here would make
    those already-completed arms unrunnable.  What a non-population arm means is
    decided by the caller, which knows the arm's layout; ``active_arm`` below maps
    every one of them onto the untreated control.
    """
    selected = os.environ.get(ARM_ENV, CONTROL_ARM) if value is None else value
    arm = str(selected or "").strip().upper()
    if not arm or not all(character.isalnum() for character in arm):
        raise SourcePopulationError(f"unsupported_source_population_arm:{selected!r}")
    if arm not in ISOLATION_ARMS:
        raise SourcePopulationError(f"unsupported_source_population_arm:{selected!r}")
    return arm


def active_arm(value: Any = None) -> str:
    """The population arm this address space will actually apply.

    Returns ``"A"`` unless the gate is up *and* the deployment declares a
    treatment arm, so a gate-off address space is always the untreated control.

    The gate-off-with-A2-declared case must NOT raise, and that is not a
    relaxation. The gate is process-local on purpose, so the experiment's own
    ``build_plan`` runs treated and then the real Golden source owner -- a
    different process in the same container, with the gate popped -- runs
    untreated. Raising here killed the real CLIP load of an otherwise perfect
    A2 request with
    ``source_population_arm_requires_gate:A2``.

    A treated arm that silently ran as the control is still caught, one layer up
    and with better evidence: ``source_copy_isolation.population_contract``
    compares the declared arm against the arm the payload actually recorded and
    rejects the mismatch. That check is scoped to the experiment's own mapping,
    which is where the claim "this arm was treated" actually has to be proven.
    """
    arm = declared_arm(value)
    if arm not in POPULATION_TREATMENT_ARMS:
        return CONTROL_ARM
    if not population_enabled():
        return CONTROL_ARM
    return arm


def _libc() -> Any:
    """The C library, or a clean failure the caller can turn into an error.

    ``CDLL(None)`` is the process symbol table on POSIX.  It is not portable:
    CPython 3.11 on Windows raises ``TypeError`` from ``CDLL(None)`` before it
    ever reaches the handle, so the platform C runtime is tried as well.  A
    failure here is never silent -- the caller raises
    :class:`SourcePopulationError`, because an arm that cannot perform its own
    treatment is not that arm.
    """
    if os.name == "posix":
        candidates = (None,)
    else:
        candidates = (None, "msvcrt")
    last: Exception | None = None
    for name in candidates:
        try:
            return ctypes.CDLL(name, use_errno=True)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            last = exc
    raise SourcePopulationError(f"libc_unavailable:{type(last).__name__}")


def fadvise_willneed(fd: int, *, generation: int, arm: str | None = None) -> dict[str, Any]:
    """One ``posix_fadvise(POSIX_FADV_WILLNEED)`` over the whole descriptor.

    Called once per model generation, on the same persistent descriptor that is
    about to be mapped, before the mapping is consumed.  Not per block, with no
    polling loop, no sleep and no artificial wait for prefetched pages: the
    experiment must measure what the syscall costs, not a scheduler's idea of how
    long prefetching ought to take.
    """
    selected = active_arm(arm)
    if selected != WILLNEED_ARM:
        return {
            "arm": selected,
            "fadvise_called": False,
            "fadvise_call_count": 0,
            "reason": "control_arm",
        }
    libc = _libc()
    if not hasattr(libc, "posix_fadvise"):
        # Fail closed rather than downgrade to the control: an arm that cannot
        # perform its own treatment is not that arm.
        raise SourcePopulationError(
            f"posix_fadvise_unavailable:{WILLNEED_ARM}:generation={generation}"
        )
    libc.posix_fadvise.argtypes = [
        ctypes.c_int, ctypes.c_longlong, ctypes.c_longlong, ctypes.c_int,
    ]
    libc.posix_fadvise.restype = ctypes.c_int
    started_ns = time.monotonic_ns()
    rc = int(libc.posix_fadvise(int(fd), ctypes.c_longlong(0), ctypes.c_longlong(0),
                                POSIX_FADV_WILLNEED))
    wall_ns = max(0, time.monotonic_ns() - started_ns)
    errno_value = ctypes.get_errno() if rc != 0 else None
    evidence = {
        "arm": selected,
        "generation": int(generation),
        "fd": int(fd),
        "fadvise_called": True,
        "fadvise_call_count": 1,
        "fadvise_advice": POSIX_FADV_WILLNEED,
        "fadvise_offset": 0,
        "fadvise_length": 0,
        "fadvise_return_code": rc,
        "fadvise_errno": errno_value,
        "fadvise_wall_ms": round(wall_ns / 1e6, 4),
        "fadvise_wall_ns": wall_ns,
    }
    if rc != 0:
        raise SourcePopulationError(
            f"posix_fadvise_willneed_failed:rc={rc}:errno={errno_value}:"
            f"generation={generation}"
        )
    return evidence


def mapping_flags(
    base_flags: int, *, arm: str | None = None
) -> tuple[int, dict[str, Any]]:
    """``MAP_PRIVATE``, plus ``MAP_POPULATE`` for arm A3 and nothing else.

    The base flags are whatever the caller passed; A3 adds exactly one bit.  The
    returned evidence records the numeric flags so the payload can prove which
    mapping was actually requested rather than asserting a name.
    """
    selected = active_arm(arm)
    base = int(base_flags)
    if selected != POPULATE_ARM:
        return base, {
            "arm": selected,
            "mmap_flags": base,
            "map_populate_requested": False,
            "map_populate_in_flags": bool(base & MAP_POPULATE),
        }
    flags = base | MAP_POPULATE
    return flags, {
        "arm": selected,
        "mmap_flags": flags,
        "mmap_flags_base": base,
        "map_populate_bit": MAP_POPULATE,
        "map_populate_requested": True,
        "map_populate_in_flags": bool(flags & MAP_POPULATE),
    }


def confirm_mapping(populated: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    """Fail closed when the declared arm's mapping flag did not take effect.

    Called by the mapping site once ``mmap`` has returned, so "A3 ran" means the
    mapping syscall was issued with ``MAP_POPULATE`` **and** succeeded, not merely
    that the policy intended to add the bit.
    """
    arm = str(evidence.get("arm") or CONTROL_ARM)
    if arm != POPULATE_ARM:
        return evidence
    if not evidence.get("map_populate_in_flags"):
        raise SourcePopulationError("source_population_arm_without_map_populate")
    if not populated:
        raise SourcePopulationError("source_population_arm_mapping_failed")
    # What is honestly observable is that MAP_POPULATE was requested and that
    # mmap accepted it.  Whether gVisor's Sentry actually faulted the whole
    # range in is NOT observable here: the residency probe that would answer it
    # is unreliable for a file-backed mapping on a mounted Volume, so it is
    # recorded as unavailable rather than as evidence either way.
    evidence["map_populate_accepted_by_mmap"] = True
    evidence["page_population_observable"] = False
    evidence["page_population_evidence"] = "unavailable_under_gvisor_mincore"
    return evidence


def _positioned_read_capability(namespace: Any = None) -> str:
    """Which positioned-read primitive ``namespace`` offers, most-preferred first.

    The same precedence as the production fillers in
    ``golden_io_process_v2._pread`` and ``clip_qd_reader._syscall_mode``:
    ``os.preadv``, then ``os.pread``, and no seek-based fallback.  ``namespace``
    is injectable so the precedence is a behavioural test rather than a comment.

    One deliberate divergence from ``clip_qd_reader``: that module falls back to
    ``lseek``+``read`` because each of its workers owns a private descriptor.  A4
    must not, because a silent fallback would mean the warm read -- and therefore
    the recommendation the experiment exists to inform -- was measuring a
    different primitive than the one it names.
    """
    module = os if namespace is None else namespace
    if hasattr(module, "preadv"):
        return "os.preadv"
    if hasattr(module, "pread"):
        return "os.pread"
    raise SourcePopulationError("positioned_read_unsupported")


def positioned_read_primitive() -> str:
    """Which positioned-read primitive this interpreter will actually use."""
    return _positioned_read_capability()


def _pread_once(fd: int, view: Any, offset: int) -> int:
    """One positioned read attempt into ``view``.  Bytes actually read, or <=0.

    Mirrors ``golden_io_process_v2._pread``: ``preadv`` writes straight into the
    target buffer, while ``pread`` allocates and is copied in.  The caller owns
    the short-read loop, the same way the production filler does.
    """
    primitive = positioned_read_primitive()
    if primitive == "os.preadv":
        return int(os.preadv(fd, [view], int(offset)))
    data = os.pread(fd, len(view), int(offset))
    got = len(data)
    if got:
        view[:got] = data
    return got


def _fill_range(
    fd: int, buffer: Any, offset: int, length: int, records: list[dict[str, Any]],
) -> int:
    """Read exactly ``length`` bytes at ``offset``, retrying short reads.

    Appends one record per *syscall*, not per range, so a range that needed
    three attempts is visible as three attempts.  A range that cannot be filled
    raises: a warm read that quietly read less than the file is not a warm read.
    """
    total = 0
    attempt = 0
    while total < length:
        view = memoryview(buffer)[total:length]
        started_ns = time.monotonic_ns()
        cpu_started_ns = time.thread_time_ns()
        try:
            got = _pread_once(fd, view, offset + total)
            state = "ok"
            error = None
        except InterruptedError:
            # PEP 475 retries these inside CPython, so reaching here means the
            # handler asked us not to.  Count it and retry rather than abort.
            got = 0
            state = "eintr"
            error = "InterruptedError"
        except OSError as exc:
            got = 0
            state = "error"
            error = f"{type(exc).__name__}:errno={exc.errno}"
        wall_ns = max(0, time.monotonic_ns() - started_ns)
        cpu_ns = max(0, time.thread_time_ns() - cpu_started_ns)
        attempt += 1
        records.append({
            "attempt": attempt,
            "source_offset": int(offset + total),
            "requested_bytes": int(length - total),
            "returned_bytes": int(max(0, got)),
            "wall_ms": round(wall_ns / 1e6, 4),
            "wall_ns": wall_ns,
            "thread_cpu_ms": round(cpu_ns / 1e6, 4),
            "state": state,
            "error": error,
        })
        if state == "error":
            raise SourcePopulationError(
                f"positioned_read_failed:{error}:offset={offset + total}"
                f":remaining={length - total}"
            )
        if state == "eintr":
            # An interrupted syscall transferred nothing, so it must not be
            # mistaken for EOF.  Fall through to the retry without advancing.
            continue
        if got <= 0:
            # EOF, or a descriptor that will never produce more.  Either way the
            # file is not the size the mapping said it was.
            raise SourcePopulationError(
                f"positioned_read_short:offset={offset + total}"
                f":requested={length - total}:got={got}:eof_before_expected_size"
            )
        total += int(got)
    return total


def full_file_read(
    fd: int, *, size: int, generation: int, arm: str | None = None,
    block_bytes: int = WARM_READ_BLOCK_BYTES,
) -> dict[str, Any]:
    """A4: synchronously consume every byte of the file before any mmap copy.

    This is the discriminator between two hypotheses that A2/A3 could not
    separate.  ``posix_fadvise(WILLNEED)`` returned in 0.040 ms and
    ``mmap(MAP_POPULATE)`` returned in 0.774 ms for a 12.31 GB file, which means
    both were accepted and neither materialised anything.  So neither of them
    tested the hypothesis at all; they tested whether the platform honours the
    request, and it does not.  This function removes the platform from the
    experiment: the bytes are read by an ordinary positioned read into a bounded
    reusable scratch buffer, which cannot be optimised away, cannot be advisory,
    and does not touch the mapping.

    Deliberately *not* done, because each would stop it being a diagnostic:

    * no pipelining, no QD, no second thread, no overlap with the timed copies
      or with H2D -- the claim is "every byte was consumed before timing began";
    * no whole-file anonymous buffer -- 12.31 GB will not fit beside the pinned
      arena, and holding it would replace the mmap read with an ordinary RAM read;
    * no ``mmap`` for the warm read, and no slicing of the source mapping, so the
      warm path and the timed path are provably different code.

    The scratch is a ``bytearray``: real anonymous memory, one 64 MiB buffer,
    reused for every block, with no mapping involved at all.

    Fails closed.  The caller may only treat A4 as run when
    ``warm_bytes_read == warm_bytes_requested == size`` and ``warm_complete``.
    """
    selected = active_arm(arm)
    if selected != FULLREAD_ARM:
        return {
            "arm": selected,
            "warm_read_called": False,
            "warm_read_call_count": 0,
            "warm_complete": False,
            "reason": "control_arm",
        }
    total_size = int(size)
    if total_size <= 0:
        raise SourcePopulationError("full_file_read_empty_source")
    step = int(block_bytes)
    if step <= 0:
        raise SourcePopulationError(f"full_file_read_bad_block:{step}")
    primitive = positioned_read_primitive()
    buffer = bytearray(step)
    records: list[dict[str, Any]] = []
    started_ns = time.monotonic_ns()
    started_cpu_ns = time.thread_time_ns()
    bytes_read = 0
    blocks: list[dict[str, Any]] = []
    offset = 0
    ordinal = 0
    while offset < total_size:
        length = min(step, total_size - offset)
        block_started_ns = time.monotonic_ns()
        block_cpu_ns = time.thread_time_ns()
        before = len(records)
        got = _fill_range(fd, buffer, offset, length, records)
        block_wall_ns = max(0, time.monotonic_ns() - block_started_ns)
        block_cpu_ns_used = max(0, time.thread_time_ns() - block_cpu_ns)
        attempts = records[before:]
        blocks.append({
            "ordinal": ordinal,
            "source_offset": int(offset),
            "requested_bytes": int(length),
            "returned_bytes": int(got),
            "wall_ms": round(block_wall_ns / 1e6, 4),
            "thread_cpu_ms": round(block_cpu_ns_used / 1e6, 4),
            "attempts": len(attempts),
            "short_read_retries": sum(
                1 for item in attempts if item["returned_bytes"] < item["requested_bytes"]
            ),
            "eintr_retries": sum(1 for item in attempts if item["state"] == "eintr"),
            "error": next((item["error"] for item in attempts if item["error"]), None),
        })
        bytes_read += int(got)
        offset += int(got)
        ordinal += 1
    wall_ns = max(0, time.monotonic_ns() - started_ns)
    cpu_ns = max(0, time.thread_time_ns() - started_cpu_ns)
    complete = bytes_read == total_size
    evidence = {
        "arm": selected,
        "generation": int(generation),
        "fd": int(fd),
        "warm_read_called": True,
        "warm_read_call_count": 1,
        "warm_primitive": primitive,
        "warm_scratch_bytes": step,
        "warm_scratch_reused": True,
        "warm_uses_mmap": False,
        "warm_bytes_requested": total_size,
        "warm_bytes_read": int(bytes_read),
        "warm_complete": bool(complete),
        "warm_block_bytes": step,
        "warm_block_count": ordinal,
        "warm_read_calls": len(records),
        "warm_short_read_retries": int(sum(
            1 for item in records if item["returned_bytes"] < item["requested_bytes"]
        )),
        "warm_eintr_retries": int(sum(1 for item in records if item["state"] == "eintr")),
        "warm_total_ms": round(wall_ns / 1e6, 4),
        "warm_total_ns": wall_ns,
        "warm_thread_cpu_ms": round(cpu_ns / 1e6, 4),
        "warm_effective_gbps": round((bytes_read / 1e9) / (wall_ns / 1e9), 4) if wall_ns else None,
        "warm_blocks": blocks,
        "warm_reads": records,
    }
    if not complete:
        raise SourcePopulationError(
            f"full_file_read_incomplete:requested={total_size}:read={bytes_read}"
            f":generation={generation}"
        )
    return evidence


__all__ = [
    "CONTROL_ARM",
    "FULLREAD_ARM",
    "ISOLATION_ARMS",
    "MAP_ANONYMOUS",
    "MAP_POPULATE",
    "MAP_PRIVATE",
    "POPULATE_ARM",
    "POPULATION_ARMS",
    "POPULATION_GATE_ENV",
    "POPULATION_TREATMENT_ARMS",
    "POSIX_FADV_WILLNEED",
    "PROT_READ",
    "SourcePopulationError",
    "WARM_READ_BLOCK_BYTES",
    "WILLNEED_ARM",
    "active_arm",
    "confirm_mapping",
    "declared_arm",
    "fadvise_willneed",
    "full_file_read",
    "mapping_flags",
    "population_enabled",
    "positioned_read_primitive",
]
