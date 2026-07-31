"""V2 experiment invoker implementing the ``_RemoteInvoker`` protocol.

For each cell, builds a canonical ``ExecutionPlan`` preserving the resolved
workflow, cell controls, input images, production options, GPU, and workspace,
then submits the complete request directly via ``ModalTransport.execute_plan``.

Events are streamed through a shared event sink that the scheduler translates
to journal entries.

This module is a pure protocol implementation — no scheduler, store, or lease
logic lives here.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from pathlib import Path
from typing import Any, Callable

_log = logging.getLogger(__name__)


class V2ExperimentInvoker:
    """Implements the ``_RemoteInvoker`` protocol using the V2 execution pipeline.

    Protocol methods
    ----------------
    - ``open_worker(worker_invocation_id, checkpoint_id, profile_id, workflow, triple)``
    - ``run_cell(worker_invocation_id, cell)`` → dict
    - ``close_worker(worker_invocation_id)``
    - ``cancel_worker(worker_invocation_id)``

    Construction parameters
    -----------------------
    *experiment_id*:
        Unique experiment identifier for tracing.
    *modal_options*:
        Shared modal options dict forwarded to every ``ExecutionPlan``.
    *gpu*:
        GPU identifier for Modal invocation.
    *workspace*:
        Active workspace dict for Modal transport.
    *stream_event_sink*:
        Async callback for streaming progress/status events.
    """

    def __init__(
        self,
        experiment_id: str = "",
        *,
        execution_mode: str = "v2",
        execution_mode_source: str = "request",
        modal_options: dict | None = None,
        gpu: Any = None,
        workspace: dict | None = None,
        stream_event_sink: Callable[..., Any] | None = None,
    ) -> None:
        self._experiment_id = experiment_id
        self._execution_mode = execution_mode or "v2"
        self._execution_mode_source = execution_mode_source or "request"
        self._modal_options = dict(modal_options or {})
        self._gpu = gpu
        self._workspace = workspace
        self._stream_event_sink = stream_event_sink or _safe_event_sink

        # Per-worker state
        self._active_plans: dict[str, dict] = {}

    async def open_worker(
        self,
        worker_invocation_id: str,
        checkpoint_id: str,
        profile_id: str,
        workflow: dict,
        triple: dict,
    ) -> None:
        """Protocol: prepare worker state."""
        self._active_plans[worker_invocation_id] = {
            "checkpoint_id": checkpoint_id,
            "profile_id": profile_id,
            "triple": dict(triple or {}),
        }

    async def run_cell(self, worker_invocation_id: str, cell: dict) -> dict:
        """Protocol: build and execute a single cell via V2 pipeline.

        Returns a dict with keys expected by ``ExperimentRunner._run_checkpoint``:
          - status: "completed" | "error"
          - result: raw Modal result dict
          - output_paths: list of written file paths
          - timing_payload: optional timing data
          - error: error message on failure
          - execution_mode: "v2" (for metadata persistence)
        """
        worker_state = self._active_plans.get(worker_invocation_id)
        if not worker_state:
            return {"status": "error", "error": f"No active worker {worker_invocation_id}"}

        # Resolve the workflow from the cell
        resolved_workflow = cell.get("_resolved_workflow")
        if not resolved_workflow:
            return {"status": "error", "error": "Cell has no _resolved_workflow"}

        # Lazy-import expensive v2 modules
        from canonical_execution import build_execution_plan, execute_plan
        from comfymodal_runtime.modal_transport import ModalTransport
        from comfymodal_runtime.trace import RuntimeTrace

        # Determine output node IDs from cell production_options
        production_options = cell.get("production_options") or {}
        prod_enabled = bool(production_options.get("enabled"))
        output_node_ids = production_options.get("output_node_ids", []) if prod_enabled else []

        # Build execution plan
        prompt_id = cell.get("cell_key", str(uuid.uuid4().hex[:12]))
        plan = build_execution_plan(
            resolved_workflow,
            prompt_id=prompt_id,
            modal_options=self._modal_options,
            production_options=production_options if prod_enabled else None,
            gpu=str(self._gpu or "") if self._gpu else "",
            workspace=self._workspace,
            validate=False,
        )

        # Create runtime trace for this cell
        trace = RuntimeTrace(request_id=prompt_id, process="local")
        trace.set_metadata(
            experiment_id=self._experiment_id,
            execution_mode="v2",
            checkpoint_id=worker_state["checkpoint_id"],
            cell_key=cell.get("cell_key", ""),
        )

        # Execute via V2 pipeline
        try:
            transport = ModalTransport()
            result = await execute_plan(
                plan,
                transport=transport,
                profile_setter=None,
                gpu=str(self._gpu or "") if self._gpu else "",
                workspace=self._workspace,
                trace=trace,
                event_sink=_protocol_event_sink(
                    self._stream_event_sink,
                    context={
                        "experiment_id": self._experiment_id,
                        "checkpoint_id": worker_state["checkpoint_id"],
                        "cell_key": cell.get("cell_key", ""),
                        "attempt_id": cell.get("attempt_id", ""),
                    },
                ),
            )
        except Exception as exc:
            _log.error("V2 experiment invoker execution failed for %s: %s", prompt_id, exc)
            return {
                "status": "error",
                "error": str(exc)[:500],
                "cell_key": cell.get("cell_key", ""),
                "timing_payload": None,
                "execution_mode": self._execution_mode,
                "execution_mode_source": self._execution_mode_source,
            }

        # Keep the V2 path on the same local output/history contract as the
        # legacy invoker.  ``execute_plan`` returns the remote result; this
        # boundary is responsible for writing inline output bytes locally and
        # exposing ComfyUI-compatible output descriptors to the scheduler.
        output_paths: list[str] = []
        primary_output: dict | None = None
        try:
            from local_artifacts import get_studio_outputs_dir
            from comfymodal_runtime.result_delivery import materialize_modal_result

            output_dir = get_studio_outputs_dir()
            output_dir.mkdir(parents=True, exist_ok=True)
            materialized = materialize_modal_result(
                result,
                output_dir=str(output_dir),
                prompt_id=prompt_id,
                auto_save_local=bool(self._modal_options.get("auto_save_local", False)),
                save_folder=str(self._modal_options.get("save_folder", "") or ""),
                save_metadata_sidecar=self._modal_options.get("save_metadata_sidecar", True) is not False,
                output_format=str(self._modal_options.get("output_format", "original") or "original"),
                expected_output_node_ids=tuple(plan.output_node_ids),
            )
            written_files = materialized.get("written_files", [])
            output_paths = [
                Path(path).name for path in written_files
                if isinstance(path, str) and path
            ]
            primary_output = materialized.get("primary_output")
            # Replace the raw output map with native ComfyUI descriptors while
            # retaining the remote result's timing and metadata.
            if isinstance(materialized.get("history_outputs"), dict):
                result["outputs"] = materialized["history_outputs"]
            if primary_output and primary_output.get("asset_id"):
                result["primary_asset_id"] = primary_output["asset_id"]
            result["materialization_timing"] = materialized.get("materialization_timing", {})
        except Exception as exc:
            # A delivery failure must not turn a completed remote cell into a
            # false remote failure; the scheduler still records the cell and
            # the error remains visible in metadata for diagnosis.
            _log.warning("V2 output materialization failed for %s: %s", prompt_id, exc)
            result.setdefault("output_materialization_error", str(exc)[:500])

        # Extract timing payload
        trace_dict = result.get("trace", {}) if isinstance(result, dict) else {}
        _timing_payload = {
            "trace": trace_dict,
            "_restore_timing": result.get("_restore_timing", {}) if isinstance(result, dict) else {},
        }

        # Return in the shape expected by ExperimentRunner
        return {
            "status": "completed",
            "result": result,
            "output_paths": output_paths,
            "timing_payload": _timing_payload,
            "cell_key": cell.get("cell_key", ""),
            "checkpoint_id": worker_state["checkpoint_id"],
            "execution_mode": self._execution_mode,
            "execution_mode_source": self._execution_mode_source,
            "primary_asset_id": (primary_output or {}).get("asset_id", ""),
        }

    async def close_worker(self, worker_invocation_id: str) -> None:
        """Protocol: clean up worker state."""
        self._active_plans.pop(worker_invocation_id, None)

    async def cancel_worker(self, worker_invocation_id: str) -> None:
        """Protocol: cancel an active worker."""
        plan = self._active_plans.pop(worker_invocation_id, None)
        if plan is not None:
            _log.debug("Cancelled V2 worker %s for checkpoint %s", worker_invocation_id, plan.get("checkpoint_id", "?"))


def _safe_event_sink(event_type: str, payload: dict) -> None:
    """Default no-op event sink."""
    pass


def _protocol_event_sink(sink: Callable[..., Any], *, context: dict | None = None) -> Callable:
    """Wrap a protocol-level event sink to match the execute_plan signature."""
    def _sink(event_type: str, payload: dict) -> None:
        try:
            detail = dict(payload or {})
            detail.setdefault("type", event_type)
            for key, value in (context or {}).items():
                if value and key not in detail:
                    detail[key] = value

            async def _dispatch() -> None:
                try:
                    try:
                        maybe_awaitable = sink(event_type, detail)
                    except TypeError:
                        # Studio's existing progress callback accepts one
                        # normalized detail argument; protocol callbacks may
                        # accept the event type and payload separately.
                        maybe_awaitable = sink(detail)
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable
                except Exception:
                    pass

            asyncio.get_running_loop().create_task(_dispatch())
        except Exception:
            pass
    return _sink
