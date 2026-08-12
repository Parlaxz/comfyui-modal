"""Focused tests for the native fast-disk UNET benchmark harness plumbing.

CPU-only; no Modal, no network, no new dependency:

1. ``COMFYMODAL_V2_NATIVE_FAST_DISK_UNET`` configuration plumbing:
   - deploy-baked into the V2 container from the caller's environment via
     ``comfyapp._V2_RUNTIME_ENV`` with a default of ``"0"`` (OFF);
   - pinned to default ``0`` and printed in the sanitized env-profile
     summary of both ``deploy_and_run_v2_single.bat`` and ``run_v2_single.bat``.

2. No-model-snapshot runtime-shape validator correction in
   ``tools.benchmark_v2_direct._validate_runtime_shape``:
   - with ``COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=0`` a None
     ``stored_snapshot_model_order`` is valid and artifacts persist;
   - when snapshots are enabled, existing exact order validation is
     unchanged (on + None rejected, on + matching order accepted);
   - an unexpected non-None order is never silently accepted, even when
     snapshots are disabled (no other validation is loosened).

3. Output identity/hash reuse for deterministic baseline parity: the harness
   already captures a deterministic sha256 output identity per image
   (``asset_id`` is the bare sha256) and verifies it during asset proof
   fetch (``_read_remote_asset``).  Those existing primitives are reused
   here — no broad parity system is invented and generation behavior is
   unchanged.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from tools.benchmark_v2_direct import (  # noqa: E402
    _cpu_model_snapshot_enabled,
    _extract_images,
    _read_remote_asset,
    _validate_runtime_shape,
)
from comfymodal_runtime.runtime_shape import runtime_shape_config  # noqa: E402

REPO_ROOT = Path(_PROJECT_ROOT)
COMFYAPP_PATH = REPO_ROOT / "comfyapp.py"
DEPLOY_BAT_PATH = REPO_ROOT / "deploy_and_run_v2_single.bat"
RUN_BAT_PATH = REPO_ROOT / "run_v2_single.bat"

_ENV_KEYS = (
    "COMFYMODAL_V2_THREAD_POLICY",
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER",
    "COMFYMODAL_V2_CPU_REQUEST",
    "COMFYMODAL_V2_MEMORY_REQUEST",
    "COMFYMODAL_V2_MEMORY_MB",
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT",
    "COMFYMODAL_V2_BASELINE_CPU_REQUEST",
    "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST",
    "COMFYMODAL_V2_RUNTIME_SHAPE_LABEL",
    "COMFYMODAL_V2_RUNTIME_SHAPE_ID",
    "COMFYMODAL_V2_RESTORE_TORCH_THREADS",
    "COMFYMODAL_V2_ALLOW_MULTI_AXIS",
)


def _expected_shape() -> dict[str, Any]:
    return runtime_shape_config().identity_payload()


def _valid_identity(*, stored_order: str | None = "O0") -> dict[str, Any]:
    """Minimal identity that passes every C8 check except stored order."""
    shape = _expected_shape()
    return {
        "app_name": "stable-modal-comfy-v2-shadow",
        "class_name": "ModalRuntimeEntrypointV2",
        "method_name": "run_plan_stream",
        "cpu": shape["cpu_request"],
        "memory_mb": shape["memory_request"],
        "fingerprint": "a" * 24,
        "runtime_shape": dict(shape),
        "runtime_shape_fingerprint": shape["runtime_shape_fingerprint"],
        "runtime_shape_label": shape["runtime_shape_label"],
        "stored_snapshot_model_order": stored_order,
    }


def _valid_result() -> dict[str, Any]:
    """Minimal remote result carrying a runtime_shape_observed event."""
    return {
        "trace": {
            "events": [
                {
                    "name": "runtime_shape_observed",
                    "phase": "lifecycle",
                    "metadata": {
                        "runtime_shape_fingerprint": _expected_shape()[
                            "runtime_shape_fingerprint"
                        ],
                        "status": "baseline_passthrough",
                    },
                }
            ]
        }
    }


def _result_with_snapshot_order(construction_order: str) -> dict[str, Any]:
    """Result whose trace reports a successful cpu_snapshot_models_ready."""
    result = _valid_result()
    result["trace"]["events"].append(
        {
            "name": "cpu_snapshot_models_ready",
            "phase": "snapshot",
            "metadata": {"status": "ok", "construction_order": construction_order},
        }
    )
    return result


class RuntimeShapeValidatorNoSnapshotTests(unittest.TestCase):
    """Requirement 2: no-model-snapshot runtime-shape validation."""

    def setUp(self) -> None:
        for key in _ENV_KEYS:
            os.environ.pop(key, None)

    def test_snapshot_disabled_accepts_none_stored_order(self) -> None:
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "0"
        artifact = _validate_runtime_shape(_valid_result(), _valid_identity(stored_order=None))
        self.assertIsNone(artifact["stored_snapshot_model_order"])
        self.assertEqual(
            artifact["construction_order_semantics"], "model_construction_order_only"
        )

    def test_snapshot_disabled_absent_flag_accepts_none_stored_order(self) -> None:
        # The flag is absent: env_flag semantics treat it as disabled.
        os.environ.pop("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", None)
        artifact = _validate_runtime_shape(_valid_result(), _valid_identity(stored_order=None))
        self.assertIsNone(artifact["stored_snapshot_model_order"])

    def test_snapshot_disabled_accepts_matching_non_none_order(self) -> None:
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "0"
        artifact = _validate_runtime_shape(_valid_result(), _valid_identity(stored_order="O0"))
        self.assertEqual(artifact["stored_snapshot_model_order"], "O0")

    def test_snapshot_disabled_rejects_unexpected_non_none_order(self) -> None:
        # An unexpected non-None order is never silently accepted even when
        # snapshots are disabled: validation is not loosened.
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "0"
        with self.assertRaisesRegex(RuntimeError, "stored snapshot order"):
            _validate_runtime_shape(_valid_result(), _valid_identity(stored_order="O3"))

    def test_snapshot_disabled_still_recovers_order_from_trace_event(self) -> None:
        # Existing event-based recovery is unchanged: when the trace reports a
        # successful cpu_snapshot_models_ready, its order is validated exactly.
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "0"
        result = _result_with_snapshot_order("O0")
        artifact = _validate_runtime_shape(result, _valid_identity(stored_order=None))
        self.assertEqual(artifact["stored_snapshot_model_order"], "O0")

    def test_snapshot_enabled_rejects_none_stored_order(self) -> None:
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"
        with self.assertRaisesRegex(RuntimeError, "stored snapshot order"):
            _validate_runtime_shape(_valid_result(), _valid_identity(stored_order=None))

    def test_snapshot_enabled_accepts_matching_order(self) -> None:
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"
        artifact = _validate_runtime_shape(_valid_result(), _valid_identity(stored_order="O0"))
        self.assertEqual(artifact["stored_snapshot_model_order"], "O0")

    def test_snapshot_enabled_rejects_mismatched_order(self) -> None:
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"
        with self.assertRaisesRegex(RuntimeError, "stored snapshot order"):
            _validate_runtime_shape(_valid_result(), _valid_identity(stored_order="O1"))

    def test_snapshot_enabled_recovers_order_from_trace_event(self) -> None:
        # Existing event-based recovery also works when snapshots are enabled.
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"
        result = _result_with_snapshot_order("O0")
        artifact = _validate_runtime_shape(result, _valid_identity(stored_order=None))
        self.assertEqual(artifact["stored_snapshot_model_order"], "O0")

    def test_cpu_model_snapshot_enabled_follows_env_flag_semantics(self) -> None:
        os.environ.pop("COMFYMODAL_V2_CPU_MODEL_SNAPSHOT", None)
        self.assertFalse(_cpu_model_snapshot_enabled())
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "0"
        self.assertFalse(_cpu_model_snapshot_enabled())
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "off"
        self.assertFalse(_cpu_model_snapshot_enabled())
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "1"
        self.assertTrue(_cpu_model_snapshot_enabled())
        os.environ["COMFYMODAL_V2_CPU_MODEL_SNAPSHOT"] = "TRUE"
        self.assertTrue(_cpu_model_snapshot_enabled())


class NativeFastDiskUnetFlagPlumbingTests(unittest.TestCase):
    """Requirement 1: COMFYMODAL_V2_NATIVE_FAST_DISK_UNET plumbing."""

    def test_comfyapp_bakes_flag_from_caller_env_default_off(self) -> None:
        source = COMFYAPP_PATH.read_text(encoding="utf-8-sig")
        start = source.index("_V2_RUNTIME_ENV = {")
        end = source.index("_V2_RUNTIME_ENV.update(runtime_shape_config")
        runtime_env_block = source[start:end]
        self.assertIn(
            '"COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": os.environ.get(', runtime_env_block
        )
        self.assertIn('"COMFYMODAL_V2_NATIVE_FAST_DISK_UNET", "0"', runtime_env_block)

    def test_deploy_bat_pins_flag_default_off_and_prints_it(self) -> None:
        content = DEPLOY_BAT_PATH.read_text(encoding="utf-8-sig")
        self.assertIn(
            'if not defined COMFYMODAL_V2_NATIVE_FAST_DISK_UNET '
            'set "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=0"',
            content,
        )
        self.assertIn("echo native_fast_disk_unet=!COMFYMODAL_V2_NATIVE_FAST_DISK_UNET!", content)

    def test_run_bat_pins_flag_default_off_and_prints_it(self) -> None:
        content = RUN_BAT_PATH.read_text(encoding="utf-8-sig")
        self.assertIn(
            'if not defined COMFYMODAL_V2_NATIVE_FAST_DISK_UNET '
            'set "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=0"',
            content,
        )
        self.assertIn("echo native_fast_disk_unet=!COMFYMODAL_V2_NATIVE_FAST_DISK_UNET!", content)

    def test_deploy_bat_preserves_caller_activation_value(self) -> None:
        # The `if not defined` guard means a caller-provided '1' survives the
        # script, which is exactly how $env:COMFYMODAL_V2_NATIVE_FAST_DISK_UNET='1'
        # activates the flag before deploy_and_run_v2_single.bat runs.
        content = DEPLOY_BAT_PATH.read_text(encoding="utf-8-sig")
        self.assertIn(
            "if not defined COMFYMODAL_V2_NATIVE_FAST_DISK_UNET set",
            content,
        )
        self.assertNotIn('set "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=1"', content)


class OutputIdentityParityReuseTests(unittest.TestCase):
    """Requirement 3: reuse the harness's existing sha256 output identity.

    The harness already captures a deterministic output identity per image:
    ``asset_id`` is the bare sha256 and ``_read_remote_asset`` verifies the
    actual sha256 matches it during asset-proof fetch.  These existing
    primitives are exercised here for deterministic baseline parity; no new
    hashing or generation-behavior changes are introduced.
    """

    def test_extract_images_exposes_deterministic_sha256_identity(self) -> None:
        sha = hashlib.sha256(b"deterministic-baseline").hexdigest()
        result = {
            "images": [
                {"asset_id": sha, "backend_path": "output_assets/x.png", "file_ext": ".png"}
            ]
        }
        images = _extract_images(result)
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["asset_id"], sha)
        # sha256 hex digest: 64 lowercase hex chars.
        self.assertEqual(len(sha), 64)
        int(sha, 16)  # raises if not valid hex

    def test_extract_images_falls_back_to_trace_images(self) -> None:
        sha = hashlib.sha256(b"trace-baseline").hexdigest()
        # The harness falls back to trace.images only when result["images"] is
        # present but not a list (an absent key already returns []).
        result = {"images": "not-a-list", "trace": {"images": [{"asset_id": sha}]}}
        images = _extract_images(result)
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["asset_id"], sha)

    def test_read_remote_asset_proof_verifies_deterministic_sha(self) -> None:
        sha = "a" * 64

        def _remote(backend_path: str, expected_sha256: str) -> dict[str, Any]:
            return {"data": b"x", "sha256": sha, "byte_count": 1}

        handle = SimpleNamespace(read_output_asset=SimpleNamespace(remote=_remote))
        proof = asyncio.run(
            _read_remote_asset(handle, "output_assets/x.png", sha, timeout=5.0)
        )
        self.assertEqual(proof["expected_sha256"], sha)
        self.assertEqual(proof["actual_sha256"], sha)
        self.assertEqual(proof["byte_count"], 1)

    def test_read_remote_asset_proof_rejects_sha_mismatch(self) -> None:
        def _remote(backend_path: str, expected_sha256: str) -> dict[str, Any]:
            return {"data": b"x", "sha256": "b" * 64, "byte_count": 1}

        handle = SimpleNamespace(read_output_asset=SimpleNamespace(remote=_remote))
        with self.assertRaisesRegex(RuntimeError, "SHA mismatch"):
            asyncio.run(
                _read_remote_asset(handle, "output_assets/x.png", "a" * 64, timeout=5.0)
            )


if __name__ == "__main__":
    unittest.main()
