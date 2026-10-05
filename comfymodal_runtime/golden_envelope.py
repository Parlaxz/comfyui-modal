"""Golden call-envelope marks: pure measurement with no heavy imports.

Modal's UI "Execution time" spans the whole method call, while every Golden
mark starts at ``golden_call_start_mono_ns`` (just before ``execute_golden``)
and ends at ``return_armed``. The interval between those boundaries was
therefore unattributed by construction. These scalar monotonic marks bracket it
so the gap can be split into pre-Golden, result-construction, wire handoff and
post-stream release instead of estimated from outside.

This module exists separately from ``modal_app`` for two reasons:

1. The logic is genuinely lightweight -- an ordered dict of integers and a
   print -- so tests of it should not have to import a 24k-line module that
   pulls in torch and ComfyUI just to exercise boundary ordering.
2. The emitted ``executed_source_sha256`` is read from the identity frozen at
   *import* time by :mod:`comfymodal_runtime.source_identity`, not by hashing
   ``__file__`` during the request. A container restored from a Modal memory
   snapshot keeps the code objects imported before capture while the mounted
   tree can be newer, so hashing the mounted file at request time reports the
   NEW bytes while OLD code executes. The frozen value cannot drift that way,
   and it costs a dict lookup instead of a filesystem read on the request path.
"""

from __future__ import annotations

from . import deploy_identity as _deploy
from . import source_identity as _identity

#: Declared boundary order. Emission follows this, not dict insertion order.
ENVELOPE_ORDER = (
    "method_entry_mono_ns",
    "golden_call_start_mono_ns",
    "golden_return_mono_ns",
    "yield_mono_ns",
    "stream_drained_mono_ns",
    "release_start_mono_ns",
    "release_end_mono_ns",
)

#: Cap on tracked requests so a long-lived container cannot accumulate them.
ENVELOPE_MAX = 64

ENVELOPE: dict[str, dict[str, int]] = {}

# The module whose identity the envelope reports: the one running Golden.
_EXECUTING_MODULE = "comfymodal_runtime.modal_app"


def executed_source_sha256() -> str:
    """SHA-256 of the source this interpreter actually imported.

    Frozen at import time by ``source_identity``. Never hashes the mounted
    filesystem at request time, so a stale snapshot reports its own old
    identity instead of the newer mounted bytes.
    """
    return _identity.imported_sha(_EXECUTING_MODULE)


def record(request_id: str, marks: dict[str, int]) -> None:
    """Store marks for ``request_id``, evicting the oldest beyond the cap."""
    ENVELOPE[request_id] = marks
    while len(ENVELOPE) > ENVELOPE_MAX:
        ENVELOPE.pop(next(iter(ENVELOPE)), None)


def emit_envelope(request_id: str) -> None:
    """Print the measured call envelope as deltas from method entry.

    Pops the marks so a long-lived container cannot accumulate them. An unknown
    or already-emitted ``request_id`` is a safe no-op.

    The line also carries ``deploy_id``, read from the value frozen at import by
    :mod:`comfymodal_runtime.deploy_identity`. That is the authoritative
    same-request statement of which deployment ran: a container restored from an
    older snapshot reports the older id, which the caller compares against the
    deployment it intended to run.
    """
    marks = ENVELOPE.pop(request_id, None)
    if not marks:
        return
    base = marks.get("method_entry_mono_ns")
    parts: list[str] = []
    for key in ENVELOPE_ORDER:
        value = marks.get(key)
        if value is None:
            continue
        delta = "" if base is None else " delta_ms=%.3f" % ((value - base) / 1e6)
        parts.append("%s=%d%s" % (key, value, delta))
    print(
        "[v2.golden.envelope] request_id=%s deploy_id=%s "
        "executed_source_sha256=%s %s"
        % (
            request_id,
            _deploy.deploy_id(),
            executed_source_sha256(),
            " ".join(parts),
        ),
        flush=True,
    )