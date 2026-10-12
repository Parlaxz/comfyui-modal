"""Focused tests for the post-yield cert-write deferral.

Covers:
  1. ``build_pending_cert_write`` — stash built exactly when the inline
     write was due (scheduled AND preflight ran AND nonempty identity),
     ``None`` otherwise. Never raises.
  2. ``cert_cache_lookup_label`` — a lookup with nothing stored is a
     ``cache_miss`` (fresh container), not a ``cache_evict`` with an empty
     reason. Revalidation failures keep the evict label.
  3. ``ModalRuntimeEntrypoint._finalize_pending_cert_write`` — consumes the
     stash idempotently, awaits the volume write with the stashed payload,
     updates in-memory snapshot state on success, invalidates on failure,
     and never raises (a failure must not mask the terminal result).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.fast_unit

import comfymodal_runtime.modal_app as modal_app
from comfymodal_runtime.modal_app import (
    ModalRuntimeEntrypoint,
    build_pending_cert_write,
    cert_cache_lookup_label,
)


# ── build_pending_cert_write ─────────────────────────────────────────────


def test_pending_cert_write_none_when_not_scheduled() -> None:
    assert build_pending_cert_write(False, True, "abc", ["1"], {}, {"a": "b"}) is None


def test_pending_cert_write_none_when_preflight_did_not_run() -> None:
    assert build_pending_cert_write(True, False, "abc", ["1"], {}, {"a": "b"}) is None


def test_pending_cert_write_none_on_empty_identity() -> None:
    assert build_pending_cert_write(True, True, "", ["1"], {}, {"a": "b"}) is None


def test_pending_cert_write_builds_stash() -> None:
    stash = build_pending_cert_write(True, True, "id123", ["7", "9"], {"e": 1}, {"workflow_hash": "w"})
    assert stash is not None
    assert stash["identity"] == "id123"
    assert stash["outputs_to_execute"] == ["7", "9"]
    assert stash["node_errors"] == {"e": 1}
    assert stash["identity_components"] == {"workflow_hash": "w"}


def test_pending_cert_write_copies_inputs() -> None:
    outputs = ["7"]
    stash = build_pending_cert_write(True, True, "id123", outputs, {}, {})
    assert stash is not None
    outputs.append("MUTATED")
    assert stash["outputs_to_execute"] == ["7"]


# ── cert_cache_lookup_label ──────────────────────────────────────────────


def test_cache_lookup_labels_plain_miss() -> None:
    label, reason = cert_cache_lookup_label(cached_present=False, evict_reason="")
    assert label == "cache_miss"
    assert reason == "no_process_entry"


def test_cache_lookup_keeps_evict_on_revalidation_failure() -> None:
    label, reason = cert_cache_lookup_label(cached_present=True, evict_reason="component_mismatch")
    assert label == "cache_evict"
    assert reason == "component_mismatch"


def test_cache_lookup_evict_defaults_reason() -> None:
    label, reason = cert_cache_lookup_label(cached_present=True, evict_reason="")
    assert label == "cache_evict"
    assert reason == "revalidation_failed"


# ── _finalize_pending_cert_write ─────────────────────────────────────────


class _FakeBootstrapState:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.snapshot_cert_valid = False
        self.snapshot_cert_retained = False
        self.snapshot_cert_identity = ""
        self.snapshot_cert_reason = ""

    def set_snapshot_certificate(self, cert: dict) -> None:
        self.calls.append("set")
        # Mirror the real validator's accept path for a coherent cert.
        self.snapshot_cert_valid = bool(cert.get("identity") and cert.get("preflight_ok"))

    def invalidate_snapshot_certificate(self, *, reason: str = "") -> None:
        self.calls.append(f"invalidate:{reason}")
        self.snapshot_cert_valid = False


def _make_self(stash: Any) -> SimpleNamespace:
    state = _FakeBootstrapState()
    return SimpleNamespace(
        _v2_pending_cert_write=stash,
        bootstrap=SimpleNamespace(state=state),
        _fake_state=state,
    )


def test_finalize_noop_without_stash() -> None:
    async def _run() -> None:
        fake = _make_self(None)
        with patch.object(modal_app, "_write_v2_validation_certificate") as writer:
            await ModalRuntimeEntrypoint._finalize_pending_cert_write(fake)  # type: ignore[arg-type]
            writer.assert_not_called()
        assert fake._v2_pending_cert_write is None
        assert fake._fake_state.calls == []

    asyncio.run(_run())


def test_finalize_writes_and_consumes_stash() -> None:
    async def _run() -> None:
        stash = build_pending_cert_write(True, True, "id123", ["7"], {}, {"workflow_hash": "w"})
        fake = _make_self(stash)

        async def _writer(identity: str, outputs: list, errors: dict, *, components: Any = None, preflight_ok: bool = False) -> bool:
            assert identity == "id123"
            assert outputs == ["7"]
            assert preflight_ok is True
            assert components == {"workflow_hash": "w"}
            return True

        with patch.object(modal_app, "_write_v2_validation_certificate", side_effect=_writer):
            await ModalRuntimeEntrypoint._finalize_pending_cert_write(fake)  # type: ignore[arg-type]
        # Consumed idempotently...
        assert fake._v2_pending_cert_write is None
        # ...and the in-memory snapshot state was retained.
        assert fake._fake_state.calls == ["set"]
        assert fake._fake_state.snapshot_cert_valid is True
        assert fake._fake_state.snapshot_cert_retained is True
        # Second call is a no-op.
        with patch.object(modal_app, "_write_v2_validation_certificate") as writer:
            await ModalRuntimeEntrypoint._finalize_pending_cert_write(fake)  # type: ignore[arg-type]
            writer.assert_not_called()

    asyncio.run(_run())


def test_finalize_never_raises_and_invalidates_on_failure() -> None:
    async def _run() -> None:
        stash = build_pending_cert_write(True, True, "id123", ["7"], {}, {})
        fake = _make_self(stash)

        async def _boom(*args: Any, **kwargs: Any) -> bool:
            raise RuntimeError("volume gone")

        with patch.object(modal_app, "_write_v2_validation_certificate", side_effect=_boom):
            # Must not raise: tail failures never mask the terminal result.
            await ModalRuntimeEntrypoint._finalize_pending_cert_write(fake)  # type: ignore[arg-type]
        assert fake._v2_pending_cert_write is None
        assert fake._fake_state.calls == ["invalidate:certificate_write_failed"]

    asyncio.run(_run())
