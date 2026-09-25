"""Minimal additive shareable-host-staging support for the frozen mmap source harness.

This module is intentionally small and is *only* used when the caller opts in.
When it is not used, ``run_mmap_lifecycle_probe`` follows its original private
destination path byte-for-byte.

Phase 1 (this file): the four QD4 reader processes write the 64 MiB blocks they
already read into a POSIX shared-memory staging region (``/dev/shm`` backed,
fork-inherited) instead of process-private bytearrays.  A release consumer in
the CUDA-owning parent process advances each lane's ``consumed`` counter so a
reader can reuse a slot.  No CUDA is involved yet.

Staging layout: ``qd`` lanes; each lane owns ``slots`` slots of ``read_bytes``.
A lane's slot ``k`` is the block with per-lane publish sequence ``k % slots``.
A reader may only write sequence ``s`` when ``s - consumed < slots``; it
publishes ``s + 1`` only after the native memcpy has fully returned.

All control counters use ``lock=False`` shared primitives.  There is exactly one
writer per counter per lane (the lane's reader) and exactly one reader (the
consumer thread), so the unlocked 8-byte accesses are race-free and are ordered
by the publish-after-copy stores.  Avoiding the primitive's lock matters because
the parent forks reader processes while the consumer thread is alive; an
unlocked integer cannot be inherited in a locked state.
"""

from __future__ import annotations

import ctypes
import threading
import time
from typing import Any


def build_staging(qd: int, slots: int, read_bytes: int) -> dict[str, Any]:
    """Allocate one POSIX shared-memory staging region for ``qd`` reader lanes.

    The returned dict is passed to the reader child (inherited by fork) and to
    the release consumer.  ``_buf`` keeps the mapping owner alive.
    """
    import multiprocessing as mp

    qd = int(qd)
    slots = int(slots)
    read_bytes = int(read_bytes)
    if qd < 1 or slots < 1 or read_bytes < 1:
        raise ValueError("qd, slots and read_bytes must be positive")
    lane_bytes = slots * read_bytes
    total = qd * lane_bytes
    buf = mp.RawArray(ctypes.c_char, total)
    return {
        "enabled": True,
        "seg_base": int(ctypes.addressof(buf)),
        "slots": slots,
        "lane_bytes": lane_bytes,
        "read_bytes": read_bytes,
        "bytes": total,
        "published": [mp.Value("q", 0, lock=False) for _ in range(qd)],
        "consumed": [mp.Value("q", 0, lock=False) for _ in range(qd)],
        "slot_off": [mp.Array("q", slots, lock=False) for _ in range(qd)],
        "slot_len": [mp.Array("q", slots, lock=False) for _ in range(qd)],
        "alive": mp.Value("i", 1, lock=False),
        "_buf": buf,
    }


def start_release_consumer(staging: dict[str, Any], qd: int) -> tuple[threading.Thread, dict[str, Any]]:
    """Release staging slots as soon as a reader publishes them (Phase 1 only).

    No bytes are copied: this only proves that a shareable destination does not
    change the source path.  The consumer exits once ``alive`` is cleared and no
    further published slots are pending.
    """
    qd = int(qd)
    state: dict[str, Any] = {"released": 0, "max_lag": 0, "wall_ms": None}

    def _run() -> None:
        started = time.perf_counter()
        while True:
            progressed = False
            for lane in range(qd):
                pub = int(staging["published"][lane].value)
                con = int(staging["consumed"][lane].value)
                if pub > con:
                    staging["consumed"][lane].value = pub
                    state["released"] += pub - con
                    progressed = True
            lag = 0
            for lane in range(qd):
                lane_lag = int(staging["published"][lane].value) - int(staging["consumed"][lane].value)
                if lane_lag > lag:
                    lag = lane_lag
            if lag > state["max_lag"]:
                state["max_lag"] = lag
            if not progressed and int(staging["alive"].value) == 0:
                break
            time.sleep(0.0002)
        state["wall_ms"] = (time.perf_counter() - started) * 1000.0

    thread = threading.Thread(target=_run, name="staging-release", daemon=True)
    thread.start()
    return thread, state


def start_consumer(
    staging: dict[str, Any],
    qd: int,
    read_bytes: int,
    mode: str,
    verify: bool = False,
) -> tuple[threading.Thread, dict[str, Any]]:
    """Start the parent-side consumer for the requested additive mode.

    ``mode="shared"`` releases slots only (Phase 1).  ``registered`` (Phase 2)
    and ``h2d`` (Phase 3) are added by later commits and use the same seam.
    """
    if mode == "shared":
        return start_release_consumer(staging, int(qd))
    raise ValueError(f"unsupported staging consumer mode: {mode}")

