"""Conditioning cache contract: forced miss, encode=1, persist=0 — no exception."""

from __future__ import annotations

import pytest

from comfymodal_runtime.golden.contracts import (
    DEFAULT_CONDITIONING_CONTRACT,
    ConditioningContract,
    GoldenError,
)


def test_default_contract_values():
    assert DEFAULT_CONDITIONING_CONTRACT.forced_miss is True
    assert DEFAULT_CONDITIONING_CONTRACT.encode_calls == 1
    assert DEFAULT_CONDITIONING_CONTRACT.persist == 0
    assert DEFAULT_CONDITIONING_CONTRACT == ConditioningContract()


def test_validate_observed_holds_on_forced_miss_single_encode():
    contract = ConditioningContract()
    contract.validate_observed(observed_miss=False, observed_encodes=1, observed_persisted=0)


def test_validate_observed_rejects_hit():
    with pytest.raises(GoldenError, match="miss"):
        ConditioningContract().validate_observed(observed_miss=True, observed_encodes=1, observed_persisted=0)


def test_validate_observed_rejects_wrong_encode_count():
    with pytest.raises(GoldenError, match="encode_calls"):
        ConditioningContract().validate_observed(observed_miss=False, observed_encodes=2, observed_persisted=0)


def test_validate_observed_rejects_persistence():
    with pytest.raises(GoldenError, match="persisted"):
        ConditioningContract().validate_observed(observed_miss=False, observed_encodes=1, observed_persisted=3)
