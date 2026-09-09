"""Focused offline contracts for the RA5 request-local attention selector."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import torch

from comfymodal_runtime import golden_serial as gs
from comfymodal_runtime import modal_app
from comfymodal_runtime import runtime_bootstrap as rbm
from comfyapp import (
    _ComfyAPIMixin,
    build_sage_runtime_identity,
    patch_kjnodes_get_sage_func,
)


def test_request_attention_backend_is_normalized_and_validated():
    omitted = gs.GoldenRequest("r-omitted", {})
    assert omitted.attention_backend is None
    omitted_session = gs.GoldenSession(omitted, volume=object())
    assert omitted_session.run_identity["attention_backend"] is None

    request = gs.GoldenRequest("r", {}, attention_backend=" SAGE ")
    assert request.attention_backend == "sage"
    session = gs.GoldenSession(request, volume=object())
    assert session.run_identity["attention_backend"] == "sage"
    assert session.recorder.to_json_dict()["run_identity"] == session.run_identity
    for value in ("flash", "", 1):
        with pytest.raises(ValueError):
            gs.GoldenRequest("r", {}, attention_backend=value)


def test_selector_is_mutually_exclusive_and_restores_previous_override():
    previous = lambda *_args, **_kwargs: "previous"
    patcher = SimpleNamespace(model_options={
        "transformer_options": {"optimized_attention_override": previous, "keep": 1}
    })
    fake_attention = types.ModuleType("comfy.ldm.modules.attention")
    fake_attention.attention_pytorch = lambda *args, **kwargs: "pytorch"
    with patch.dict(sys.modules, {"comfy.ldm.modules.attention": fake_attention}):
        with gs.attention_backend_scope(patcher, "pytorch") as state:
            override = patcher.model_options["transformer_options"]["optimized_attention_override"]
            assert override is not previous
            assert override(None, torch.ones(1), torch.ones(1), torch.ones(1), 1) == "pytorch"
            assert state["requested_backend"] == "pytorch"
        assert state["calls"] == 1
        assert patcher.model_options["transformer_options"]["optimized_attention_override"] is previous
        assert patcher.model_options["transformer_options"]["keep"] == 1


def test_sampler_scope_targets_cached_model_clone_and_restores_both_patchers():
    seeded_previous = lambda *_args, **_kwargs: "seeded"
    clone_previous = lambda *_args, **_kwargs: "clone"
    seeded = SimpleNamespace(model_options={
        "transformer_options": {
            "optimized_attention_override": seeded_previous,
            "seeded_keep": True,
        }
    })
    clone = SimpleNamespace(model_options={
        "transformer_options": {
            "optimized_attention_override": clone_previous,
            "clone_keep": True,
        }
    })
    runner = SimpleNamespace(
        prompt={"sampler": {"inputs": {"model": ["wrapper", 0]}}},
        cache={"wrapper": gs._CacheEntry(outputs=[[clone]])},
    )
    session = SimpleNamespace(
        patcher=seeded,
        runner=runner,
        node_map=SimpleNamespace(sampler_id="sampler"),
    )

    fake_attention = types.ModuleType("comfy.ldm.modules.attention")
    fake_attention.attention_pytorch = lambda *args, **kwargs: "pytorch"
    with patch.dict(sys.modules, {"comfy.ldm.modules.attention": fake_attention}):
        bound = gs._sampler_bound_patcher(session)
        assert bound is clone
        with gs.attention_backend_scope(bound, "pytorch"):
            assert (
                clone.model_options["transformer_options"]["optimized_attention_override"]
                is not clone_previous
            )
            assert (
                seeded.model_options["transformer_options"]["optimized_attention_override"]
                is seeded_previous
            )

    assert clone.model_options["transformer_options"]["optimized_attention_override"] is clone_previous
    assert seeded.model_options["transformer_options"]["optimized_attention_override"] is seeded_previous
    assert clone.model_options["transformer_options"]["clone_keep"] is True
    assert seeded.model_options["transformer_options"]["seeded_keep"] is True


def test_sampler_bound_patcher_falls_back_to_seeded_patcher_without_clone():
    seeded = object()
    session = SimpleNamespace(
        patcher=seeded,
        runner=SimpleNamespace(
            prompt={"sampler": {"inputs": {}}},
            cache={},
        ),
        node_map=SimpleNamespace(sampler_id="sampler"),
    )
    assert gs._sampler_bound_patcher(session) is seeded


def test_golden_sampling_scopes_sampler_bound_clone_not_seeded_patcher():
    seeded_previous = lambda *_args, **_kwargs: "seeded"
    clone_previous = lambda *_args, **_kwargs: "clone"
    seeded = SimpleNamespace(model_options={
        "transformer_options": {"optimized_attention_override": seeded_previous}
    })
    clone = SimpleNamespace(model_options={
        "transformer_options": {"optimized_attention_override": clone_previous}
    })
    prompt = {"sampler": {"inputs": {"model": ["wrapper", 0]}}}
    observed = {}

    class Runner:
        def __init__(self):
            self.prompt = prompt
            self.cache = {"wrapper": gs._CacheEntry(outputs=[[clone]])}
            self.executed = []
            self._golden_futures = set()

        def begin_scope(self, _allowed):
            pass

        def end_scope(self):
            pass

        async def run_closure(self, target_id, *, include_target):
            assert include_target is True
            observed["override"] = clone.model_options["transformer_options"][
                "optimized_attention_override"
            ]
            self.executed.append({
                "node_id": target_id,
                "class_type": "Sampler",
                "stage_class": "sampling",
            })
            self.cache[target_id] = gs._CacheEntry(outputs=[["latent"]])
            return [
                (item["node_id"], item["class_type"], item["stage_class"])
                for item in self.executed
            ]

    runner = Runner()
    session = SimpleNamespace(
        recorder=gs.GoldenTelemetryRecorder(),
        request=SimpleNamespace(
            request_id="r",
            prompt=prompt,
            attention_backend="pytorch",
        ),
        contract=SimpleNamespace(sampler_class_type="Sampler"),
        node_map=SimpleNamespace(sampler_id="sampler"),
        runner=runner,
        patcher=seeded,
    )
    fake_attention = types.ModuleType("comfy.ldm.modules.attention")
    fake_attention.attention_pytorch = lambda *args, **kwargs: "pytorch"
    fake_runtime = SimpleNamespace(ensure_sampling_timing_wrapper=lambda _patcher: False)
    real_import = gs.importlib.import_module

    def import_module(name, *args, **kwargs):
        if name == "comfymodal_runtime.runtime_executor":
            return fake_runtime
        if name == "comfymodal_runtime.sampling_deep_profile":
            raise ImportError("offline test")
        return real_import(name, *args, **kwargs)

    with patch.dict(sys.modules, {"comfy.ldm.modules.attention": fake_attention}), \
         patch.object(gs.importlib, "import_module", side_effect=import_module):
        assert asyncio.run(gs.golden_sampling(session)) == [["latent"]]

    assert observed["override"] is not clone_previous
    assert seeded.model_options["transformer_options"]["optimized_attention_override"] is seeded_previous
    assert clone.model_options["transformer_options"]["optimized_attention_override"] is clone_previous


def test_golden_sampling_omitted_backend_preserves_existing_override_and_runs():
    existing_calls = []

    def existing_override(*args, **kwargs):
        existing_calls.append((args, kwargs))
        return "existing"

    patcher = SimpleNamespace(model_options={
        "transformer_options": {"optimized_attention_override": existing_override}
    })
    prompt = {"sampler": {"inputs": {}}}

    class Runner:
        def __init__(self):
            self.prompt = prompt
            self.cache = {}
            self.executed = []
            self._golden_futures = set()

        def begin_scope(self, _allowed):
            pass

        def end_scope(self):
            pass

        async def run_closure(self, target_id, *, include_target):
            assert include_target is True
            override = patcher.model_options["transformer_options"][
                "optimized_attention_override"
            ]
            assert override is existing_override
            assert override(None, "q", "k", "v", 1) == "existing"
            self.executed.append({
                "node_id": target_id,
                "class_type": "Sampler",
                "stage_class": "sampling",
            })
            self.cache[target_id] = gs._CacheEntry(outputs=[["latent"]])
            return [(target_id, "Sampler", "sampling")]

    runner = Runner()
    session = SimpleNamespace(
        recorder=gs.GoldenTelemetryRecorder(),
        request=SimpleNamespace(request_id="r", prompt=prompt),
        contract=SimpleNamespace(sampler_class_type="Sampler"),
        node_map=SimpleNamespace(sampler_id="sampler"),
        runner=runner,
        patcher=patcher,
    )
    fake_runtime = SimpleNamespace(ensure_sampling_timing_wrapper=lambda _patcher: False)
    real_import = gs.importlib.import_module

    def import_module(name, *args, **kwargs):
        if name == "comfymodal_runtime.runtime_executor":
            return fake_runtime
        if name == "comfymodal_runtime.sampling_deep_profile":
            raise ImportError("offline test")
        return real_import(name, *args, **kwargs)

    with patch.object(gs.importlib, "import_module", side_effect=import_module), \
         patch.object(gs, "attention_backend_scope", side_effect=AssertionError("scope must be omitted")):
        assert asyncio.run(gs.golden_sampling(session)) == [["latent"]]

    assert existing_calls
    assert patcher.model_options["transformer_options"][
        "optimized_attention_override"
    ] is existing_override
    selection = next(
        event for event in session.recorder.events
        if event["name"] == "attention_backend_selection"
    )
    assert selection["fields"]["requested_backend"] is None
    assert selection["fields"]["override_applied"] is False


def test_sage_scope_routes_public_dispatcher_and_does_not_touch_clip_or_vae():
    calls = []

    def sageattn(q, k, v, **kwargs):
        calls.append(kwargs)
        return q

    fake_sage = types.ModuleType("sageattention")
    fake_sage.sageattn = sageattn
    clip = object()
    vae = object()
    patcher = SimpleNamespace(model_options={"transformer_options": {}})
    with patch.dict(sys.modules, {"sageattention": fake_sage}):
        with gs.attention_backend_scope(patcher, "sage") as state:
            out = patcher.model_options["transformer_options"]["optimized_attention_override"](
                None, torch.ones(1, 2, 3, 4), torch.ones(1, 2, 3, 4),
                torch.ones(1, 2, 3, 4), 2, skip_reshape=True,
            )
            assert tuple(out.shape) == (1, 3, 8)
            assert state["selected_callable"] == "sageattention.sageattn"
        assert calls[0]["tensor_layout"] == "HND"
    assert clip is not None and vae is not None


def test_sage_scope_maps_comfy_scale_only_to_public_sm_scale():
    calls = []

    def sageattn(q, k, v, *, tensor_layout, is_causal, sm_scale):
        calls.append({
            "tensor_layout": tensor_layout,
            "is_causal": is_causal,
            "sm_scale": sm_scale,
        })
        return q

    fake_sage = types.ModuleType("sageattention")
    fake_sage.sageattn = sageattn
    patcher = SimpleNamespace(model_options={"transformer_options": {}})
    q = torch.ones(1, 2, 3, 4, dtype=torch.bfloat16)
    with patch.dict(sys.modules, {"sageattention": fake_sage}):
        with gs.attention_backend_scope(patcher, "sage"):
            out = patcher.model_options["transformer_options"][
                "optimized_attention_override"
            ](None, q, q, q, 2, skip_reshape=True, skip_output_reshape=True, scale=0.25)
    assert tuple(out.shape) == tuple(q.shape)
    assert calls == [{"tensor_layout": "HND", "is_causal": False, "sm_scale": 0.25}]


def test_sage_scope_rejects_masks_and_gqa_before_native_dispatch():
    native_calls = []

    def sageattn(q, k, v, **kwargs):
        native_calls.append(kwargs)
        return q

    fake_sage = types.ModuleType("sageattention")
    fake_sage.sageattn = sageattn
    patcher = SimpleNamespace(model_options={"transformer_options": {}})
    q = torch.ones(1, 2, 3, 4)
    with patch.dict(sys.modules, {"sageattention": fake_sage}):
        with gs.attention_backend_scope(patcher, "sage"):
            override = patcher.model_options["transformer_options"][
                "optimized_attention_override"
            ]
            with pytest.raises(gs.AttentionBackendValidationError, match="mask"):
                override(None, q, q, q, 2, mask=torch.ones(1, 2, 3, 3), skip_reshape=True)
            k = torch.ones(1, 1, 3, 4)
            with pytest.raises(gs.AttentionBackendValidationError, match="gqa"):
                override(None, q, k, k, 2, skip_reshape=True)
    assert native_calls == []


def test_sage_scope_rejects_scale_when_public_callable_does_not_name_sm_scale():
    fake_sage = types.ModuleType("sageattention")
    fake_sage.sageattn = lambda q, k, v, **kwargs: q
    patcher = SimpleNamespace(model_options={"transformer_options": {}})
    q = torch.ones(1, 2, 3, 4)
    with patch.dict(sys.modules, {"sageattention": fake_sage}):
        with gs.attention_backend_scope(patcher, "sage"):
            override = patcher.model_options["transformer_options"][
                "optimized_attention_override"
            ]
            with pytest.raises(gs.AttentionBackendValidationError, match="sm_scale"):
                override(None, q, q, q, 2, skip_reshape=True, scale=0.25)


def test_kitchen_unavailability_is_rejected_without_fallback():
    patcher = SimpleNamespace(model_options={"transformer_options": {}})
    with patch.dict(sys.modules, {"comfy.ldm.modules.attention": types.ModuleType("attention")}, clear=False):
        with pytest.raises(gs.AttentionBackendValidationError, match="kitchen_attention_unavailable"):
            with gs.attention_backend_scope(patcher, "comfy_kitchen"):
                pass


def test_diagnostic_pytorch_fallback_is_rejected_for_sage():
    artifact = {"attention_backend": {
        "dispatch_counts": {"pytorch_override": 0, "sage_override": 1},
        "pytorch_sdpa_calls": 1,
    }}
    with pytest.raises(gs.AttentionBackendValidationError, match="fallback_or_wrong_backend:sage"):
        gs.validate_attention_backend_diagnostics("sage", artifact)


def test_golden_restore_forces_sage_selection_after_cuda_even_on_identity_match():
    calls = []
    bootstrap = rbm.RuntimeBootstrap(
        restore_gpu_state=lambda: calls.append("gpu"),
        initialize_cuda=lambda: calls.append("cuda"),
        select_sage_runtime_mode=lambda: calls.append("select") or {
            "mode": "baked_cuda", "reason": "fresh", "identity": {"digest": "x"}
        },
        apply_sage_policy=lambda: calls.append("apply") or True,
    )
    bootstrap.state.snapshot_sage_identity = {"module_name": "snapshot"}
    with patch.object(rbm, "_verify_sage_snapshot_identity", return_value=True):
        bootstrap.restore()
    assert calls[:4] == ["gpu", "cuda", "select", "apply"]
    assert bootstrap.state.sage_runtime_identity == {"digest": "x"}
    assert bootstrap.state.restore_stage_classifications["sage_policy"] == "restored"


def test_golden_profile_installs_restore_sage_callbacks_without_backend_override():
    api = SimpleNamespace(
        _sage_runtime_mode="triton_fallback",
        _sage_runtime_reason="snapshot",
        _select_sage_runtime_mode=lambda: None,
        _apply_sage_attention_policy=lambda: None,
    )

    class CapturingBootstrap:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._load_legacy_runtime = lambda: api
    entrypoint._legacy_module = SimpleNamespace()
    with patch.dict(
        "os.environ",
        {
            "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
            "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "0",
        },
        clear=False,
    ):
        with patch.object(modal_app, "RuntimeBootstrap", CapturingBootstrap):
            entrypoint._configure_runtime()

    callbacks = entrypoint.bootstrap.kwargs
    assert callbacks["select_sage_runtime_mode"] is not None
    assert callbacks["apply_sage_policy"] is not None
    # Golden selection is forced by the specialized selector callback itself;
    # the restore-wide force flag remains an ordinary-profile policy.
    assert callbacks["force_sage_selection_after_restore"] is False
    assert "attention_backend" not in callbacks


def test_golden_restore_callback_clears_stale_mode_and_uses_baked_env_without_probe():
    calls = []

    api = SimpleNamespace(
        _sage_runtime_mode="triton_fallback",
        _sage_runtime_reason="snapshot",
        _sage_probe_identity=None,
        _apply_sage_attention_policy=lambda: calls.append("apply") or True,
    )
    api._select_sage_runtime_mode = _ComfyAPIMixin._select_sage_runtime_mode.__get__(api)
    api._verify_baked_sageattention_runtime = lambda: (_ for _ in ()).throw(
        AssertionError("Golden restore must not probe")
    )

    class CapturingBootstrap:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._load_legacy_runtime = lambda: api
    entrypoint._legacy_module = SimpleNamespace()
    with patch.dict(
        "os.environ",
        {
            "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
            "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "0",
            "COMFYMODAL_SAGE_RUNTIME_MODE": "baked_cuda",
            "COMFYMODAL_SAGE_RUNTIME_PROBE_ON_RESTORE": "0",
        },
        clear=False,
    ):
        with patch.object(modal_app, "RuntimeBootstrap", CapturingBootstrap):
            entrypoint._configure_runtime()
        callbacks = entrypoint.bootstrap.kwargs
        with patch("comfyapp._resolve_sage_runtime_env_override", return_value="baked_cuda"):
            with patch("comfyapp._resolve_sage_probe_on_restore", return_value=False):
                assert callbacks["select_sage_runtime_mode"]() == {
                    "mode": "baked_cuda",
                    "reason": "runtime_override",
                    "identity": {},
                    "selection": "normal_restore",
                }
        assert callbacks["apply_sage_policy"]() is True
    assert calls == ["apply"]


def test_golden_baked_selector_overrides_stale_snapshot_mode_without_cuda():
    api = SimpleNamespace(
        _sage_runtime_mode="triton_fallback",
        _sage_runtime_reason="snapshot",
        _verify_baked_sageattention_runtime=lambda: (_ for _ in ()).throw(
            AssertionError("baked selector must not probe")
        ),
    )
    with patch.dict(
        "os.environ",
        {
            "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
            "COMFYMODAL_SAGE_RUNTIME_MODE": "baked_cuda",
        },
        clear=False,
    ):
        assert _ComfyAPIMixin._select_sage_runtime_mode(api) == (
            "baked_cuda",
            "runtime_override",
        )


def test_v2_restore_sage_callbacks_use_permissive_policy_not_ra5_strict_mode():
    calls = []
    api = SimpleNamespace(
        _sage_runtime_mode="baked_cuda",
        _select_sage_runtime_mode=lambda *args, **kwargs: calls.append(
            ("select", args, kwargs)
        ) or ("triton_fallback", "normal"),
        _apply_sage_attention_policy=lambda *args, **kwargs: calls.append(
            ("apply", args, kwargs)
        ) or False,
    )

    class CapturingBootstrap:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._load_legacy_runtime = lambda: api
    entrypoint._legacy_module = SimpleNamespace()
    with patch.dict(
        "os.environ",
        {
            "COMFYMODAL_V2CTL_PROFILE": "production",
            "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "0",
        },
        clear=False,
    ):
        with patch.object(modal_app, "RuntimeBootstrap", CapturingBootstrap):
            entrypoint._configure_runtime()

    callbacks = getattr(entrypoint.bootstrap, "kwargs")
    assert callbacks["select_sage_runtime_mode"] is not None
    assert callbacks["apply_sage_policy"] is not None
    assert callbacks["force_sage_selection_after_restore"] is True
    bootstrap = rbm.RuntimeBootstrap(
        restore_gpu_state=lambda: None,
        initialize_cuda=lambda: {},
        select_sage_runtime_mode=callbacks["select_sage_runtime_mode"],
        apply_sage_policy=callbacks["apply_sage_policy"],
        force_sage_selection_after_restore=callbacks[
            "force_sage_selection_after_restore"
        ],
    )
    bootstrap.restore()

    assert calls == [("select", (), {}), ("apply", (), {})]


def test_golden_sampling_closes_its_runner_scope_once():
    source = Path(gs.__file__).read_text(encoding="utf-8")
    function_source = source[source.index("async def golden_sampling"):]
    function_source = function_source[:function_source.index("async def golden_sampler_tail")]
    assert function_source.count("runner.end_scope()") == 1


def test_non_pytorch_sampling_requires_an_observed_override_call():
    with pytest.raises(gs.AttentionBackendValidationError, match="not_invoked"):
        gs._require_attention_backend_invocation("sage", {"calls": 0})
    gs._require_attention_backend_invocation("pytorch", {"calls": 0})
    gs._require_attention_backend_invocation("sage", {"calls": 1})


def test_strict_kjnodes_rejects_inner_pytorch_fallback_after_native_error():
    module = types.ModuleType("fake_kjnodes")
    fallback_calls = []

    def attention_pytorch(*args, **kwargs):
        fallback_calls.append(True)
        return "pytorch"

    module.attention_pytorch = attention_pytorch
    module.wrap_attn = lambda fn: fn
    exec(
        """
def get_sage_func(sage_attention, allow_compile=False):
    def selected(q, k, v, heads, mask=None, **kwargs):
        try:
            raise ValueError('native Sage failure')
        except Exception:
            return attention_pytorch(q, k, v, heads, mask=mask, **kwargs)
    return selected
""",
        module.__dict__,
    )
    patch_kjnodes_get_sage_func(module, baked_cuda_available=True, strict=True)
    q = torch.ones(1, 2, 3, 4)
    with pytest.raises(RuntimeError, match="attention_pytorch fallback"):
        module.get_sage_func("sageattn")(q, q, q, heads=2, skip_reshape=True)
    assert fallback_calls == []


def test_strict_kjnodes_explicit_sage_binds_public_native_callable():
    native_calls = []
    fallback_calls = []
    factory_calls = []

    def sageattn(q, k, v, *, attn_mask, is_causal, tensor_layout, sm_scale=None):
        native_calls.append((q, k, v, attn_mask, is_causal, tensor_layout, sm_scale))
        return q

    fake_sage = types.ModuleType("sageattention")
    fake_sage.sageattn = sageattn
    module = types.ModuleType("fake_kjnodes")
    module.attention_pytorch = lambda *_args, **_kwargs: fallback_calls.append(True)

    def wrap_attn(fn):
        fn.__wrapped__ = fn
        return fn

    module.wrap_attn = wrap_attn

    def get_sage_func(sage_attention, allow_compile=False):
        factory_calls.append(sage_attention)
        return lambda *_args, **_kwargs: fallback_calls.append(True)

    module.get_sage_func = get_sage_func
    q = torch.ones(1, 16, 32, 64, dtype=torch.float32)
    with patch.dict(sys.modules, {"sageattention": fake_sage}):
        patch_kjnodes_get_sage_func(module, baked_cuda_available=True, strict=True)
        selected = module.get_sage_func("sageattn_qk_int8_pv_fp16_cuda")
        # This is the exact KJNodes model-options seam: its override invokes
        # ``new_attention.__wrapped__`` rather than the outer Comfy wrapper.
        model_override = lambda _func, *args, **kwargs: selected.__wrapped__(*args, **kwargs)
        out = model_override(None, q, q, q, 16, skip_reshape=True, scale=0.125)

    assert factory_calls == []
    assert fallback_calls == []
    assert len(native_calls) == 1
    assert native_calls[0][0].dtype is torch.float16
    assert native_calls[0][5:] == ("HND", 0.125)
    assert out.dtype is torch.float32
    assert tuple(out.shape) == (1, 32, 1024)


def test_strict_kjnodes_native_adapter_rejects_unsupported_inputs_before_dispatch():
    native_calls = []

    def sageattn(*args, **kwargs):
        native_calls.append((args, kwargs))
        return args[0]

    fake_sage = types.ModuleType("sageattention")
    fake_sage.sageattn = sageattn
    module = types.ModuleType("fake_kjnodes")
    module.attention_pytorch = lambda *_args, **_kwargs: "pytorch"
    module.wrap_attn = lambda fn: fn
    module.get_sage_func = lambda *_args, **_kwargs: "unused"
    q = torch.ones(1, 16, 32, 64, dtype=torch.float16)
    with patch.dict(sys.modules, {"sageattention": fake_sage}):
        patch_kjnodes_get_sage_func(module, baked_cuda_available=True, strict=True)
        selected = module.get_sage_func("auto")
        with pytest.raises(RuntimeError, match="unsupported attention mask"):
            selected(q, q, q, heads=16, mask=torch.ones(1, 16, 32, 32), skip_reshape=True)
        with pytest.raises(RuntimeError, match="attention_pytorch fallback"):
            selected(q, q, q, heads=16, skip_reshape=True, low_precision_attention=False)

    assert native_calls == []


def test_golden_selector_uses_request_local_fresh_strict_probe():
    saves = []
    api = SimpleNamespace(
        _sage_runtime_mode="triton_fallback",
        _sage_runtime_reason="stale",
        _verify_baked_sageattention_runtime=lambda: (True, ["ok"]),
        _save_sage_runtime_cache=lambda *_args: saves.append(True),
    )
    with patch("comfyapp.list_sageattention_extension_files", return_value=[Path("_qattn_sm89.so")]):
        mode, reason = _ComfyAPIMixin._select_sage_runtime_mode(
            api, force_probe=True, strict=True
        )
    assert (mode, reason) == ("baked_cuda", "ok")
    assert not saves


def test_sage_identity_carries_pinned_source_policy_and_native_family():
    identity = build_sage_runtime_identity()
    assert identity["sage_source_repository"].endswith("SageAttention.git")
    assert identity["sage_source_ref"] == "v2.2.0"
    assert identity["sage_source_policy"].endswith("@v2.2.0")
    assert identity["sage_expected_native_family"] == "_qattn_sm89"
