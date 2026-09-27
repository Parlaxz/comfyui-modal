"""Shared worker control backend for cross-environment pause/stop coordination.

Both local bridge code (experiment_runner.py, experiment_scheduler.py)
and remote Modal containers (comfyapp.py) use this to coordinate
pause/stop-now/stop-after-current signals.

The production backend uses modal.Dict as the shared primitive accessible
from both local and remote environments. Tests inject a
FakeDictControlBackend.

Key format (5-component identity contract)::

    control:{deployment_generation}:{experiment_id}:{checkpoint_id}:{worker_invocation_id}:{lease_generation}

Every identity component is required so that control for one invocation,
checkpoint, or experiment never leaks to another.

Stored values are dicts with:
  - ``state``: "continue" | "pause_after_current" | "stop_after_current" | "stop_now"
  - All five identity components
  - ``updated_at``: unix timestamp
"""
from __future__ import annotations

import abc
import hashlib
import os
import time
from typing import Any


# ── Module-level integrity probe (area A1 / area 26) ─────────────────────

def verify_deployment_integrity() -> dict:
    """Return a dict with module path, source SHA-256, control dict name,
    and container session id. Used by the deployed image to validate
    that the control plane module is the expected version.

    This function is called from the deployed container and from local
    tests. It reads its own source file to compute the SHA-256 so the
    probe is always self-consistent.
    """
    module_path = os.path.abspath(__file__)
    source_sha256 = ""
    try:
        with open(module_path, "rb") as f:
            source_sha256 = hashlib.sha256(f.read()).hexdigest()
    except OSError:
        pass
    return {
        "module_path": module_path,
        "source_sha256": source_sha256,
        "control_dict_name": ModalDictControlBackend.DICT_NAME,
        "container_session_id": os.environ.get("MODAL_CONTAINER_ID", ""),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Key construction  (single source of truth — shared by local & remote)
# ═══════════════════════════════════════════════════════════════════════════

CONTROL_KEY_PREFIX = "control:"


def control_key(
    deployment_generation: str,
    experiment_id: str,
    checkpoint_id: str,
    worker_invocation_id: str,
    lease_generation: int,
) -> str:
    """Return the unique dict key for a worker's control record.

    The five-component identity ensures full isolation between
    different deployments, experiments, checkpoints, workers,
    and lease generations.
    """
    return (
        f"{CONTROL_KEY_PREFIX}"
        f"{deployment_generation}:"
        f"{experiment_id}:"
        f"{checkpoint_id}:"
        f"{worker_invocation_id}:"
        f"{lease_generation}"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Backend interface
# ═══════════════════════════════════════════════════════════════════════════


class ControlBackend(abc.ABC):
    """Abstract interface for the shared worker control backend.

    All five identity components are required so the backend
    constructs the correct key and enforces full isolation.
    """

    @abc.abstractmethod
    async def set_control(
        self,
        deployment_generation: str,
        experiment_id: str,
        checkpoint_id: str,
        worker_invocation_id: str,
        lease_generation: int,
        state: str,
    ) -> None:
        """Set the shared control state for a specific invocation.

        May also store the identity components inside the record
        for diagnostic/debugging access.
        """
        ...

    @abc.abstractmethod
    async def get_control(
        self,
        deployment_generation: str,
        experiment_id: str,
        checkpoint_id: str,
        worker_invocation_id: str,
        lease_generation: int,
    ) -> str:
        """Return the current control state ("continue" if absent)."""
        ...

    @abc.abstractmethod
    async def clear_control(
        self,
        deployment_generation: str,
        experiment_id: str,
        checkpoint_id: str,
        worker_invocation_id: str,
        lease_generation: int,
    ) -> None:
        """Remove any stored control record (returns to "continue" default)."""
        ...


# ═══════════════════════════════════════════════════════════════════════════
#  FakeDictControlBackend  (in-memory, for tests)
# ═══════════════════════════════════════════════════════════════════════════


class FakeDictControlBackend(ControlBackend):
    """In-memory dict backend for tests.

    Does NOT depend on Modal; can be used in unit tests directly.
    The ``_get_record()`` helper exposes the full stored dict for
    test assertions about identity metadata.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    async def set_control(
        self,
        deployment_generation: str,
        experiment_id: str,
        checkpoint_id: str,
        worker_invocation_id: str,
        lease_generation: int,
        state: str,
    ) -> None:
        key = control_key(
            deployment_generation, experiment_id,
            checkpoint_id, worker_invocation_id, lease_generation,
        )
        self._store[key] = {
            "state": state,
            "deployment_generation": deployment_generation,
            "experiment_id": experiment_id,
            "checkpoint_id": checkpoint_id,
            "worker_invocation_id": worker_invocation_id,
            "lease_generation": lease_generation,
            "updated_at": time.time(),
        }

    async def get_control(
        self,
        deployment_generation: str,
        experiment_id: str,
        checkpoint_id: str,
        worker_invocation_id: str,
        lease_generation: int,
    ) -> str:
        key = control_key(
            deployment_generation, experiment_id,
            checkpoint_id, worker_invocation_id, lease_generation,
        )
        entry = self._store.get(key)
        if entry is None:
            return "continue"
        return entry.get("state", "continue")

    async def clear_control(
        self,
        deployment_generation: str,
        experiment_id: str,
        checkpoint_id: str,
        worker_invocation_id: str,
        lease_generation: int,
    ) -> None:
        key = control_key(
            deployment_generation, experiment_id,
            checkpoint_id, worker_invocation_id, lease_generation,
        )
        self._store.pop(key, None)

    # ── TTL / cleanup (area A1) ────────────────────────────────────

    async def clear_expired_controls(self, max_age_seconds: float = 3600) -> int:
        """Remove all records whose ``updated_at`` is older than *max_age_seconds*.

        Returns the number of cleared records.
        """
        now = time.time()
        cutoff = now - max_age_seconds
        expired_keys = [
            k for k, v in self._store.items()
            if isinstance(v, dict) and v.get("updated_at", 0) < cutoff
        ]
        for k in expired_keys:
            self._store.pop(k, None)
        return len(expired_keys)

    # ── Test helper ────────────────────────────────────────────────

    def _get_record(
        self,
        deployment_generation: str,
        experiment_id: str,
        checkpoint_id: str,
        worker_invocation_id: str,
        lease_generation: int,
    ) -> dict | None:
        """Return the full stored record for test assertions."""
        key = control_key(
            deployment_generation, experiment_id,
            checkpoint_id, worker_invocation_id, lease_generation,
        )
        return self._store.get(key)


# ═══════════════════════════════════════════════════════════════════════════
#  ModalDictControlBackend  (production, wraps modal.Dict)
# ═══════════════════════════════════════════════════════════════════════════


class ModalDictControlBackend(ControlBackend):
    """Production backend backed by modal.Dict.

    The Modal Dict is created implicitly on first ``.from_name()`` call
    with ``create_if_missing=True``.  Both local bridge code and the
    remote Modal container share the same dict handle.

    The dict name is ``"comfyui-checkpoint-control"``.
    """

    DICT_NAME = "comfyui-checkpoint-control"

    def __init__(self, dict_handle=None):
        """Optionally accept a pre-resolved dict handle for testing."""
        self._dict = dict_handle  # lazy-resolve if None

    def _resolve(self):
        if self._dict is None:
            import modal
            self._dict = modal.Dict.from_name(
                self.DICT_NAME, create_if_missing=True
            )
        return self._dict

    async def set_control(
        self,
        deployment_generation: str,
        experiment_id: str,
        checkpoint_id: str,
        worker_invocation_id: str,
        lease_generation: int,
        state: str,
    ) -> None:
        d = self._resolve()
        key = control_key(
            deployment_generation, experiment_id,
            checkpoint_id, worker_invocation_id, lease_generation,
        )
        record: dict[str, Any] = {
            "state": state,
            "deployment_generation": deployment_generation,
            "experiment_id": experiment_id,
            "checkpoint_id": checkpoint_id,
            "worker_invocation_id": worker_invocation_id,
            "lease_generation": lease_generation,
            "updated_at": time.time(),
        }
        import asyncio
        await asyncio.to_thread(d.__setitem__, key, record)

    async def get_control(
        self,
        deployment_generation: str,
        experiment_id: str,
        checkpoint_id: str,
        worker_invocation_id: str,
        lease_generation: int,
    ) -> str:
        d = self._resolve()
        key = control_key(
            deployment_generation, experiment_id,
            checkpoint_id, worker_invocation_id, lease_generation,
        )
        import asyncio
        try:
            entry = await asyncio.to_thread(d.__getitem__, key)
            if isinstance(entry, dict):
                return entry.get("state", "continue")
        except KeyError:
            pass
        return "continue"

    async def clear_control(
        self,
        deployment_generation: str,
        experiment_id: str,
        checkpoint_id: str,
        worker_invocation_id: str,
        lease_generation: int,
    ) -> None:
        d = self._resolve()
        key = control_key(
            deployment_generation, experiment_id,
            checkpoint_id, worker_invocation_id, lease_generation,
        )
        import asyncio
        try:
            await asyncio.to_thread(d.__delitem__, key)
        except KeyError:
            pass

    async def clear_expired_controls(self, max_age_seconds: float = 3600) -> int:
        """Remove all records whose ``updated_at`` is older than *max_age_seconds*.

        Scans all keys with the ``control:`` prefix, checks the stored
        record's ``updated_at`` field, and deletes expired entries.
        Returns the number of cleared records.

        This is a best-effort cleanup that does NOT hold a global lock
        on the Modal Dict.
        """
        d = self._resolve()
        import asyncio

        now = time.time()
        cutoff = now - max_age_seconds
        cleared = 0
        try:
            all_keys = await asyncio.to_thread(d.keys)
        except Exception:
            return 0
        for k in all_keys:
            if not isinstance(k, str) or not k.startswith(CONTROL_KEY_PREFIX):
                continue
            try:
                entry = await asyncio.to_thread(d.__getitem__, k)
                if isinstance(entry, dict) and entry.get("updated_at", 0) < cutoff:
                    await asyncio.to_thread(d.__delitem__, k)
                    cleared += 1
            except KeyError:
                continue
            except Exception:
                continue
        return cleared
