from __future__ import annotations

from pathlib import Path

import pytest

from tools.v2_control import cli
from tools.v2_control.errors import FlagError, GateError
from tools.v2_control.golden_payload import _golden_p1_request_payload


pytestmark = pytest.mark.fast_unit
ROOT = Path(__file__).resolve().parents[1]
SOURCE = {"prompt": {"1": {}}, "extra_data": {}, "modal_options": {}}
QD2_FLAG = "COMFYMODAL_V2_GOLDEN_CPU_QD2_PREFETCH"


def _config(*sets: str):
    return cli.build_components(ROOT, "golden_p1", sets=list(sets))[3]


def test_golden_control_payload_omits_optional_qd2_selector():
    payload = _golden_p1_request_payload(SOURCE, request_id="control", index=0)
    assert "cpu_qd2_prefetch" not in payload


def test_golden_qd2_payload_sets_explicit_request_selector():
    payload = _golden_p1_request_payload(
        SOURCE, request_id="qd2", index=0, cpu_qd2_prefetch=True,
    )
    assert payload["cpu_qd2_prefetch"] is True

    config = _config(f"{QD2_FLAG}=1")
    args, _env = cli._validation_backend_args(config)
    assert args[-1] == "--golden-p1-cpu-qd2-prefetch"


def test_invalid_qd2_selector_is_rejected_at_registry_and_payload_boundaries():
    with pytest.raises(FlagError):
        _config(f"{QD2_FLAG}=maybe")
    with pytest.raises(ValueError, match="golden_cpu_qd2_prefetch_must_be_bool"):
        _golden_p1_request_payload(  # type: ignore[arg-type]
            SOURCE, request_id="bad", index=0, cpu_qd2_prefetch=1,  # type: ignore[arg-type]
        )


def test_qd2_requires_deploy_gate_and_rejects_instant_tensor():
    config = _config(f"{QD2_FLAG}=1")
    with pytest.raises(GateError, match="COMFYMODAL_GOLDEN_CPU_QD2_PREFETCH=1"):
        cli._require_golden_cpu_qd2_deploy_gate(config)

    source = {"prompt": {}, "extra_data": {"instant_tensor": True}, "modal_options": {}}
    with pytest.raises(ValueError, match="instant_tensor_conflict"):
        _golden_p1_request_payload(
            source, request_id="qd2-instant", index=0, cpu_qd2_prefetch=True,
        )
