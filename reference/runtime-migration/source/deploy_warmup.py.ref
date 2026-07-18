"""Deployment generation tracking and warmup state machine.

Authoritative spec: parent plan §15 of
``docs/superpowers/plans/2026-06-17-modal-comfy-testing-suite.md``.

Conventions:
- A "deployment generation" is sha256(version + ":" + fingerprint + ":" +
  deploy_started_unix_s). Any change to version, fingerprint, or a fresh
  deploy bumps the generation. The timestamp component is a known
  weakness (redeploying identical code without time advancing won't bump
  generation); the future Modal-side hook can replace the timestamp with
  the actual Modal deployment ID.
- State lives at .deploy_warmup_state.json (separate from
  .deployed_state.json which the existing __init__.py code maintains).
- Atomic writes via tmp + os.replace. Schema-versioned.

This module does NOT call modal deploy or restart ComfyUI. It owns the
state machine and is consumed by the HTTP routes (Phase 9) which wire
the actual side-effects.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Public errors

class WarmupError(RuntimeError):
    pass


class WarmupRequiredError(WarmupError):
    """Raised when an experiment start is blocked because the active
    deployment is not yet warmed."""


# State file schema version

STATE_SCHEMA_VERSION = 1
STATE_FILENAME = ".deploy_warmup_state.json"


# Generation token

def deployment_generation(comfyapp_version: str, custom_nodes_fingerprint: str,
                          deploy_started_at_unix_s: float) -> str:
    """Return a stable deployment-generation token.

    See module docstring for the design choice. Three components:
    - comfyapp_version
    - custom_nodes_fingerprint
    - deploy_started_at_unix_s
    """
    payload = f"{comfyapp_version}:{custom_nodes_fingerprint}:{deploy_started_at_unix_s}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# WarmupState

class WarmupState:
    """File-backed warmup state. Atomic write."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._data: dict = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return self._default()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return self._default()
            data.setdefault("schema_version", STATE_SCHEMA_VERSION)
            data.setdefault("deployment_generation", "")
            data.setdefault("warmed", False)
            data.setdefault("warmup_status", "")  # "" | "warming" | "warmed" | "failed"
            data.setdefault("warmup_run_id", "")
            data.setdefault("warmed_at", "")
            data.setdefault("warmup_error", "")
            data.setdefault("ui_state", {})
            data.setdefault("deploy_started_at", "")
            data.setdefault("auto_warmup_pending", False)
            return data
        except (json.JSONDecodeError, OSError):
            return self._default()

    @staticmethod
    def _default() -> dict:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "deployment_generation": "",
            "warmed": False,
            "warmup_status": "",
            "warmup_run_id": "",
            "warmed_at": "",
            "warmup_error": "",
            "ui_state": {},
            "deploy_started_at": "",
            "auto_warmup_pending": False,
        }

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)

    # Read API

    def is_warmed(self) -> bool:
        """Return True only if fully warmed (not just warming)."""
        return bool(self._data.get("warmed")) and self._data.get("warmup_status") == "warmed"

    def is_warming(self) -> bool:
        """Return True if warmup is in progress but not yet complete."""
        return self._data.get("warmup_status") == "warming"

    def deployment_generation(self) -> str:
        return self._data.get("deployment_generation", "")

    def warmup_run_id(self) -> str:
        return self._data.get("warmup_run_id", "")

    def warmup_status(self) -> str:
        """Return the raw warmup_status string (\"\", \"warming\", \"warmed\", \"failed\")."""
        return str(self._data.get("warmup_status", ""))

    def warmup_error(self) -> str:
        return self._data.get("warmup_error", "")

    def get_ui_state(self) -> dict:
        return dict(self._data.get("ui_state", {}))

    def snapshot(self) -> dict:
        """Return a copy of the full state for inspection by routes / tests."""
        return dict(self._data)

    # Write API

    def mark_deploy_started(self, comfyapp_version: str, custom_nodes_fingerprint: str,
                            deploy_started_at_unix_s: float) -> str:
        """Mark a new deployment starting. Bumps the generation token and
        marks the state unwarmed."""
        gen = deployment_generation(comfyapp_version, custom_nodes_fingerprint,
                                     deploy_started_at_unix_s)
        self._data["deployment_generation"] = gen
        self._data["warmed"] = False
        self._data["warmup_status"] = ""
        self._data["warmup_run_id"] = ""
        self._data["warmed_at"] = ""
        self._data["warmup_error"] = ""
        self._data["auto_warmup_pending"] = False
        self._data["deploy_started_at"] = (
            datetime.fromtimestamp(deploy_started_at_unix_s, tz=timezone.utc).isoformat()
        )
        self._flush()
        return gen

    def mark_warmup_started(self, generation: str, warmup_run_id: str) -> None:
        """Mark warmup as in-progress.

        Establishes the deployment generation if not already set.  Raises
        WarmupError if warmup is already in progress (exactly one warmup
        per deployment generation).
        """
        if self._data.get("warmup_status") == "warming":
            raise WarmupError(
                f"warmup already in progress for generation "
                f"{self._data['deployment_generation'][:12]}"
            )
        self._data["deployment_generation"] = generation
        self._data["warmup_status"] = "warming"
        self._data["warmed"] = False
        self._data["warmup_run_id"] = warmup_run_id
        self._data["warmed_at"] = ""
        self._data["warmup_error"] = ""
        self._flush()

    def mark_warmed(self, generation: str, warmup_run_id: str) -> None:
        # If a deployment generation is stored and does not match, the
        # supplied generation is stale — reject instead of silently
        # replacing.  The caller must call mark_deploy_started first
        # to establish the correct generation.
        stored_gen = self._data.get("deployment_generation", "")
        if stored_gen and stored_gen != generation:
            raise WarmupError(
                f"stale warmup: generation {generation[:12]} != "
                f"stored {stored_gen[:12]}"
            )
        if not stored_gen:
            self._data["deployment_generation"] = generation
        self._data["warmed"] = True
        self._data["warmup_status"] = "warmed"
        self._data["warmup_run_id"] = warmup_run_id
        self._data["warmed_at"] = datetime.now(tz=timezone.utc).isoformat()
        self._data["warmup_error"] = ""
        self._flush()

    def mark_warmup_failed(self, generation: str, error: str) -> None:
        if generation == self._data.get("deployment_generation", ""):
            self._data["warmed"] = False
            self._data["warmup_status"] = "failed"
            self._data["warmup_error"] = error
            self._flush()

    def invalidate(self) -> None:
        self._data["warmed"] = False
        self._data["warmup_status"] = ""
        self._data["warmup_run_id"] = ""
        self._data["warmed_at"] = ""
        self._data["warmup_error"] = ""
        self._flush()

    def set_ui_state(self, ui_state: dict) -> None:
        self._data["ui_state"] = dict(ui_state)
        self._flush()

    def on_workspace_changed(self, old_workspace_id: str, new_workspace_id: str) -> None:
        """Called when the active Modal workspace changes.

        Marks the warmup state as unwarmed so a stale deployment generation
        from the old workspace cannot be reused. Area A8.
        """
        if old_workspace_id != new_workspace_id:
            self.invalidate()


# ensure_warmup / gate

def _run_placeholder_warmup() -> str:
    """Run a placeholder warmup. Real implementation calls a verified
    warmup workflow (see parent plan section 15 preference order). Returns
    the run id. In this in-session scaffolding, returns a UUID."""
    return f"warm_{uuid.uuid4().hex[:8]}"


def ensure_warmup(state: WarmupState, comfyapp_version: str,
                  custom_nodes_fingerprint: str,
                  deploy_started_at_unix_s: float) -> dict:
    """Ensure the active deployment is warmed.

    Returns one of:
        {"status": "already_warmed", "warmup_run_id": str}
        {"status": "warmed", "warmup_run_id": str}

    Raises WarmupError if a warmup is already in progress (exactly one
    warmup per deployment generation).
    """
    gen = deployment_generation(comfyapp_version, custom_nodes_fingerprint,
                                 deploy_started_at_unix_s)
    if state.deployment_generation() != gen:
        state.mark_deploy_started(comfyapp_version, custom_nodes_fingerprint,
                                   deploy_started_at_unix_s)
    if state.is_warmed():
        return {"status": "already_warmed", "warmup_run_id": state.warmup_run_id()}
    if state.is_warming():
        raise WarmupError(
            f"warmup already in progress for generation {gen[:12]}"
        )
    run_id = _run_placeholder_warmup()
    state.mark_warmup_started(gen, warmup_run_id=run_id)
    state.mark_warmed(gen, warmup_run_id=run_id)
    return {"status": "warmed", "warmup_run_id": run_id}


def gate_experiment(state: WarmupState, comfyapp_version: str,
                    custom_nodes_fingerprint: str,
                    deploy_started_at_unix_s: float) -> None:
    """Block experiment start if the active deployment is not warmed.

    Raises WarmupRequiredError if a warmup is required. The caller is
    expected to call ensure_warmup() first or surface a button to do so.

    Note: the caller should normally use gate_experiment_on_stored_generation()
    instead. This overload regenerates a fresh generation token which will
    NOT match the stored token unless ``deploy_started_at_unix_s`` is the
    exact same value used at deploy time (i.e., not ``time.time()``).
    """
    gen = deployment_generation(comfyapp_version, custom_nodes_fingerprint,
                                 deploy_started_at_unix_s)
    if state.deployment_generation() != gen:
        raise WarmupRequiredError(
            "deployment has changed; warmup required before scored cells"
        )
    if not state.is_warmed():
        raise WarmupRequiredError(
            f"deployment generation {gen[:12]} is not warmed"
        )


def gate_experiment_on_stored_generation(state: WarmupState) -> None:
    """Gate experiment on the stored deployment generation.

    Compares the active state against itself (no fresh timestamp needed)
    so the caller never generates a mismatched token. This is the correct
    function for experiment start routes.
    """
    stored_gen = state.deployment_generation()
    if not stored_gen:
        raise WarmupRequiredError("no deployment found; deploy before scoring")
    if not state.is_warmed():
        raise WarmupRequiredError(
            f"deployment generation {stored_gen[:12]} is not warmed"
        )


# RedeployStateMachine

SEQUENCE = (
    "idle",
    "deploying",
    "waiting_for_modal",
    "restarting_comfyui",
    "waiting_for_comfyui",
    "restoring_ui",
    "running_warmup",
    "ready",
    "unwarmed",
    "failed",
)

_TRANSITIONS: dict = {
    "idle": {"deploying"},
    "deploying": {"waiting_for_modal", "failed"},
    "waiting_for_modal": {"restarting_comfyui", "failed"},
    "restarting_comfyui": {"waiting_for_comfyui", "failed"},
    "waiting_for_comfyui": {"restoring_ui", "failed"},
    "restoring_ui": {"running_warmup", "failed"},
    "running_warmup": {"ready", "unwarmed", "failed"},
    "ready": set(),
    "unwarmed": set(),
    "failed": set(),
}


class RedeployStateMachine:
    """Tracks the (Deploy, Restart, Warm) stateful sequence.

    Side effects (real modal deploy, real ComfyUI restart) are the
    caller's responsibility. This class owns the state transitions
    only.
    """

    def __init__(self, state: WarmupState) -> None:
        self._state = state
        self._phase: str = "idle"
        self._error: str = ""

    def status(self) -> str:
        return self._phase

    def error(self) -> str:
        return self._error

    def _transition(self, target: str) -> None:
        if target not in SEQUENCE:
            raise WarmupError(f"unknown phase: {target!r}")
        allowed = _TRANSITIONS.get(self._phase, set())
        if target not in allowed:
            raise WarmupError(
                f"invalid transition {self._phase!r} -> {target!r}; "
                f"allowed: {sorted(allowed)}"
            )
        self._phase = target

    def start_deploy(self) -> None:
        self._transition("deploying")

    def deploy_succeeded(self, comfyapp_version: str, custom_nodes_fingerprint: str,
                          deploy_started_at_unix_s: float) -> None:
        self._state.mark_deploy_started(
            comfyapp_version, custom_nodes_fingerprint, deploy_started_at_unix_s)
        self._transition("waiting_for_modal")

    def deploy_failed(self, error: str) -> None:
        self._error = error
        self._phase = "failed"

    def modal_ready(self) -> None:
        self._transition("restarting_comfyui")

    def comfyui_restarting(self) -> None:
        self._transition("waiting_for_comfyui")

    def comfyui_ready(self) -> None:
        self._transition("restoring_ui")

    def ui_restored(self) -> None:
        self._transition("running_warmup")

    def warmup_succeeded(self, warmup_run_id: str) -> None:
        gen = self._state.deployment_generation()
        if not gen:
            raise WarmupError("no active deployment generation when warmup succeeded")
        self._state.mark_warmed(gen, warmup_run_id=warmup_run_id)
        self._phase = "ready"

    def warmup_failed(self, error: str) -> None:
        gen = self._state.deployment_generation()
        if gen:
            self._state.mark_warmup_failed(gen, error)
        self._error = error
        self._phase = "unwarmed"
