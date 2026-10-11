"""Request-local Golden source experiment controls.

The normal Golden request deliberately does not import or consult this module's
selection state.  Callers enter here once, at request ingress, only when one of
the experimental selectors is present.  The returned value is immutable and
is safe to carry through the plan and worker boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType
from typing import Any, Mapping


SOURCE_POLICY_ENV = "COMFYMODAL_GOLDEN_SOURCE_POLICY"
SOURCE_LAUNCH_GAP_ENV = "COMFYMODAL_GOLDEN_SOURCE_LAUNCH_GAP_NS"
MICROSCOPE_ENV = "COMFYMODAL_GOLDEN_MICROSCOPE"
QD_MODE_ENV = "COMFYMODAL_GOLDEN_QD_MODE"

CURRENT = "CURRENT"
PHASE_EXACT = "PHASE_EXACT"
MICROSCOPE_OFF = "OFF"
SUBDIVIDED64 = "SUBDIVIDED64_RESIDENCY_FORENSIC_EXACT"
QD_CURRENT = "CURRENT"
SUPPORTED_GAPS_NS = (4_000_000, 6_000_000, 8_000_000, 10_000_000, 15_000_000, 20_000_000)
# Deliberately blocked: these are not implemented experiments.  Never turn a
# request for one of them into CURRENT or a different QD arm silently.
BLOCKED_QD_MODES = ("TRUE_QD1", "TRUE_QD1_128", "LRU8_EXACT", "SUBDIVIDED64_EXACT")
EXACT_IMPL_SOURCE_ID = "43d5f3c31e2d522b26cca647abf83a58c356804e:GlobalSourcePacer.PHASE"


class GoldenExperimentControlError(ValueError):
    """A requested control is unknown, unsupported, or incompatible."""


@dataclass(frozen=True)
class GoldenSourceExperimentControls:
    source_policy: str = CURRENT
    launch_gap_ns: int = 4_000_000
    microscope_mode: str = MICROSCOPE_OFF
    qd_mode: str = QD_CURRENT
    explicit: bool = False

    @property
    def experimental(self) -> bool:
        return self.explicit

    @property
    def effective_description(self) -> Mapping[str, Any]:
        return MappingProxyType({
            "source_policy": self.source_policy,
            "launch_gap_ns": self.launch_gap_ns,
            "microscope_mode": self.microscope_mode,
            "qd_mode": self.qd_mode,
            "reader_count": 4,
            "native_qd": 4,
            "block_bytes": 64 * 1024 * 1024,
            "subdivision_bytes": 4 * 1024 * 1024,
            "exact_impl_source_id": EXACT_IMPL_SOURCE_ID,
        })


_ACTIVE_CONTROLS: ContextVar[GoldenSourceExperimentControls | None] = ContextVar(
    "golden_source_experiment_controls", default=None
)


def _value(raw: Mapping[str, Any], *names: str) -> tuple[Any, bool]:
    for name in names:
        if name in raw:
            return raw[name], True
    return None, False


def parse_controls(raw: Mapping[str, Any] | None = None, *, explicit: bool | None = None) -> GoldenSourceExperimentControls:
    """Parse controls once and fail closed; absence remains distinguishable."""
    values = raw if isinstance(raw, Mapping) else {}
    policy_raw, policy_present = _value(values, "source_policy", SOURCE_POLICY_ENV)
    gap_raw, gap_present = _value(values, "source_launch_gap_ns", SOURCE_LAUNCH_GAP_ENV, "launch_gap_ns")
    microscope_raw, microscope_present = _value(values, "microscope_mode", MICROSCOPE_ENV)
    qd_raw, qd_present = _value(values, "qd_mode", QD_MODE_ENV)
    has_controls = policy_present or gap_present or microscope_present or qd_present
    if explicit is not None:
        has_controls = bool(explicit)

    policy = CURRENT if policy_raw is None or str(policy_raw).strip() == "" else str(policy_raw).strip().upper()
    if policy not in {CURRENT, PHASE_EXACT}:
        raise GoldenExperimentControlError(f"unsupported_source_policy:{policy}")
    microscope = MICROSCOPE_OFF if microscope_raw is None or str(microscope_raw).strip() == "" else str(microscope_raw).strip().upper()
    if microscope not in {MICROSCOPE_OFF, SUBDIVIDED64}:
        raise GoldenExperimentControlError(f"unsupported_microscope_mode:{microscope}")
    qd = QD_CURRENT if qd_raw is None or str(qd_raw).strip() == "" else str(qd_raw).strip().upper()
    if qd in BLOCKED_QD_MODES:
        raise GoldenExperimentControlError(f"blocked_qd_mode:{qd}")
    if qd != QD_CURRENT:
        raise GoldenExperimentControlError(f"unsupported_qd_mode:{qd}")
    if gap_raw is None or str(gap_raw).strip() == "":
        gap = 4_000_000
    else:
        try:
            gap = int(str(gap_raw).strip())
        except (TypeError, ValueError) as exc:
            raise GoldenExperimentControlError("invalid_source_launch_gap_ns") from exc
    if gap not in SUPPORTED_GAPS_NS:
        raise GoldenExperimentControlError(f"unsupported_source_launch_gap_ns:{gap}")
    return GoldenSourceExperimentControls(policy, gap, microscope, qd, has_controls)


def validate_compatibility(
    controls: GoldenSourceExperimentControls,
    *,
    reader_count: int = 4,
    native_qd: int = 4,
    block_bytes: int = 64 * 1024 * 1024,
    mmap_lifecycle: str = "fresh",
    linux_probes: bool = True,
    whole_mmap: bool | None = None,
    parent_ordinals: tuple[int, ...] | list[int] | None = None,
) -> None:
    """Validate topology-sensitive constraints before worker admission."""
    if controls.source_policy == PHASE_EXACT and (reader_count, native_qd, block_bytes) != (4, 4, 64 * 1024 * 1024):
        raise GoldenExperimentControlError("phase_exact_requires_qd4_four_readers_64mib_slots")
    if controls.microscope_mode == SUBDIVIDED64:
        if not linux_probes:
            raise GoldenExperimentControlError("subdivided64_requires_linux_probes")
        if whole_mmap is False or str(mmap_lifecycle).lower() != "whole":
            raise GoldenExperimentControlError("subdivided64_requires_whole_mmap")
        if parent_ordinals is not None and tuple(parent_ordinals) != tuple(dict.fromkeys(parent_ordinals)):
            raise GoldenExperimentControlError("subdivided64_requires_distinct_parents")
        if parent_ordinals is not None and len(parent_ordinals) != 3:
            raise GoldenExperimentControlError("subdivided64_requires_three_full_parents")


def subdivision_scope_note(selected_ordinals: tuple[int, ...] | list[int], *, expected_count: int = 3) -> Mapping[str, Any]:
    """Immutable diagnostic scope note shared by runtime and report consumers."""
    selected = tuple(int(value) for value in selected_ordinals)
    return MappingProxyType({
        "selection_algorithm": "three_fixed_full_parent_ordinals:second_midpoint_last",
        "selected_ordinal_list": list(selected),
        "expected_count": int(expected_count),
        "actual_count": len(selected),
        "scope": "three_fixed_full_parent_ordinals_per_model",
        "reconciliation": "64MiB_parent=16x4MiB_subchunks",
        "probe_fault_overhead": "included_in_parent_wall_and_classified_contaminated",
        "contamination_classification": "diagnostic_probe_fault_read_overhead",
    })


def controls_from_request(request: Mapping[str, Any]) -> GoldenSourceExperimentControls:
    """Perform the single ingress presence check for a request."""
    origin = request.get("request_origin_info") if isinstance(request, Mapping) else None
    origin = origin if isinstance(origin, Mapping) else {}
    raw: dict[str, Any] = {}
    for key in ("source_policy", "source_launch_gap_ns", "microscope_mode", "qd_mode"):
        if key in request:
            raw[key] = request[key]
        elif key in origin:
            raw[key] = origin[key]
    return parse_controls(raw, explicit=bool(raw))


def active_controls() -> GoldenSourceExperimentControls | None:
    return _ACTIVE_CONTROLS.get()


@contextmanager
def controls_context(controls: GoldenSourceExperimentControls):
    token = _ACTIVE_CONTROLS.set(controls)
    try:
        yield controls
    finally:
        _ACTIVE_CONTROLS.reset(token)


__all__ = [
    "CURRENT", "PHASE_EXACT", "MICROSCOPE_OFF", "SUBDIVIDED64", "QD_CURRENT",
    "SUPPORTED_GAPS_NS", "GoldenExperimentControlError", "GoldenSourceExperimentControls",
    "controls_from_request", "parse_controls", "validate_compatibility",
    "active_controls", "controls_context", "subdivision_scope_note",
]
