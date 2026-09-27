"""Deployment orchestration without execution side effects.

State machine: ``REQUIRED → RUNNING → {PASSED, FAILED}``.

Validation must be explicitly invoked — the coordinator never moves, deletes,
repairs files, or auto-generates.  Concurrent validation requests are
serialized (at most one in-flight at a time).
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from comfymodal_runtime.contracts import DeploymentIdentity


# ── State enumeration ────────────────────────────────────────────────────


class ValidationState(str, Enum):
    """Lifecycle state for deployment validation."""

    REQUIRED = "required"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


# ── Validation record ────────────────────────────────────────────────────


@dataclass
class DeploymentValidation:
    """Immutable snapshot of a single validation run."""

    state: ValidationState = ValidationState.REQUIRED
    generation: int = 0
    validation_run_id: str = ""
    started_at: float | None = None
    completed_at: float | None = None
    error: str = ""
    workflow_hash: str = ""
    model_hash: str = ""
    identity: DeploymentIdentity | None = None

    @classmethod
    def fresh(cls, generation: int = 0) -> DeploymentValidation:
        """Return a clean pre-validation record."""
        return cls(
            state=ValidationState.REQUIRED,
            generation=generation,
            validation_run_id="",
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "state": self.state.value,
            "generation": self.generation,
            "validation_run_id": self.validation_run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "workflow_hash": self.workflow_hash,
            "model_hash": self.model_hash,
        }
        if self.identity is not None:
            d["identity"] = self.identity.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DeploymentValidation:
        identity: DeploymentIdentity | None = None
        raw_id = d.get("identity")
        if raw_id is not None and isinstance(raw_id, dict):
            try:
                identity = DeploymentIdentity(
                    runtime_hash=str(raw_id.get("runtime_hash", "")),
                    dependency_hash=str(raw_id.get("dependency_hash", "")),
                    custom_node_hash=str(raw_id.get("custom_node_hash", "")),
                    source_bytes=int(raw_id.get("source_bytes", 0)),
                    file_hashes=raw_id.get("file_hashes", {}),
                )
            except Exception:
                identity = None
        return cls(
            state=ValidationState(d.get("state", "required")),
            generation=int(d.get("generation", 0)),
            validation_run_id=str(d.get("validation_run_id", "")),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            error=str(d.get("error", "")),
            workflow_hash=str(d.get("workflow_hash", "")),
            model_hash=str(d.get("model_hash", "")),
            identity=identity,
        )


# ── Coordinator ──────────────────────────────────────────────────────────


class ValidationCoordinator:
    """Serializes concurrent validation requests.

    * Only one ``RUNNING`` validation at a time.
    * Concurrent ``request_validation()`` calls return the already-running
      run ID instead of starting a duplicate.
    * ``complete_validation()`` transitions ``RUNNING → {PASSED, FAILED}``.
    * ``mark_required()`` resets the state for a new generation.
    * The coordinator never moves, deletes, repairs files, or auto-generates.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: DeploymentValidation = DeploymentValidation.fresh()

    # ── Thread-safe read ─────────────────────────────────────────────

    @property
    def current(self) -> DeploymentValidation:
        """Latest validation snapshot."""
        with self._lock:
            return self._current

    @property
    def state(self) -> ValidationState:
        """Current validation state."""
        with self._lock:
            return self._current.state

    # ── Mutators ─────────────────────────────────────────────────────

    def request_validation(
        self,
        generation: int,
        *,
        workflow_hash: str = "",
        model_hash: str = "",
        identity: DeploymentIdentity | None = None,
    ) -> str:
        """Explicitly invoke a validation run.

        Returns the ``validation_run_id``.  When a validation is already
        in progress, returns the in-progress run ID (serialization).
        """
        run_id = str(uuid.uuid4())
        with self._lock:
            if self._current.state == ValidationState.RUNNING:
                return self._current.validation_run_id
            self._current = DeploymentValidation(
                state=ValidationState.RUNNING,
                generation=generation,
                validation_run_id=run_id,
                started_at=time.time(),
                completed_at=None,
                workflow_hash=workflow_hash,
                model_hash=model_hash,
                identity=identity,
            )
        return run_id

    def complete_validation(
        self, run_id: str, passed: bool, error: str = ""
    ) -> bool:
        """Mark an in-progress validation as passed or failed.

        Returns ``True`` when *run_id* matched the current validation.
        Returns ``False`` when *run_id* is stale (caller should retry
        or discard).
        """
        with self._lock:
            if self._current.validation_run_id != run_id:
                return False
            if self._current.state != ValidationState.RUNNING:
                return False
            self._current = DeploymentValidation(
                state=ValidationState.PASSED if passed else ValidationState.FAILED,
                generation=self._current.generation,
                validation_run_id=run_id,
                started_at=self._current.started_at,
                completed_at=time.time(),
                error=error,
                workflow_hash=self._current.workflow_hash,
                model_hash=self._current.model_hash,
                identity=self._current.identity,
            )
        return True

    def mark_required(self, generation: int) -> None:
        """Reset validation to ``REQUIRED`` for a new generation."""
        with self._lock:
            self._current = DeploymentValidation.fresh(generation=generation)
