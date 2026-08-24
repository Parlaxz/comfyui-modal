"""R44D Level-2 deployment-boundary proof: ``modal_app._runtime_env()``.

R44C proved that a v2ctl dry-run only shows the CHILD environment handed to
the deploy BAT; the Modal class-level ``env=`` dictionary built by
``_runtime_env()`` is a SECOND boundary that silently dropped the four R44B
``COMFYMODAL_V2_REQUEST_*`` activation keys (the container resolved them to
"0" and the whole request FastSafe lane disengaged).

These tests exercise ``_runtime_env()`` itself -- the authoritative output
that Modal receives at deploy time -- and must stay in sync with the
profile's activation contract.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


REQUEST_KEYS = (
    "COMFYMODAL_V2_REQUEST_FASTSAFE",
    "COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE",
    "COMFYMODAL_V2_REQUEST_UNET_FASTSAFE",
    "COMFYMODAL_V2_REQUEST_UNET_SOURCE_PREP",
)

TUNING_KEYS = (
    "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB",
    "COMFYMODAL_V2_UNET_FASTSAFE_THREADS",
    "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES",
    "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB",
)


def _runtime_env():
    from comfymodal_runtime.modal_app import _runtime_env

    return _runtime_env()


@pytest.mark.parametrize("key", REQUEST_KEYS)
def test_request_keys_default_off_when_absent(key):
    """Absent host env -> the container default stays '0' (never hardcoded on)."""
    with patch.dict(os.environ, {}, clear=True):
        env = _runtime_env()
    assert env.get(key) == "0"


@pytest.mark.parametrize("key", REQUEST_KEYS)
def test_request_keys_passthrough_when_set(key):
    """Host/deploy env value crosses into the Modal class env verbatim."""
    with patch.dict(os.environ, {key: "1"}, clear=True):
        env = _runtime_env()
    assert env.get(key) == "1"


def test_all_four_request_flags_active_together():
    """The exact R44 profile activation tuple crosses the boundary together."""
    host = {key: "1" for key in REQUEST_KEYS}
    with patch.dict(os.environ, host, clear=True):
        env = _runtime_env()
    for key in REQUEST_KEYS:
        assert env[key] == "1", key


@pytest.mark.parametrize("key", TUNING_KEYS)
def test_fastsafe_tuning_keys_present(key):
    """Historical FastSafe tuning keys remain present in the class env."""
    with patch.dict(os.environ, {}, clear=True):
        env = _runtime_env()
    assert key in env


def test_fastsafe_tuning_values_cross_boundary():
    """T8 / B256 MiB / bbuf512 values propagate when the profile sets them."""
    host = {
        "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "8",
        "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "268435456",
        "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "524288",
        "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "8",
        "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "268435456",
        "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "524288",
    }
    with patch.dict(os.environ, host, clear=True):
        env = _runtime_env()
    for key, value in host.items():
        assert env[key] == value, key


def test_global_prewarm_flag_and_request_scoped_knobs_coexist():
    """Old global prewarm stays off while request-scoped knobs cross intact."""
    host = {
        "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
        "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
        "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "8",
    }
    with patch.dict(os.environ, host, clear=True):
        env = _runtime_env()
    assert env["COMFYMODAL_V2_CHECKPOINT_PREWARM"] == "0"
