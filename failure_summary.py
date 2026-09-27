"""Structured failure summaries for comfyui-modal runs."""

import time


class FailureSummary:
    """Builder for a compact structured run-failure summary.

    Usage::

        summary = FailureSummary(phase="preflight")
        summary.fatal_error = "node 454 missing class_type"
        summary.modal_invoked = False
        print(summary.format())
    """

    def __init__(self, phase: str = "unknown"):
        self.run_failed_phase: str = phase
        self.fatal_error: str = ""
        self.modal_invoked: bool = False
        self.time_restore_ms: float = 0.0
        self.time_preload_ms: float = 0.0
        self.time_requirements_ms: float = 0.0
        self.wasted_restore_ms: float = 0.0
        self.wasted_requirements_ms: float = 0.0
        self.model_preload_files: int = 0
        self.requirements_installed: int = 0
        self.missing_nodes_before: list[str] | None = None
        self.missing_nodes_after: list[str] | None = None
        self.invalid_nodes: list[str] | None = None
        self.recommendation: str = ""
        self._created_at: float = time.time()

    def format(self) -> str:
        parts: list[str] = []
        _add = parts.append

        _add(f"run_failed_phase={self.run_failed_phase}")
        if self.fatal_error:
            _add(f'fatal_error="{self.fatal_error}"')
        _add(f"modal_invoked={1 if self.modal_invoked else 0}")

        if self.time_restore_ms > 0:
            _add(f"time_restore_ms={round(self.time_restore_ms, 1)}")
        if self.time_preload_ms > 0:
            _add(f"time_preload_ms={round(self.time_preload_ms, 1)}")
        if self.time_requirements_ms > 0:
            _add(f"time_requirements_ms={round(self.time_requirements_ms, 1)}")

        if self.wasted_restore_ms > 0:
            _add(f"wasted_restore_ms={round(self.wasted_restore_ms, 1)}")
        if self.wasted_requirements_ms > 0:
            _add(f"wasted_requirements_ms={round(self.wasted_requirements_ms, 1)}")

        if self.model_preload_files > 0:
            _add(f"model_preload_files={self.model_preload_files}")
        if self.requirements_installed > 0:
            _add(f"requirements_installed={self.requirements_installed}")

        if self.missing_nodes_before:
            _add(f'missing_nodes_before={self.missing_nodes_before!r}')
        if self.missing_nodes_after:
            _add(f'missing_nodes_after={self.missing_nodes_after!r}')
        if self.invalid_nodes:
            _add(f'invalid_nodes={self.invalid_nodes!r}')

        if self.recommendation:
            _add(f'recommendation="{self.recommendation}"')

        return "  ".join(parts)

    def __str__(self) -> str:
        return self.format()
