"""Tests for the UNET A/B runtime-state diagnostics in benchmark_v2_direct.py.

Exercises the _extract_unet_runtime_state_event helper and the
_run_ab_compare flow using synthetic trace data (no Modal dependency).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _make_trace_event(
    stage: str,
    unet_identity: str = "flux1-dev.safetensors",
    requested_weight_dtype: str = "fp8_e4m3fn",
    state: dict | None = None,
) -> dict:
    """Build a synthetic unet_runtime_state trace event dict."""
    return {
        "name": "unet_runtime_state",
        "metadata": {
            "stage": stage,
            "unet_identity": unet_identity,
            "requested_weight_dtype": requested_weight_dtype,
            "state": state or {
                "patcher_type": "ModelPatcher",
                "load_device": "cpu",
                "offload_device": "cpu",
                "weight_dtype": "fp8_e4m3fn",
            },
        },
    }


def _make_result(trace_events: list[dict]) -> dict:
    """Build a synthetic Modal response dict with trace events."""
    return {
        "trace": {
            "events": trace_events,
        },
    }


class TestExtractUnetRuntimeStateEvent(unittest.TestCase):
    """_extract_unet_runtime_state_event coverage."""

    def test_extract_found(self):
        from tools.benchmark_v2_direct import _extract_unet_runtime_state_event
        result = _make_result([
            _make_trace_event("snapshot_restored_post_retarget"),
        ])
        meta = _extract_unet_runtime_state_event(result, "snapshot_restored_post_retarget")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["stage"], "snapshot_restored_post_retarget")

    def test_extract_normal_loader_ready(self):
        from tools.benchmark_v2_direct import _extract_unet_runtime_state_event
        result = _make_result([
            _make_trace_event("normal_loader_ready"),
        ])
        meta = _extract_unet_runtime_state_event(result, "normal_loader_ready")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["stage"], "normal_loader_ready")

    def test_extract_wrong_stage_returns_none(self):
        from tools.benchmark_v2_direct import _extract_unet_runtime_state_event
        result = _make_result([
            _make_trace_event("snapshot_restored_post_retarget"),
        ])
        meta = _extract_unet_runtime_state_event(result, "normal_loader_ready")
        self.assertIsNone(meta)

    def test_extract_missing_events_returns_none(self):
        from tools.benchmark_v2_direct import _extract_unet_runtime_state_event
        result = _make_result([])
        meta = _extract_unet_runtime_state_event(result, "snapshot_restored_post_retarget")
        self.assertIsNone(meta)

    def test_extract_empty_result_returns_none(self):
        from tools.benchmark_v2_direct import _extract_unet_runtime_state_event
        meta = _extract_unet_runtime_state_event({}, "snapshot_restored_post_retarget")
        self.assertIsNone(meta)


# ── Shared synthetic state for A/B tests ──────────────────────────────


_SNAPSHOT_STATE = {
    "patcher_type": "ModelPatcher",
    "model_type": "UNetModel",
    "diffusion_model_type": "UNetModel",
    "patcher_object_id": "140000000000000",
    "model_object_id": "140000000000001",
    "diffusion_model_object_id": "140000000000002",
    "load_device": "cpu",
    "offload_device": "cpu",
    "current_device": "cpu",
    "first_parameter_device": "cpu",
    "first_parameter_dtype": "torch.float16",
    "first_buffer_device": "cpu",
    "first_buffer_dtype": "torch.float16",
    "model_dtype": "torch.float16",
    "manual_cast_dtype": "torch.float16",
    "weight_dtype": "fp8_e4m3fn",
    "model_options_keys": ["some_option"],
    "transformer_options_keys": ["some_transformer_opt"],
    "patch_count": "0",
    "object_patch_count": "0",
    "model_loaded_weight_memory": "1234567890",
    "model_lowvram": "False",
    "model_lowvram_patch_counter": "0",
    "forward_module": "UNetModel",
    "forward_qualname": "UNetModel.forward",
    "loaded_models_member": "1",
}

_NORMAL_STATE = dict(_SNAPSHOT_STATE)
_NORMAL_STATE["load_device"] = "cuda:0"
_NORMAL_STATE["offload_device"] = "cpu"
_NORMAL_STATE["current_device"] = "cuda:0"
_NORMAL_STATE["first_parameter_device"] = "cuda:0"
_NORMAL_STATE["first_buffer_device"] = "cuda:0"
_NORMAL_STATE["loaded_models_member"] = "1"
_NORMAL_STATE["patcher_object_id"] = "140111111111111"
_NORMAL_STATE["model_object_id"] = "140111111111112"
_NORMAL_STATE["diffusion_model_object_id"] = "140111111111113"


def _fake_run_one_reuse(**kwargs):
    """Synthetic _run_one that returns a reuse result with post-retarget state."""
    return {
        "result": _make_result([
            _make_trace_event(
                "snapshot_restored_post_retarget",
                state=_SNAPSHOT_STATE,
            ),
        ]),
    }


def _fake_run_one_bypass(**kwargs):
    """Synthetic _run_one that returns a bypass result with normal_loader_ready."""
    return {
        "result": _make_result([
            _make_trace_event(
                "normal_loader_ready",
                state=_NORMAL_STATE,
            ),
        ]),
    }


# ══════════════════════════════════════════════════════════════════════
# Tests: _run_ab_compare
# ══════════════════════════════════════════════════════════════════════


class TestRunABCompare(unittest.TestCase):
    """_run_ab_compare coverage with synthetic results."""

    def _run_ab(self, reuse_fake=None, bypass_fake=None) -> dict:
        from tools.benchmark_v2_direct import _run_ab_compare

        workflow = {"1": {"class_type": "KSampler", "inputs": {}}}
        modal_options = {}
        workspace = {"token_id": "fake", "token_secret": "fake"}
        transport = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            async def _run():
                reuse_val = reuse_fake if reuse_fake is not None else _fake_run_one_reuse()
                bypass_val = bypass_fake if bypass_fake is not None else _fake_run_one_bypass()

                async def _patched_run_one(**kw):
                    # Return the correct result based on call index
                    if not hasattr(_patched_run_one, "_call_count"):
                        _patched_run_one._call_count = 0
                    idx = _patched_run_one._call_count
                    _patched_run_one._call_count += 1
                    if idx == 0:
                        return reuse_val
                    return bypass_val

                with patch(
                    "tools.benchmark_v2_direct._run_one",
                    new=_patched_run_one,
                ):
                    return await _run_ab_compare(
                        workflow=workflow,
                        modal_options=modal_options,
                        workspace=workspace,
                        transport=transport,
                        output_dir=output_dir,
                    )

            return asyncio.run(_run())

    def test_ab_diff_produced(self):
        """Matching identity and dtype produces a diff with expected fields."""
        result = self._run_ab()
        self.assertIn("diff", result)
        self.assertIn("reuse_state", result)
        self.assertIn("bypass_state", result)
        self.assertIn("field_count", result)
        self.assertGreater(result["field_count"], 0)

    def test_ab_diff_contains_load_device(self):
        """load_device change is captured in the diff."""
        result = self._run_ab()
        diff = result["diff"]
        self.assertIn("load_device", diff)
        self.assertEqual(diff["load_device"]["snapshot"], "cpu")
        self.assertEqual(diff["load_device"]["normal"], "cuda:0")

    def test_ab_diff_excludes_object_ids(self):
        """Object IDs differ but are excluded from semantic diff."""
        result = self._run_ab()
        diff = result["diff"]
        self.assertNotIn("patcher_object_id", diff)
        self.assertNotIn("model_object_id", diff)
        self.assertNotIn("diffusion_model_object_id", diff)

    def test_ab_diff_zero_field_count_when_identical_states(self):
        """field_count=0 when only object IDs differ."""
        from tools.benchmark_v2_direct import _run_ab_compare

        workflow = {"1": {"class_type": "KSampler", "inputs": {}}}
        modal_options = {}
        workspace = {"token_id": "fake", "token_secret": "fake"}
        transport = MagicMock()

        identical_state = dict(_SNAPSHOT_STATE)

        _identical_reuse = {
            "result": _make_result([
                _make_trace_event(
                    "snapshot_restored_post_retarget",
                    state=identical_state,
                ),
            ]),
        }
        _identical_bypass = {
            "result": _make_result([
                _make_trace_event(
                    "normal_loader_ready",
                    state=identical_state,
                ),
            ]),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            async def _run():
                call_count = 0
                async def _patched_both(**kw):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return _identical_reuse
                    return _identical_bypass

                with patch(
                    "tools.benchmark_v2_direct._run_one",
                    new=_patched_both,
                ):
                    return await _run_ab_compare(
                        workflow=workflow,
                        modal_options=modal_options,
                        workspace=workspace,
                        transport=transport,
                        output_dir=output_dir,
                    )

            result = asyncio.run(_run())
        self.assertEqual(result["field_count"], 0)
        self.assertEqual(result["diff"], {})
        self.assertIn("reuse_state", result)
        self.assertIn("bypass_state", result)

    def test_ab_diff_different_unet_identity_raises(self):
        """Different UNET identities raise RuntimeError."""

        def _reuse_diff_identity(**kw):
            return {
                "result": _make_result([
                    _make_trace_event(
                        "snapshot_restored_post_retarget",
                        unet_identity="model_a.safetensors",
                        state=_SNAPSHOT_STATE,
                    ),
                ]),
            }

        def _bypass_diff_identity(**kw):
            return {
                "result": _make_result([
                    _make_trace_event(
                        "normal_loader_ready",
                        unet_identity="model_b.safetensors",
                        state=_NORMAL_STATE,
                    ),
                ]),
            }

        with self.assertRaises(RuntimeError) as ctx:
            self._run_ab(reuse_fake=_reuse_diff_identity(), bypass_fake=_bypass_diff_identity())
        self.assertIn("UNET identity mismatch", str(ctx.exception))

    def test_ab_diff_different_weight_dtype_raises(self):
        """Different requested_weight_dtype raise RuntimeError."""

        def _reuse_diff_wd(**kw):
            return {
                "result": _make_result([
                    _make_trace_event(
                        "snapshot_restored_post_retarget",
                        requested_weight_dtype="fp8_e4m3fn",
                        state=_SNAPSHOT_STATE,
                    ),
                ]),
            }

        def _bypass_diff_wd(**kw):
            return {
                "result": _make_result([
                    _make_trace_event(
                        "normal_loader_ready",
                        requested_weight_dtype="default",
                        state=_NORMAL_STATE,
                    ),
                ]),
            }

        with self.assertRaises(RuntimeError) as ctx:
            self._run_ab(reuse_fake=_reuse_diff_wd(), bypass_fake=_bypass_diff_wd())
        self.assertIn("weight_dtype mismatch", str(ctx.exception))

    def test_ab_missing_reuse_event_raises(self):
        """Missing snapshot_restored_post_retarget raises RuntimeError."""

        def _reuse_no_event(**kw):
            return {"result": _make_result([])}

        with self.assertRaises(RuntimeError) as ctx:
            self._run_ab(reuse_fake=_reuse_no_event())
        self.assertIn("snapshot_restored_post_retarget", str(ctx.exception))

    def test_ab_missing_bypass_event_raises(self):
        """Missing normal_loader_ready raises RuntimeError."""

        def _bypass_no_event(**kw):
            return {"result": _make_result([])}

        with self.assertRaises(RuntimeError) as ctx:
            self._run_ab(bypass_fake=_bypass_no_event())
        self.assertIn("normal_loader_ready", str(ctx.exception))

    def test_ab_saves_diff_json(self):
        """unet_runtime_diff.json contains reuse_state, bypass_state, diff, field_count."""
        from tools.benchmark_v2_direct import _run_ab_compare

        workflow = {"1": {"class_type": "KSampler", "inputs": {}}}
        modal_options = {}
        workspace = {"token_id": "fake", "token_secret": "fake"}
        transport = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            async def _run():
                call_count = 0
                async def _patched(**kw):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return _fake_run_one_reuse()
                    return _fake_run_one_bypass()

                with patch(
                    "tools.benchmark_v2_direct._run_one",
                    new=_patched,
                ):
                    return await _run_ab_compare(
                        workflow=workflow,
                        modal_options=modal_options,
                        workspace=workspace,
                        transport=transport,
                        output_dir=output_dir,
                    )

            result = asyncio.run(_run())

            diff_path = output_dir / "unet_runtime_diff.json"
            self.assertTrue(diff_path.exists(), f"File not found: {diff_path}")

            with open(diff_path, "r") as f:
                saved = json.load(f)

            self.assertIn("reuse_state", saved)
            self.assertIn("bypass_state", saved)
            self.assertIn("diff", saved)
            self.assertIn("field_count", saved)
            self.assertEqual(saved["field_count"], result["field_count"])
            self.assertEqual(saved["diff"], result["diff"])
            self.assertEqual(saved["reuse_state"], result["reuse_state"])
            self.assertEqual(saved["bypass_state"], result["bypass_state"])


class TestLoadUnetEmitsToBridgeTrace(unittest.TestCase):
    """_load_unet emits to self._trace when _ACTIVE_REQUEST_TRACE is empty."""

    def setUp(self):
        # Clear the context var
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE
        self._token = _ACTIVE_REQUEST_TRACE.set(None)
        from comfymodal_runtime.contracts import ModelRestoreKey
        self._model_key = ModelRestoreKey(
            unet_identity="test.safetensors",
            clip_identity="",
            clip_type="sd",
        )
        # Stash _original_methods so we can run _load_unet without real nodes
        from comfymodal_runtime.model_preload import V2LoaderBridge
        self._bridge = V2LoaderBridge()
        self._bridge._original_methods = {"UNETLoader.load_unet": lambda self, unet_name, weight_dtype: (object(),)}
        self._bridge._model_spec = {
            "loaders": {
                "unet": [{"unet_name": "test.safetensors", "weight_dtype": "default"}],
                "clip": [],
            },
        }
        self._bridge._model_key = self._model_key

    def tearDown(self):
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE
        _ACTIVE_REQUEST_TRACE.reset(self._token)

    def test_emits_to_self_trace_when_no_request_trace(self):
        """When _ACTIVE_REQUEST_TRACE is None, _load_unet uses self._trace."""
        from comfymodal_runtime.trace import RuntimeTrace
        from types import SimpleNamespace

        bridge_trace = RuntimeTrace(request_id="bridge-test", process="remote")
        self._bridge._trace = bridge_trace

        fake_unet = SimpleNamespace(
            model=SimpleNamespace(
                diffusion_model=SimpleNamespace(
                    named_parameters=lambda recurse=True: iter([]),
                    named_buffers=lambda recurse=True: iter([]),
                    forward=lambda x: x,
                ),
                named_parameters=lambda recurse=True: iter([]),
                named_buffers=lambda recurse=True: iter([]),
                device="cpu",
            ),
            load_device="cpu",
            offload_device="cpu",
            weight_dtype="default",
        )

        original_invoke = self._bridge._invoke_original

        def _fake_invoke(class_name, kwargs):
            return (fake_unet,)

        self._bridge._invoke_original = _fake_invoke
        try:
            try:
                self._bridge._load_unet(self._model_key)
            except Exception:
                pass
            event_names = [e.name for e in bridge_trace.events]
            self.assertIn(
                "unet_runtime_state",
                event_names,
                msg=f"Expected unet_runtime_state in bridge trace events, got {event_names}",
            )
        finally:
            self._bridge._invoke_original = original_invoke
