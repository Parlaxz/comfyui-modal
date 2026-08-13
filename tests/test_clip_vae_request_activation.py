"""Focused tests for the UNET-absent ``clip_vae`` request-time clip-only
bridge activation (modal_app) and the deep-profile env baking (comfyapp).
Integration/config scope only — no code outside those two modules."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import comfyapp
import comfymodal_runtime.model_preload as mp
import comfymodal_runtime.modal_app as ma
from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey
from comfymodal_runtime.trace import RuntimeTrace

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))

_CLIP_VAE_ENV = {
    "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "1",
    "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "clip_vae",
}


def _clip_vae_models(clip: Any = None, vae: Any = None) -> SimpleNamespace:
    return SimpleNamespace(clip=clip, unet=None, vae=vae)


def _model_key() -> ModelRestoreKey:
    return ModelRestoreKey(
        unet_identity="unet.safetensors",
        clip_identity="clip.safetensors",
        clip_type="flux",
    )


def _prefill_key() -> PrefillKey:
    return PrefillKey(
        model_key=_model_key(),
        prompt_bundle_hash="bundle-clip-vae",
        encode_options={
            "eligible": True,
            "encodes": [{"node_id": "6", "text": "a cat", "role": "positive"}],
        },
    )


def _model_spec() -> dict:
    return {
        "loaders": {
            "unet": [{"unet_name": "unet.safetensors"}],
            "clip": [{"clip_name": "clip.safetensors", "type": "flux"}],
        }
    }


def _bridge() -> mp.V2LoaderBridge:
    bridge = mp.V2LoaderBridge(max_workers=2)
    bridge.install = lambda nodes=None, trace=None: True
    bridge.coordinator.clip_loader = lambda k: SimpleNamespace(patcher=SimpleNamespace())
    bridge.coordinator.unet_loader = lambda k: "unet-loaded"
    return bridge


class TestClipVaeArchitectureGuard:
    """``_snapshot_is_clip_vae_unet_absent`` exact architecture guard."""

    def test_guard_true_for_unet_absent_clip_vae(self):
        models = _clip_vae_models(clip=object(), vae=object())
        with patch.dict(os.environ, _CLIP_VAE_ENV):
            assert ma._snapshot_is_clip_vae_unet_absent(models) is True

    def test_guard_false_for_both_present(self):
        models = SimpleNamespace(clip=object(), unet=object(), vae=object())
        with patch.dict(os.environ, _CLIP_VAE_ENV):
            assert ma._snapshot_is_clip_vae_unet_absent(models) is False

    def test_guard_false_when_exclude_unet_gate_off(self):
        models = _clip_vae_models(clip=object(), vae=object())
        with patch.dict(os.environ, {"COMFYMODAL_V2_EVICT_RETAIN_ROLE": "clip_vae"}):
            assert ma._snapshot_is_clip_vae_unet_absent(models) is False

    def test_guard_false_when_retain_role_not_clip_vae(self):
        models = _clip_vae_models(clip=object(), vae=object())
        with patch.dict(os.environ, {"COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "1"}):
            assert ma._snapshot_is_clip_vae_unet_absent(models) is False

    def test_guard_false_when_clip_missing(self):
        with patch.dict(os.environ, _CLIP_VAE_ENV):
            assert ma._snapshot_is_clip_vae_unet_absent(_clip_vae_models(clip=None, vae=object())) is False

    def test_guard_false_when_vae_missing(self):
        with patch.dict(os.environ, _CLIP_VAE_ENV):
            assert ma._snapshot_is_clip_vae_unet_absent(_clip_vae_models(clip=object(), vae=None)) is False

    def test_guard_false_when_models_none(self):
        with patch.dict(os.environ, _CLIP_VAE_ENV):
            assert ma._snapshot_is_clip_vae_unet_absent(None) is False


class TestClipOnlyBridgePreparation:
    """Completed clip_future, no unet_future, exact VAE, prefill consume,
    and native UNET fallback."""

    def test_clip_only_preparation_prefill_and_unet_fallback(self):
        clip_obj = SimpleNamespace(patcher=SimpleNamespace())
        vae_obj = object()
        encode_calls: list[str] = []
        bridge = _bridge()

        def tracking_encode(class_name: str, kwargs: dict) -> tuple:
            encode_calls.append(kwargs.get("text", ""))
            return (f"conditioning:{kwargs['text']}",)

        bridge._invoke_original = tracking_encode
        trace = RuntimeTrace(request_id="cv-bridge", process="remote")

        prep = bridge.use_ready_clip(
            model_key=_model_key(),
            prefill_key=_prefill_key(),
            model_spec=_model_spec(),
            clip=clip_obj,
            trace=trace,
        )
        bridge.set_exact_vae(vae_obj)

        assert prep.clip_future is not None and prep.clip_future.done()
        assert prep.clip_future.result() is clip_obj
        assert prep.unet_future is None
        assert bridge._exact_vae is vae_obj
        assert bridge.coordinator.pending_lane_count() == 0

        with patch.object(mp, "get_exact_conditioning_cache", return_value=None):
            assert bridge.schedule_execution_prefill(trace=trace) is True
            result = bridge._consume_prefill((), {"clip": clip_obj, "text": "a cat"})

        assert result is not mp._LOADER_MISS
        assert result == ("conditioning:a cat",)
        assert encode_calls == ["a cat"], "graph consumption must not re-encode"

        # Graph UNETLoader continues through the existing original-loader
        # fallback (no unet_future / no UNET lane on the bridge).
        assert bridge._consume_unet(("unet.safetensors", "default"), {}) is mp._LOADER_MISS
        bridge.coordinator.close()


class TestClipVaeRequestActivation:
    """``_activate_clip_vae_only_request_binding`` + CLIP/VAE retarget."""

    def _entry(self, models: Any, bridge: mp.V2LoaderBridge) -> SimpleNamespace:
        entry = SimpleNamespace(
            _cpu_snapshot_models=models,
            _preload_bridge=bridge,
            _cpu_snapshot_models_active=False,
        )
        entry._retarget_cpu_snapshot_clip_vae_for_request = lambda *, trace=None: None
        return entry

    def test_binding_activates_and_binds_exact_objects(self):
        clip_obj = SimpleNamespace(patcher=SimpleNamespace())
        vae_obj = object()
        bridge = _bridge()
        entry = self._entry(_clip_vae_models(clip=clip_obj, vae=vae_obj), bridge)

        with patch.dict(os.environ, _CLIP_VAE_ENV):
            ma.ModalRuntimeEntrypoint._activate_clip_vae_only_request_binding(
                entry,
                request_model_key=_model_key(),
                request_prefill_key=_prefill_key(),
                request_model_spec=_model_spec(),
            )

        assert entry._cpu_snapshot_models_active is True
        prep = bridge._preparation
        assert prep is not None
        assert prep.clip_future.done() and prep.clip_future.result() is clip_obj
        assert prep.unet_future is None
        assert bridge._exact_vae is vae_obj
        bridge.coordinator.close()

    def test_retarget_clip_vae_uses_same_policy_no_unet(self):
        clip_patcher = SimpleNamespace(load_device=None, offload_device=None)
        vae_patcher = SimpleNamespace(load_device=None, offload_device=None)
        vae = SimpleNamespace(patcher=vae_patcher, device=None)
        models = SimpleNamespace(
            clip=SimpleNamespace(patcher=clip_patcher),
            unet=None,
            vae=vae,
        )
        mm = SimpleNamespace(
            text_encoder_device=lambda: "cuda:0",
            text_encoder_offload_device=lambda: "cpu",
            vae_device=lambda: "cuda:0",
            vae_offload_device=lambda: "cpu",
        )
        entry = SimpleNamespace(_cpu_snapshot_models=models)
        ma.ModalRuntimeEntrypoint._retarget_cpu_snapshot_clip_vae_for_request(
            entry, model_management=mm,
        )
        assert clip_patcher.load_device == "cuda:0"
        assert clip_patcher.offload_device == "cpu"
        assert vae_patcher.load_device == "cuda:0"
        assert vae_patcher.offload_device == "cpu"
        assert vae.device == "cuda:0"
        assert not hasattr(models, "unet_devices_touched")

    def test_invalid_states_fail_closed(self):
        for models in (
            _clip_vae_models(clip=None, vae=object()),
            _clip_vae_models(clip=object(), vae=None),
        ):
            bridge = _bridge()
            entry = self._entry(models, bridge)
            with patch.dict(os.environ, _CLIP_VAE_ENV):
                try:
                    ma.ModalRuntimeEntrypoint._activate_clip_vae_only_request_binding(
                        entry,
                        request_model_key=_model_key(),
                        request_prefill_key=_prefill_key(),
                        request_model_spec=_model_spec(),
                    )
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("clip_vae binding must fail closed on invalid state")
            assert entry._cpu_snapshot_models_active is False
            bridge.coordinator.close()

    def test_gate_off_fails_closed(self):
        clip_obj = SimpleNamespace(patcher=SimpleNamespace())
        bridge = _bridge()
        entry = self._entry(_clip_vae_models(clip=clip_obj, vae=object()), bridge)
        with patch.dict(os.environ, {"COMFYMODAL_V2_EVICT_RETAIN_ROLE": "clip_vae"}):
            try:
                ma.ModalRuntimeEntrypoint._activate_clip_vae_only_request_binding(
                    entry,
                    request_model_key=_model_key(),
                    request_prefill_key=_prefill_key(),
                    request_model_spec=_model_spec(),
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("clip_vae binding must fail closed when exclude-UNET gate is off")
        assert entry._cpu_snapshot_models_active is False
        bridge.coordinator.close()


class TestActivationInvariant:
    """Invariant reports active clip-only bind: cpu_snapshot_container_active=1,
    loader_bridge_active=1, unet_present=0, clip present, VAE bound."""

    def test_invariant_reports_clip_vae_active_state(self):
        entry = SimpleNamespace(
            _cpu_snapshot_models=_clip_vae_models(clip=object(), vae=object()),
            _cpu_snapshot_models_active=True,
            _preload_bridge=SimpleNamespace(_preparation=object()),
        )
        with patch.dict(os.environ, {"COMFYMODAL_V2_ENV_PROFILE": "inherit"}):
            rec = ma.ModalRuntimeEntrypoint._enforce_snapshot_activation_invariant(
                entry, request_id="cv-invariant", trace=None,
            )
        assert rec["cpu_snapshot_container_active"] == 1
        assert rec["loader_bridge_active"] == 1
        assert rec["unet_present"] == 0
        assert rec["clip_present"] == 1
        assert rec["models_container_present"] == 1
        assert rec["status"] == "pass"

    def test_invariant_pass_when_clip_vae_inactive_unet_absent(self):
        entry = SimpleNamespace(
            _cpu_snapshot_models=_clip_vae_models(clip=object(), vae=object()),
            _cpu_snapshot_models_active=False,
            _preload_bridge=SimpleNamespace(_preparation=None),
        )
        with patch.dict(os.environ, {"COMFYMODAL_V2_ENV_PROFILE": "production"}):
            rec = ma.ModalRuntimeEntrypoint._enforce_snapshot_activation_invariant(
                entry, request_id="cv-inactive", trace=None,
            )
        assert rec["status"] == "pass"
        assert rec["unet_present"] == 0


class TestDeepProfileEnvBaking:
    """COMFYMODAL_SAMPLING_DEEP_PROFILE baked like the native-fast-disk flag,
    default off, profiler module untouched."""

    def test_runtime_env_defaults_off(self):
        assert comfyapp._V2_RUNTIME_ENV.get("COMFYMODAL_SAMPLING_DEEP_PROFILE") == "off"

    def test_runtime_env_bakes_blocks_from_caller_env(self):
        code = (
            "import os; "
            "os.environ['COMFYMODAL_SAMPLING_DEEP_PROFILE']='blocks'; "
            "import comfyapp; "
            "print(comfyapp._V2_RUNTIME_ENV['COMFYMODAL_SAMPLING_DEEP_PROFILE'])"
        )
        out = subprocess.check_output(
            [sys.executable, "-c", code],
            cwd=_PROJECT_ROOT,
            env={
                **os.environ,
                "PYTHONPATH": _PROJECT_ROOT
                + os.pathsep
                + os.environ.get("PYTHONPATH", ""),
            },
            text=True,
            timeout=240,
        )
        assert out.strip().splitlines()[-1] == "blocks"

    def test_profiler_module_untouched(self):
        from comfymodal_runtime import sampling_deep_profile as sdp

        assert sdp.FLAG_ENV == "COMFYMODAL_SAMPLING_DEEP_PROFILE"
        assert sdp._DEFAULT_LEVEL == "off"
        assert sdp._VALID_LEVELS == frozenset({"off", "steps", "blocks"})
        source = Path(sdp.__file__).read_text(encoding="utf-8")
        assert "_V2_RUNTIME_ENV" not in source
