"""Tests for the request-carried variance diagnostic env allowlist.

Covers, without requiring Modal/CUDA:
  1  allowlist contains exactly the bounded diagnostic keys
  2  abbreviated variance_mode / variance_pretouch map to their env vars
  3  direct env-key forms are accepted
  4  bool/int values normalize to bounded env strings
  5  dict/list/object and non-scalar values are rejected (no injection)
  6  out-of-allowlist observability modes are rejected
  7  arbitrary / unknown keys are never applied
  8  application writes only allowlisted env values (preserving defaults)
  9  applied values are recorded back into request_origin_info (trace-visible)
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from comfymodal_runtime.modal_app import (
    _apply_request_variance_diagnostics,
    _normalize_request_diag_env_value,
)

_BOOL_KEYS = {
    "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS",
    "COMFYMODAL_V2_UNET_PRETOUCH",
}


class NormalizeValueTest(unittest.TestCase):
    def test_bool_true_false(self):
        self.assertEqual(_normalize_request_diag_env_value(True), "1")
        self.assertEqual(_normalize_request_diag_env_value(False), "0")

    def test_int_only_zero_one(self):
        self.assertEqual(_normalize_request_diag_env_value(1), "1")
        self.assertEqual(_normalize_request_diag_env_value(0), "0")
        self.assertIsNone(_normalize_request_diag_env_value(2))
        self.assertIsNone(_normalize_request_diag_env_value(-1))

    def test_string_lowercased_and_bounded(self):
        self.assertEqual(_normalize_request_diag_env_value("  ON "), "on")
        self.assertEqual(_normalize_request_diag_env_value("true"), "true")
        self.assertIsNone(_normalize_request_diag_env_value(""))
        self.assertIsNone(_normalize_request_diag_env_value("x" * 65))
        # innocuous charset only
        self.assertIsNone(_normalize_request_diag_env_value("a; rm -rf /"))

    def test_non_scalar_rejected(self):
        self.assertIsNone(_normalize_request_diag_env_value({"x": 1}))
        self.assertIsNone(_normalize_request_diag_env_value([1, 2]))
        self.assertIsNone(_normalize_request_diag_env_value(object()))


class ApplyDiagnosticsTest(unittest.TestCase):
    def test_abbreviated_keys_map_to_env(self):
        with patch.dict(os.environ, {}, clear=False):
            for key in _BOOL_KEYS:
                os.environ.pop(key, None)
            os.environ.pop("COMFYMODAL_V2_OBSERVABILITY_MODE", None)
            applied = _apply_request_variance_diagnostics(
                {"variance_mode": True, "variance_pretouch": 0}
            )
            self.assertEqual(applied.get("COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"), "1")
            self.assertEqual(applied.get("COMFYMODAL_V2_UNET_PRETOUCH"), "0")
            self.assertEqual(
                os.environ.get("COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"), "1"
            )
            self.assertEqual(os.environ.get("COMFYMODAL_V2_UNET_PRETOUCH"), "0")

    def test_direct_env_key_forms_accepted(self):
        with patch.dict(os.environ, {}, clear=False):
            applied = _apply_request_variance_diagnostics(
                {
                    "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "1",
                    "COMFYMODAL_V2_UNET_PRETOUCH": "off",
                    "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
                }
            )
            self.assertEqual(
                applied["COMFYMODAL_V2_VARIANCE_DIAGNOSTICS"], "1"
            )
            self.assertEqual(applied["COMFYMODAL_V2_UNET_PRETOUCH"], "off")
            self.assertEqual(applied["COMFYMODAL_V2_OBSERVABILITY_MODE"], "full")

    def test_out_of_allowlist_observability_rejected(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMFYMODAL_V2_OBSERVABILITY_MODE", None)
            applied = _apply_request_variance_diagnostics(
                {"COMFYMODAL_V2_OBSERVABILITY_MODE": "secret_mode"}
            )
            self.assertEqual(applied, {})
            self.assertNotIn(
                "COMFYMODAL_V2_OBSERVABILITY_MODE", os.environ
            )

    def test_unknown_and_non_scalar_keys_ignored(self):
        with patch.dict(os.environ, {}, clear=False):
            for key in list(_BOOL_KEYS):
                os.environ.pop(key, None)
            os.environ.pop("COMFYMODAL_V2_OBSERVABILITY_MODE", None)
            applied = _apply_request_variance_diagnostics(
                {
                    "variance_mode": {"inject": True},
                    "evil_env_key": "1",
                    "COMFYMODAL_V2_UNET_PRETOUCH": ["not", "scalar"],
                    "some_token": "supersecret",
                }
            )
            self.assertEqual(applied, {})
            # no env var written for the ignored / invalid keys
            self.assertNotIn("evil_env_key", os.environ)
            self.assertNotIn("some_token", os.environ)
            self.assertNotIn("COMFYMODAL_V2_UNET_PRETOUCH", os.environ)

    def test_boolean_token_validation(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMFYMODAL_V2_UNET_PRETOUCH", None)
            applied = _apply_request_variance_diagnostics(
                {"COMFYMODAL_V2_UNET_PRETOUCH": "maybe"}
            )
            self.assertEqual(applied, {})
            self.assertNotIn("COMFYMODAL_V2_UNET_PRETOUCH", os.environ)


class TraceVisibilityTest(unittest.TestCase):
    def test_applied_values_flow_into_request_origin_info(self):
        # Emulates the run_plan_stream_impl wiring: apply then record back.
        request_origin_info: dict = {"variance_pretouch": 1}
        applied = _apply_request_variance_diagnostics(request_origin_info)
        if applied:
            _existing = request_origin_info.get("applied_diagnostic_env")
            if not isinstance(_existing, dict):
                _existing = {}
            _existing.update(applied)
            request_origin_info["applied_diagnostic_env"] = _existing
        self.assertEqual(
            request_origin_info["applied_diagnostic_env"],
            {"COMFYMODAL_V2_UNET_PRETOUCH": "1"},
        )


if __name__ == "__main__":
    unittest.main()
