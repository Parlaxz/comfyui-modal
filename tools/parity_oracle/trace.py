"""Semantic trace: user-observable behavior + backend intent. No implementation details."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class SemanticTrace:
    scenario_id: str
    impl: str  # "legacy" | "vue"
    visible_controls: list = field(default_factory=list)
    control_types: dict = field(default_factory=dict)
    control_values: dict = field(default_factory=dict)
    available_options: dict = field(default_factory=dict)
    control_ordering: list = field(default_factory=list)
    collapsed_expanded: dict = field(default_factory=dict)
    enabled_disabled: dict = field(default_factory=dict)
    route_hash: str = ""
    storage_writes: dict = field(default_factory=dict)
    api_requests: list = field(default_factory=list)
    request_intent: dict = field(default_factory=dict)
    wizard_suggestions: dict = field(default_factory=dict)
    graph_ops: list = field(default_factory=list)
    upload_guard: str = ""
    sketch_upload: str = ""
    experiment_ops: str = ""
    queue_ops: str = ""
    history_actions: list = field(default_factory=list)
    version_switch: str = ""
    final_state: str = ""

    def to_dict(self):
        return asdict(self)
