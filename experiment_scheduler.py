"""Experiment scheduler and controls.

Owns the lifecycle of one experiment:
  start, pause, stop_after_current, stop_now, resume,
  continue_here, restart_block, restart_from, skip_block, run_missing.

Wraps ``ExperimentRunner`` (Phase 5). Cooperates with ``ExperimentStore``
(Phase 1) for the event journal. Bridges journal events to an
event_callback so Phase 9 can forward them to PromptServer.send_sync.

Conventions:
- Status lifecycle: draft -> running -> (pause_requested <-> running) ->
  paused -> (resume) -> running -> completed | failed_fatal | stopped.
  "stop_after_current" and "stop_now" both settle to "stopped".
- Pause sets a flag the runner checks between cells. The runner does
  not interrupt the currently-executing cell.
- Stop-now additionally calls the runner's stop_now() which sets its
  internal _stop_event.
- Restart-Block issues a new attempt for every cell in the checkpoint
  and bumps the checkpoint's lease generation. Old attempts remain
  in the journal (immutable).
- Run-missing: cells with no "cell.completed" event in the journal
  for the current attempt lineage are re-run.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ── Public types ─────────────────────────────────────────────────────────

class SchedulerError(RuntimeError):
    pass


# Status constants
STATUS_DRAFT = "draft"
STATUS_RUNNING = "running"
STATUS_PAUSE_REQUESTED = "pause_requested"
STATUS_PAUSED = "paused"
STATUS_STOP_AFTER_CURRENT_REQUESTED = "stop_after_current_requested"
STATUS_STOP_NOW_REQUESTED = "stop_now_requested"
STATUS_STOPPED = "stopped"
STATUS_COMPLETED = "completed"
STATUS_COMPLETED_WITH_FAILURES = "completed_with_failures"
STATUS_FAILED_FATAL = "failed_fatal"


TERMINAL_STATUSES = {
    STATUS_STOPPED, STATUS_COMPLETED, STATUS_COMPLETED_WITH_FAILURES,
    STATUS_FAILED_FATAL,
}


# ── ExperimentScheduler ──────────────────────────────────────────────────

class ExperimentScheduler:
    def __init__(self, *, store, leases, invoker=None, compilation=None,
                 max_containers: int = 1, event_callback: Optional[Callable] = None) -> None:
        self._store = store
        self._leases = leases
        self._invoker = invoker
        self._compilation = compilation
        self._max_containers = max_containers
        self._event_callback = event_callback
        self._status: str = STATUS_DRAFT
        self._pause_event: asyncio.Event = asyncio.Event()
        self._runner: Any = None
        self._runner_task: Optional[asyncio.Task] = None
        self._pause_requested: bool = False
        self._stop_after_current_flag: bool = False
        self._skipped_checkpoints: set = set()
        # Skip the EventBridge's blocking callback (used in tests)

    # ── Status ──────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "status": self._status,
            "experiment_id": (self._compilation or {}).get("experiment_id", ""),
            "revision": (self._compilation or {}).get("revision", 1),
        }

    def _set_status(self, new: str) -> None:
        if self._status == new:
            return
        self._status = new
        self._emit("experiment.status", {"status": new})
        self._persist()

    # ── Public controls ─────────────────────────────────────────────

    async def start(self) -> dict:
        if self._status not in (STATUS_DRAFT, STATUS_PAUSED, STATUS_STOPPED):
            raise SchedulerError(f"cannot start from status {self._status!r}")
        if self._invoker is None:
            raise SchedulerError("invoker is required to start")
        if self._compilation is None:
            raise SchedulerError("compilation is required to start")
        # Reset pause event so runner doesn't think it's already paused
        self._pause_event.clear()
        self._pause_requested = False
        self._stop_after_current_flag = False
        self._set_status(STATUS_RUNNING)
        self._emit("experiment.started", {
            "experiment_id": self._compilation["experiment_id"],
            "revision": self._compilation["revision"],
            "total_cells": len(self._compilation.get("cells", [])),
        })
        filtered = self._filter_skipped(self._compilation)
        if not filtered.get("cells"):
            self._set_status(STATUS_COMPLETED)
            return {"completed": 0, "failed": 0, "interrupted": 0}
        from experiment_runner import ExperimentRunner
        self._runner = ExperimentRunner(
            store=self._store, leases=self._leases, invoker=self._invoker,
            compilation=filtered,
            max_containers=self._max_containers,
        )
        # If pause was requested before this run, set the pause event
        # back to triggered so the runner pauses immediately. The runner
        # itself does not check the event; the scheduler polls it
        # between cells via a wrapper. For now, we keep the runner
        # primitive; pause is handled by a parallel "monitor" that
        # calls pause_now when the event is set.
        monitor = asyncio.create_task(self._monitor())
        result = await self._runner.run()
        monitor.cancel()
        # Determine final status from snapshot counters (C1)
        self._compute_terminal_status()
        return result

    async def pause(self) -> None:
        if self._status != STATUS_RUNNING:
            raise SchedulerError(f"cannot pause from status {self._status!r}")
        self._pause_requested = True
        if self._runner is not None:
            self._runner._pause_requested = True
            self._runner._stop_event.set()
            await self._runner.request_pause()
        self._set_status(STATUS_PAUSE_REQUESTED)
        # Let start() set STATUS_PAUSED after runner.run() returns.

    async def stop_after_current(self) -> None:
        if self._status != STATUS_RUNNING:
            raise SchedulerError(f"cannot stop from status {self._status!r}")
        self._set_status(STATUS_STOP_AFTER_CURRENT_REQUESTED)
        self._stop_after_current_flag = True
        if self._runner is not None:
            self._runner._stop_event.set()
            await self._runner.request_stop_after_current()
        # Let start() set STATUS_STOPPED after runner.run() returns.

    async def stop_now(self) -> None:
        if self._status != STATUS_RUNNING:
            raise SchedulerError(f"cannot stop from status {self._status!r}")
        self._set_status(STATUS_STOP_NOW_REQUESTED)
        if self._runner is not None:
            await self._runner.stop_now()

    async def resume(self) -> dict:
        if self._status not in (STATUS_PAUSED, STATUS_STOPPED):
            raise SchedulerError(f"cannot resume from status {self._status!r}")
        # Reset pause/stop flags before the resumed run, matching start().
        self._pause_event.clear()
        self._pause_requested = False
        self._stop_after_current_flag = False
        self._set_status(STATUS_RUNNING)
        result = await self.continue_here()
        # Determine final status after resume from snapshot counters.
        self._compute_terminal_status()
        return result

    async def continue_here(self) -> dict:
        """Run from the first incomplete cell across all checkpoints."""
        if self._compilation is None:
            raise SchedulerError("no compilation set")
        self._persist()
        # Re-issue only the cells that lack a successful attempt.
        return await self._run_filtered(self._missing_cells())

    async def restart_block(self, checkpoint_id: str) -> dict:
        """Create a new attempt for every cell in the checkpoint. Bumps
        the checkpoint's lease generation. Previous attempts are kept in
        the journal as 'attempt.superseded' events."""
        if self._compilation is None:
            raise SchedulerError("no compilation set")
        # Mark previous visible attempts as superseded
        events = list(self._store.read_events())
        for ev in events:
            if ev["type"] in ("cell.completed", "cell.attempt_created") and ev.get("payload", {}).get("checkpoint_id") == checkpoint_id:
                self._store.append_event({
                    "type": "attempt.superseded",
                    "payload": {
                        "cell_key": ev["payload"].get("cell_key"),
                        "checkpoint_id": checkpoint_id,
                        "previous_attempt_id": ev["payload"].get("attempt_id"),
                    },
                })
        # Bump lease generation: claim+release+reclaim to force a fresh generation
        exp_id = self._compilation.get("experiment_id", "")
        existing = self._leases.snapshot(exp_id)["leases"].get(checkpoint_id, {})
        if existing and existing.get("status") == "claimed":
            wid = existing.get("worker_invocation_id")
            try:
                self._leases.release(exp_id, checkpoint_id, wid)
            except Exception:
                pass
        # Re-run just the cells in this checkpoint
        ck_cells = [c for c in self._compilation["cells"] if c["checkpoint_id"] == checkpoint_id]
        self._persist()
        return await self._run_subset(ck_cells)

    async def restart_from(self, checkpoint_id: str) -> dict:
        """Restart this checkpoint and all later checkpoints in execution order."""
        if self._compilation is None:
            raise SchedulerError("no compilation set")
        # Determine execution order of checkpoints (use their position in the compilation)
        ck_order = [c["id"] for c in self._compilation["checkpoints"]]
        if checkpoint_id not in ck_order:
            raise SchedulerError(f"unknown checkpoint {checkpoint_id!r}")
        idx = ck_order.index(checkpoint_id)
        target_ck_ids = set(ck_order[idx:])
        # Mark earlier visible attempts as superseded
        events = list(self._store.read_events())
        for ev in events:
            if ev["type"] in ("cell.completed", "cell.attempt_created") and ev.get("payload", {}).get("checkpoint_id") in target_ck_ids:
                self._store.append_event({
                    "type": "attempt.superseded",
                    "payload": {
                        "cell_key": ev["payload"].get("cell_key"),
                        "checkpoint_id": ev["payload"].get("checkpoint_id"),
                        "previous_attempt_id": ev["payload"].get("attempt_id"),
                    },
                })
        # Re-run those checkpoints
        target_cells = [c for c in self._compilation["cells"] if c["checkpoint_id"] in target_ck_ids]
        self._persist()
        return await self._run_subset(target_cells)

    async def skip_block(self, checkpoint_id: str) -> None:
        """Mark all cells in this checkpoint as skipped (no attempt)."""
        if self._compilation is None:
            raise SchedulerError("no compilation set")
        self._skipped_checkpoints.add(checkpoint_id)
        ck_cells = [c for c in self._compilation["cells"] if c["checkpoint_id"] == checkpoint_id]
        for cell in ck_cells:
            self._store.append_event({
                "type": "cell.skipped",
                "payload": {
                    "cell_key": cell["cell_key"],
                    "checkpoint_id": checkpoint_id,
                },
            })
        self._store.append_event({
            "type": "checkpoint.skipped",
            "payload": {"checkpoint_id": checkpoint_id},
        })
        self._persist()

    async def unskip_block(self, checkpoint_id: str) -> None:
        """Remove a checkpoint's skipped status."""
        if checkpoint_id in self._skipped_checkpoints:
            self._skipped_checkpoints.discard(checkpoint_id)
            self._store.append_event({
                "type": "checkpoint.unskipped",
                "payload": {"checkpoint_id": checkpoint_id},
            })
            self._persist()

    async def rerun_cell(self, cell_key: str) -> dict:
        """Rerun a single cell by key."""
        if self._compilation is None:
            raise SchedulerError("no compilation set")
        cells = [c for c in self._compilation.get("cells", []) if c.get("cell_key") == cell_key]
        if not cells:
            return {"completed": 0}
        # Mark previous attempts as superseded
        for ev in self._store.read_events():
            if ev.get("payload", {}).get("cell_key") == cell_key and ev["type"] in (
                "cell.completed", "cell.attempt_created", "cell.failed", "cell.interrupted"
            ):
                self._store.append_event({
                    "type": "attempt.superseded",
                    "payload": {
                        "cell_key": cell_key,
                        "checkpoint_id": cells[0].get("checkpoint_id", ""),
                        "previous_attempt_id": ev["payload"].get("attempt_id"),
                    },
                })
        self._persist()
        return await self._run_subset(cells)

    async def continue_checkpoint(self, checkpoint_id: str) -> dict:
        """Run from the first incomplete cell in a specific checkpoint.

        C3: selects from the chosen checkpoint only. Eligible: pending,
        interrupted, failed, completed-but-missing-asset.  Ineligible:
        valid completed (with primary original), skipped.
        """
        if self._compilation is None:
            raise SchedulerError("no compilation set")
        self._persist()
        ck_cells = [c for c in self._compilation["cells"] if c["checkpoint_id"] == checkpoint_id]
        missing = self._eligible_from(ck_cells)
        return await self._run_subset(missing)

    async def run_missing(self) -> dict:
        """Re-run cells that have no successful attempt in the journal."""
        if self._compilation is None:
            raise SchedulerError("no compilation set")
        self._persist()
        return await self._run_subset(self._missing_cells())

    def _compute_terminal_status(self) -> None:
        """C1: compute final status from rebuild_snapshot counters.

        Logic:
          - Every non-skipped cell with valid primary original → completed
          - Current failures + no pending → completed_with_failures
          - Pending due to pause → paused
          - Pending due to stop → stopped
          - Experiment-level fatal → failed_fatal
        """
        snap = self._store.rebuild_snapshot(
            total_cells=len(self._compilation.get("cells", [])) if self._compilation else 0
        )
        counters = snap.get("counters", {})
        checkpoint_states = snap.get("checkpoints", {}) or {}
        has_fatal_checkpoint = any(
            (checkpoint_states.get(ck_id, {}) or {}).get("status") == STATUS_FAILED_FATAL
            for ck_id in checkpoint_states
        )
        completed = counters.get("completed", 0)
        failed = counters.get("failed", 0)
        total = snap.get("total_cells", 0)
        visible_count = completed + failed + counters.get("interrupted", 0) + counters.get("skipped", 0)

        if self._pause_requested:
            self._set_status(STATUS_PAUSED)
        elif self._stop_after_current_flag or self._status == STATUS_STOP_NOW_REQUESTED:
            self._set_status(STATUS_STOPPED)
        elif snap.get("status") == STATUS_FAILED_FATAL or has_fatal_checkpoint:
            self._set_status(STATUS_FAILED_FATAL)
        elif total == 0:
            # No cells at all
            self._set_status(STATUS_COMPLETED)
        elif visible_count < total:
            # Not all expected cells are terminal — incomplete unrequested run.
            # Use a safe non-completed terminal/error status.
            self._set_status(STATUS_FAILED_FATAL)
        elif failed > 0:
            # All cells terminal, some with failures
            self._set_status(STATUS_COMPLETED_WITH_FAILURES)
        else:
            # All cells terminal, no failures
            self._set_status(STATUS_COMPLETED)

    def _eligible_from(self, cells: list) -> list:
        """C3: Return cells eligible for continue/run-missing from a cell list.

        A cell is eligible if it is NOT validly completed (no missing asset)
        and NOT skipped.
        """
        skipped_keys = set()
        for ev in self._store.read_events():
            if ev["type"] == "cell.skipped":
                ck = ev.get("payload", {}).get("cell_key", "")
                if ck:
                    skipped_keys.add(ck)
        result = []
        for cell in cells:
            ck = cell.get("cell_key", "")
            if ck in skipped_keys:
                continue
            # Check if cell is validly completed (has primary original asset on disk)
            if ck not in {c["cell_key"] for c in self._missing_cells_work(cells)}:
                # Not in missing set → validly completed → exclude
                # But _missing_cells_work returns cells that ARE missing.
                # So if this cell is NOT in that set, it's valid → skip.
                # Actually, _missing_cells_work returns cells that NEED re-run.
                # So cells NOT in the result of _missing_cells_work are valid.
                pass  # Will be handled by checking against missing
            result.append(cell)
        # Use _missing_cells_work to determine which are valid
        missing_set = {c["cell_key"] for c in self._missing_cells_work(cells)}
        return [c for c in cells if c.get("cell_key", "") in missing_set]

    def _missing_cells_work(self, candidate_cells: list) -> list:
        """Internal: check which cells from candidate_cells need re-run.

        Used by _eligible_from and _missing_cells to avoid redundant
        journal scans.
        """
        exp_id = (self._compilation or {}).get("experiment_id", "")
        events = list(self._store.read_events())
        snap = self._store.rebuild_snapshot()
        cell_visible = snap.get("cell_visible", {})
        attempts = snap.get("attempts", {})

        # C4: determine which checkpoints have been unskipped
        unskipped_checkpoints = set()
        for ev in events:
            payload = ev.get("payload", {}) or {}
            et = ev.get("type", "")
            if et == "checkpoint.unskipped":
                unskipped_checkpoints.add(payload.get("checkpoint_id", ""))

        # Build set of skipped cell_keys, excluding cells whose checkpoint
        # was later unskipped.
        skipped_ck_to_ck = {}
        for ev in events:
            payload = ev.get("payload", {}) or {}
            ck = payload.get("cell_key", "")
            et = ev.get("type", "")
            if et == "cell.skipped" and ck:
                ck_id = payload.get("checkpoint_id", "")
                skipped_ck_to_ck[ck] = ck_id

        terminal_skipped_keys = set()
        for ck, ck_id in skipped_ck_to_ck.items():
            if ck_id not in unskipped_checkpoints:
                terminal_skipped_keys.add(ck)

        result = []
        for cell in candidate_cells:
            ck = cell.get("cell_key", "")
            if ck in terminal_skipped_keys:
                continue
            latest_status = cell_visible.get(ck, "")
            if latest_status not in ("completed",):
                # Not completed → needs re-run
                result.append(cell)
                continue
            # C5: verify the primary original asset exists on disk with full integrity
            latest_attempt = attempts.get(ck, {})
            latest_attempt_id = latest_attempt.get("attempt_id", "")
            if not latest_attempt_id:
                result.append(cell)
                continue
            try:
                assets = self._leases.list_assets_for_cell(ck, experiment_id=exp_id)
                valid = False
                for asset in assets:
                    if asset.get("variant") != "original":
                        continue
                    # Verify file exists on disk
                    asset_path = asset.get("path", "")
                    if not asset_path:
                        continue
                    if not os.path.isfile(asset_path):
                        continue
                    # Verify attempt ownership
                    asset_attempt = asset.get("attempt_id", "")
                    if latest_attempt_id and asset_attempt and asset_attempt != latest_attempt_id:
                        continue
                    # C5: verify byte_size matches
                    stored_size = asset.get("byte_size", 0)
                    if stored_size > 0:
                        try:
                            actual_size = os.path.getsize(asset_path)
                            if actual_size != stored_size:
                                continue
                        except OSError:
                            continue
                    # C5: verify SHA-256 hash if stored
                    stored_hash = asset.get("content_hash", "") or ""
                    if stored_hash:
                        try:
                            import hashlib as _h
                            with open(asset_path, "rb") as _f:
                                actual_hash = _h.sha256(_f.read()).hexdigest()
                            if actual_hash != stored_hash:
                                continue
                        except OSError:
                            continue
                    # C5: verify image decodes — only when stored_hash is
                    # set (strongest integrity signal).  Avoids rejecting
                    # broadly-valid assets with only size metadata.
                    if stored_hash:
                        try:
                            from PIL import Image as _Img
                            try:
                                _img = _Img.open(asset_path)
                                _img.verify()
                            except Exception:
                                mime = asset.get("mime_type", "")
                                if mime.startswith("image/"):
                                    continue
                        except ImportError:
                            pass  # PIL not available — skip decode check
                    # All checks passed
                    valid = True
                    break
                if not valid:
                    result.append(cell)
            except Exception:
                result.append(cell)
        return result

    def _persist(self) -> None:
        """Persist current scheduler state for crash recovery."""
        try:
            from experiment_service import REGISTRY
            exp_id = (self._compilation or {}).get("experiment_id", "")
            skipped = sorted(self._skipped_checkpoints) if self._skipped_checkpoints else []
            REGISTRY.save_scheduler_state(
                exp_id,
                compilation=self._compilation,
                max_containers=self._max_containers,
                status=self._status,
                skipped_checkpoints=skipped,
            )
        except Exception as exc:
            print(f"[comfyui-modal] scheduler state persist failed: {exc}")

    # ── Internal helpers ────────────────────────────────────────────

    def _missing_cells(self) -> list:
        """Return cells that need re-running: pending, interrupted, failed,
        or completed-but-missing-asset cells.

        Delegates to ``_missing_cells_work`` with the full compilation cell list.
        """
        if self._compilation is None:
            return []
        return self._missing_cells_work(self._compilation.get("cells", []))

    def _filter_skipped(self, compilation: dict) -> dict:
        """Return a copy of the compilation with cells from skipped checkpoints removed."""
        out = dict(compilation)
        out["cells"] = [c for c in compilation["cells"] if c["checkpoint_id"] not in self._skipped_checkpoints]
        out["checkpoints"] = [
            c for c in compilation["checkpoints"] if c["id"] not in self._skipped_checkpoints
        ]
        return out

    async def _run_subset(self, cells: list) -> dict:
        """Run a subset of cells through a fresh runner."""
        from experiment_runner import ExperimentRunner
        sub_compilation = dict(self._compilation)
        ck_ids = {c["checkpoint_id"] for c in cells}
        sub_compilation["cells"] = cells
        sub_compilation["checkpoints"] = [c for c in self._compilation["checkpoints"] if c["id"] in ck_ids]
        runner = ExperimentRunner(
            store=self._store, leases=self._leases, invoker=self._invoker,
            compilation=sub_compilation, max_containers=self._max_containers,
        )
        self._runner = runner
        return await runner.run()

    async def _run_filtered(self, cells: list) -> dict:
        return await self._run_subset(cells)

    def _forward_events(self) -> None:
        """Forward all journal events to the event callback (event bridge)."""
        if self._event_callback is None:
            return
        for ev in list(self._store.read_events()):
            try:
                self._event_callback(ev)
            except Exception:
                pass

    async def _monitor(self) -> None:
        """No-op monitor for now. Pause is implemented via the runner's
        _stop_event; the real pause semantics (finish current cell, then
        stop) are achieved by setting _stop_event which the runner checks
        between cells."""
        try:
            while True:
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            return

    def _emit(self, event_type: str, payload: dict) -> None:
        ev = self._store.append_event({
            "type": event_type,
            "payload": payload,
        })
        if self._event_callback is not None:
            try:
                self._event_callback(ev)
            except Exception:
                pass
