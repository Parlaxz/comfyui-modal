from __future__ import annotations

import pytest

from comfymodal_runtime.golden_experiment_controls import (
    CURRENT,
    PHASE_EXACT,
    SUBDIVIDED64,
    GoldenExperimentControlError,
    parse_controls,
    subdivision_scope_note,
    validate_compatibility,
)
from tools.v2_control.golden_payload import _golden_p1_request_payload


pytestmark = pytest.mark.fast_unit
SOURCE = {"prompt": {"1": {}}, "extra_data": {}, "modal_options": {}}


def test_no_controls_preserves_absence_and_current_defaults():
    controls = parse_controls()
    assert controls.source_policy == CURRENT and not controls.experimental
    payload = _golden_p1_request_payload(SOURCE, request_id="baseline", index=0)
    assert "source_policy" not in payload
    assert "source_launch_gap_ns" not in payload


def test_explicit_current_is_explicit_but_selects_current():
    payload = _golden_p1_request_payload(
        SOURCE, request_id="current", index=0, source_policy="CURRENT",
    )
    assert payload["source_policy"] == CURRENT
    assert payload["request_origin_info"]["golden_source_experiment"]["native_qd"] == 4


@pytest.mark.parametrize("gap", [4_000_000, 20_000_000])
def test_supported_gap_propagates(gap):
    controls = parse_controls({"source_launch_gap_ns": gap}, explicit=True)
    assert controls.launch_gap_ns == gap
    payload = _golden_p1_request_payload(
        SOURCE, request_id=f"gap-{gap}", index=0, source_launch_gap_ns=gap,
    )
    assert payload["source_launch_gap_ns"] == gap


def test_unsupported_gap_and_unknown_modes_fail_closed():
    with pytest.raises(GoldenExperimentControlError, match="unsupported_source_launch_gap_ns"):
        parse_controls({"source_launch_gap_ns": 5_000_000}, explicit=True)
    with pytest.raises(GoldenExperimentControlError, match="unsupported_source_policy"):
        parse_controls({"source_policy": "MYSTERY"}, explicit=True)
    with pytest.raises(GoldenExperimentControlError, match="blocked_qd_mode"):
        parse_controls({"qd_mode": "LRU8_EXACT"}, explicit=True)


def test_phase_exact_requires_the_committed_topology():
    controls = parse_controls({"source_policy": PHASE_EXACT}, explicit=True)
    validate_compatibility(controls, reader_count=4, native_qd=4, block_bytes=64 * 1024 * 1024)
    with pytest.raises(GoldenExperimentControlError, match="phase_exact_requires"):
        validate_compatibility(controls, reader_count=2)


def test_subdivided64_requires_forensic_scope_and_prerequisites():
    controls = parse_controls({"microscope_mode": SUBDIVIDED64}, explicit=True)
    validate_compatibility(
        controls, mmap_lifecycle="whole", whole_mmap=True, linux_probes=True,
        parent_ordinals=(1, 8, 17),
    )
    note = subdivision_scope_note((1, 8, 17))
    assert note["scope"] == "three_fixed_full_parent_ordinals_per_model"
    assert note["reconciliation"] == "64MiB_parent=16x4MiB_subchunks"
    with pytest.raises(GoldenExperimentControlError, match="whole_mmap"):
        validate_compatibility(controls, mmap_lifecycle="fresh", whole_mmap=False)
