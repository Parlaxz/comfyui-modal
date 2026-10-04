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
POPULATION_ARMS = (CONTROL_ARM, WILLNEED_ARM, POPULATE_ARM)
# The arms that carry a population treatment at all.  ``A`` is the untreated
# control that shares the mapped source with them.
POPULATION_TREATMENT_ARMS = (WILLNEED_ARM, POPULATE_ARM)
# Every arm the isolation selector accepts, mirrored from the registry enum.  The
# prior B/C/D arms carry no population arm and must stay runnable.
ISOLATION_ARMS = ("A", "A2", "A3", "B", "C", "D")

# Linux mmap / fadvise constants, spelled out rather than imported so the values
# the experiment asserts on are visible in one place.
PROT_READ = 1
MAP_PRIVATE = 2
MAP_POPULATE = 0x8000
POSIX_FADV_WILLNEED = 3

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

    Returns ``"A"`` whenever the gate is off, which is the production path.  A
    declared ``A2``/``A3`` with the gate off is a configuration error rather than
    a silent downgrade to the control.

    ``B``/``C``/``D`` declare no population arm at all, so they are the untreated
    control whether or not the gate is up; requiring the gate for them would
    refuse to run arms that never asked for a treatment.
    """
    arm = declared_arm(value)
    if arm not in POPULATION_TREATMENT_ARMS:
        return CONTROL_ARM
    if not population_enabled():
        raise SourcePopulationError(
            f"source_population_arm_requires_gate:{arm}:{POPULATION_GATE_ENV}"
        )
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


__all__ = [
    "CONTROL_ARM",
    "ISOLATION_ARMS",
    "MAP_POPULATE",
    "MAP_PRIVATE",
    "POPULATE_ARM",
    "POPULATION_ARMS",
    "POPULATION_GATE_ENV",
    "POPULATION_TREATMENT_ARMS",
    "POSIX_FADV_WILLNEED",
    "PROT_READ",
    "SourcePopulationError",
    "WILLNEED_ARM",
    "active_arm",
    "confirm_mapping",
    "declared_arm",
    "fadvise_willneed",
    "mapping_flags",
    "population_enabled",
]
