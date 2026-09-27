"""Focused tests for blocks-mode attention observation seams."""

from __future__ import annotations

import json
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from comfymodal_runtime import sampling_deep_profile as sdp


class _Tensor:
    shape = (2, 4, 8)
    dtype = "float16"
    device = "cuda:0"
    layout = "strided"


class AttentionObservationTests(unittest.TestCase):
    def setUp(self):
        self.sage = types.ModuleType("sageattention")
        self.kitchen = types.ModuleType("comfy_kitchen")
        self.attention = types.ModuleType("comfy.ldm.modules.attention")
        self.ops = types.ModuleType("comfy.ops")
        self.calls = []

        def sageattn(*args, **kwargs):
            self.calls.append("sage")
            return "sage-result"

        def specialized(*args, **kwargs):
            self.calls.append("specialized")
            return "specialized-result"

        def attention_pytorch(*args, **kwargs):
            self.calls.append("pytorch")
            return "pytorch-result"

        def sdpa(*args, **kwargs):
            self.calls.append("sdpa")
            return "sdpa-result"

        def fallback(*args, **kwargs):
            self.calls.append("fallback")
            return "fallback-result"

        def kitchen_attention(*args, **kwargs):
            self.calls.append("kitchen")
            return "kitchen-result"

        def kitchen_attention_masked(*args, **kwargs):
            self.calls.append("kitchen-masked")
            return "kitchen-masked-result"

        self.originals = {
            "sageattn": sageattn,
            "sageattn_x_cuda": specialized,
            "attention_pytorch": attention_pytorch,
            "scaled_dot_product_attention": sdpa,
            "attention_fallback": fallback,
            "int8_attention": kitchen_attention,
            "int8_attention_masked": kitchen_attention_masked,
        }
        setattr(self.sage, "sageattn", sageattn)
        setattr(self.sage, "sageattn_x_cuda", specialized)
        setattr(self.attention, "attention_pytorch", attention_pytorch)
        setattr(self.attention, "scaled_dot_product_attention", sdpa)
        setattr(self.attention, "attention_fallback", fallback)
        setattr(self.kitchen, "int8_attention", kitchen_attention)
        setattr(self.kitchen, "int8_attention_masked", kitchen_attention_masked)
        setattr(self.ops, "scaled_dot_product_attention", sdpa)
        self.modules = {
            "sageattention": self.sage,
            "comfy_kitchen": self.kitchen,
            "comfy.ldm.modules.attention": self.attention,
            "comfy.ops": self.ops,
        }
        self.patcher = SimpleNamespace(model_options={"transformer_options": {}})

    def _profile(self, override=None, requested_backend=""):
        if override is not None:
            self.patcher.model_options["transformer_options"][
                "optimized_attention_override"
            ] = override
        profile = sdp.SamplingDeepProfile(
            None,
            level="blocks",
            node_id="n",
            node_class="c",
            steps=1,
            sampling_start_monotonic_ns=1,
            sampling_start_wall_unix_ns=1,
            patcher=self.patcher,
            dm=None,
            requested_backend=requested_backend,
        )
        imports = lambda name: self.modules[name]
        with patch.object(sdp.importlib, "import_module", side_effect=imports):
            profile._install_backend_probe()
        return profile

    def test_lazy_override_uses_each_per_call_mapping_and_records_first_call(self):
        marker = "lazy-closure"

        def override(q, k, v, heads, mask=None, skip_reshape=False):
            return marker, q

        profile = self._profile()
        profile._begin_eval()
        q, k, v, mask = _Tensor(), _Tensor(), _Tensor(), _Tensor()
        first_options = {"optimized_attention_override": override}
        hook = sdp._make_pre_hook(profile, "block:0:attention", "attention")
        hook(object(), (q, k, v), {"transformer_options": first_options})
        first_wrapper = first_options["optimized_attention_override"]
        self.assertIsNot(first_wrapper, override)
        self.assertEqual(
            first_wrapper(q, k, v, 16, mask, True),
            (marker, q),
        )
        profile._span_end("block:0:attention", "attention")

        second_options = {"optimized_attention_override": override}
        hook(object(), (q, k, v), {"transformer_options": second_options})
        self.assertIs(second_options["optimized_attention_override"], first_wrapper)
        second_options["optimized_attention_override"](q, k, v, 16, mask, True)
        profile._span_end("block:0:attention", "attention")

        artifact = profile._attention_backend_artifact()
        metadata = artifact["original_callable_metadata"]
        self.assertIsNotNone(metadata)
        for field in ("repr", "name", "qualname", "module", "sourcefile", "closure"):
            self.assertIn(field, metadata)
        self.assertEqual(artifact["override_call_count"], 2)
        descriptor = artifact["override_first_call"]
        for name in ("q", "k", "v", "mask"):
            self.assertEqual(
                set(descriptor[name]), {"shape", "dtype", "device", "layout"}
            )
        self.assertEqual(descriptor["heads"], 16)
        self.assertTrue(descriptor["mask_present"])
        self.assertTrue(descriptor["skip_reshape"])
        self.assertIs(profile._override_container, first_options)
        json.loads(json.dumps(artifact))

        profile._restore_all()
        self.assertIs(first_options["optimized_attention_override"], override)
        self.assertIs(second_options["optimized_attention_override"], override)
        self.assertNotIn(
            "optimized_attention_override",
            self.patcher.model_options["transformer_options"],
        )

    def test_callable_metadata_is_bounded_and_does_not_invoke_original(self):
        invoked = []

        def make_override():
            closure_value = "secret-but-bounded"

            def override(q, k, v, heads, mask=None, skip_reshape=False):
                invoked.append(closure_value)
                return "original-result"

            return override

        original = make_override()
        profile = self._profile(original)
        metadata = profile._override_metadata
        assert metadata is not None
        self.assertEqual(invoked, [])
        self.assertEqual(metadata["__name__"], "override")
        self.assertIn("sourcefile", metadata)
        self.assertLessEqual(len(metadata["repr"]), sdp._MAX_METADATA_CHARS)
        self.assertLessEqual(len(metadata["closure"]), 8)
        self.assertTrue(json.loads(json.dumps(metadata)))
        profile._restore_all()

    def test_wrappers_are_passthrough_counted_and_restored(self):
        def override(q, k, v, heads, mask=None, skip_reshape=False):
            return ("override-result", q)

        profile = self._profile(override)
        q, k, v = _Tensor(), _Tensor(), _Tensor()
        mask = _Tensor()
        observed_override = self.patcher.model_options["transformer_options"][
            "optimized_attention_override"
        ]
        self.assertEqual(
            observed_override(q, k, v, 16, mask, True),
            ("override-result", q),
        )
        self.assertEqual(self.sage.sageattn(q, k, v), "sage-result")
        self.assertEqual(self.sage.sageattn_x_cuda(q, k, v), "specialized-result")
        self.assertEqual(self.attention.attention_pytorch(q, k, v), "pytorch-result")
        self.assertEqual(self.attention.scaled_dot_product_attention(q, k, v), "sdpa-result")
        self.assertEqual(self.attention.attention_fallback(q, k, v), "fallback-result")

        artifact = profile._attention_backend_artifact()
        self.assertEqual(artifact["override_call_count"], 1)
        self.assertEqual(artifact["override_first_call"]["q"]["shape"], [2, 4, 8])
        self.assertEqual(artifact["override_first_call"]["heads"], 16)
        self.assertTrue(artifact["override_first_call"]["mask_present"])
        self.assertTrue(artifact["override_first_call"]["skip_reshape"])
        self.assertEqual(artifact["sageattention_sageattn_calls"], 1)
        self.assertEqual(artifact["specialized_kernel_counts"]["sageattn_x_cuda"], 1)
        self.assertEqual(artifact["attention_pytorch_calls"], 1)
        self.assertEqual(artifact["pytorch_sdpa_calls"], 1)
        self.assertEqual(artifact["fallback_counts"]["attention_fallback"], 1)
        json.loads(json.dumps(artifact))

        profile._restore_all()
        self.assertIs(self.patcher.model_options["transformer_options"][
            "optimized_attention_override"
        ], override)
        for module, name in (
            (self.sage, "sageattn"),
            (self.sage, "sageattn_x_cuda"),
            (self.attention, "attention_pytorch"),
            (self.attention, "scaled_dot_product_attention"),
            (self.attention, "attention_fallback"),
        ):
            self.assertIs(getattr(module, name), self.originals[name])

    def test_sageattn_closure_alias_is_counted_and_cell_restored(self):
        def sageattn_alias(*args, **kwargs):
            return "closure-sage-result"

        sageattn_alias.__module__ = "sageattention"
        sageattn_alias.__name__ = "sageattn"

        def make_override():
            sage_func = sageattn_alias

            def attention_sage(*args, **kwargs):
                return sage_func(*args, **kwargs)

            attention_sage.__module__ = "kjnodes.get_sage_func"
            attention_sage.__name__ = "attention_sage"
            return attention_sage

        override = make_override()
        alias_cell = next(iter(override.__closure__ or []))
        profile = self._profile(override)
        wrapped = self.patcher.model_options["transformer_options"][
            "optimized_attention_override"
        ]
        self.assertIsNot(alias_cell.cell_contents, sageattn_alias)
        self.assertEqual(wrapped(_Tensor(), _Tensor(), _Tensor(), 8), "closure-sage-result")

        artifact = profile._attention_backend_artifact()
        self.assertEqual(artifact["sageattention_sageattn_calls"], 1)
        self.assertEqual(
            artifact["backend_first_calls"]["sageattention_sageattn"]["q"]["shape"],
            [2, 4, 8],
        )
        self.assertTrue(
            any("attention_sage" in item for item in artifact["original_callable_chain"])
        )
        self.assertFalse(
            any("_profiled_closure_alias" in item for item in artifact["original_callable_chain"])
        )
        self.assertTrue(artifact["closure_aliases"])
        profile._restore_all()
        self.assertIs(alias_cell.cell_contents, sageattn_alias)

    def test_kjnodes_wrapped_contract_survives_while_native_alias_is_counted(self):
        def sageattn_alias(*args, **kwargs):
            return "native-sage-result"

        sageattn_alias.__module__ = "sageattention"
        sageattn_alias.__name__ = "sageattn"

        def make_sage_func():
            native_alias = sageattn_alias

            def sage_func(*args, **kwargs):
                return native_alias(*args, **kwargs)

            sage_func.__module__ = "ComfyUI-KJNodes.nodes.model_optimization_nodes"
            sage_func.__name__ = "sage_func"
            return sage_func

        sage_func = make_sage_func()

        def make_attention_sage():
            def attention_sage_body(*args, **kwargs):
                return sage_func(*args, **kwargs)

            attention_sage_body.__module__ = (
                "ComfyUI-KJNodes.nodes.model_optimization_nodes"
            )
            attention_sage_body.__name__ = "attention_sage"

            def attention_sage(*args, **kwargs):
                return attention_sage_body(*args, **kwargs)

            attention_sage.__module__ = (
                "ComfyUI-KJNodes.nodes.model_optimization_nodes"
            )
            attention_sage.__name__ = "attention_sage"
            # This is the contract used by attention_override_sage.
            setattr(attention_sage, "__wrapped__", attention_sage_body)
            return attention_sage

        attention_sage = make_attention_sage()
        attention_sage_body = getattr(attention_sage, "__wrapped__")

        def attention_override_sage(*args, **kwargs):
            new_attention = attention_sage
            return getattr(new_attention, "__wrapped__")(*args, **kwargs)

        attention_override_sage.__module__ = (
            "ComfyUI-KJNodes.nodes.model_optimization_nodes"
        )
        attention_override_sage.__name__ = "attention_override_sage"
        alias_cell = next(
            cell
            for cell in attention_sage_body.__closure__ or ()
            if cell.cell_contents is sage_func
        )
        native_cell = next(
            cell
            for cell in sage_func.__closure__ or ()
            if cell.cell_contents is sageattn_alias
        )

        profile = self._profile(attention_override_sage)
        self.assertIs(getattr(attention_sage, "__wrapped__"), attention_sage_body)
        self.assertIsNot(native_cell.cell_contents, sageattn_alias)
        self.assertIs(getattr(native_cell.cell_contents, "__wrapped__"), sageattn_alias)
        self.assertIs(alias_cell.cell_contents, sage_func)
        self.assertEqual(
            sdp._sage_callable_counter(attention_sage),
            (None, True),
        )
        self.assertEqual(
            sdp._sage_callable_counter(sage_func),
            (None, True),
        )

        wrapped = self.patcher.model_options["transformer_options"][
            "optimized_attention_override"
        ]
        self.assertEqual(wrapped(_Tensor(), _Tensor(), _Tensor(), 8), "native-sage-result")
        artifact = profile._attention_backend_artifact()
        self.assertEqual(artifact["sageattention_sageattn_calls"], 1)
        self.assertEqual(len(artifact["closure_aliases"]), 1)
        self.assertEqual(artifact["closure_aliases"][0]["counter"], "sageattention_sageattn")

        profile._restore_all()
        self.assertIs(getattr(attention_sage, "__wrapped__"), attention_sage_body)
        self.assertIs(native_cell.cell_contents, sageattn_alias)

    def test_specialized_sage_closure_alias_is_counted_without_changing_result(self):
        def specialized_alias(*args, **kwargs):
            return object_marker

        object_marker = object()
        specialized_alias.__module__ = "sageattention"
        specialized_alias.__name__ = "sageattn_qk_int8_pv_fp16_cuda"

        def make_override():
            sage_func = specialized_alias

            def attention_sage(*args, **kwargs):
                return sage_func(*args, **kwargs)

            attention_sage.__module__ = "kjnodes.get_sage_func"
            attention_sage.__name__ = "attention_sage"
            return attention_sage

        override = make_override()
        alias_cell = next(iter(override.__closure__ or []))
        profile = self._profile(override)
        wrapped = self.patcher.model_options["transformer_options"][
            "optimized_attention_override"
        ]
        result = wrapped(_Tensor(), _Tensor(), _Tensor(), 8)
        self.assertIs(result, object_marker)
        artifact = profile._attention_backend_artifact()
        self.assertEqual(
            artifact["specialized_kernel_counts"][
                "sageattn_qk_int8_pv_fp16_cuda"
            ],
            1,
        )
        self.assertIn(
            "sageattention_specialized:sageattn_qk_int8_pv_fp16_cuda",
            artifact["backend_first_calls"],
        )
        profile._restore_all()
        self.assertIs(alias_cell.cell_contents, specialized_alias)

    def test_failed_closure_cell_write_is_explicitly_unobservable(self):
        def sageattn_alias(*args, **kwargs):
            return "result"

        sageattn_alias.__module__ = "sageattention"
        sageattn_alias.__name__ = "sageattn"

        def make_override():
            alias = sageattn_alias

            def attention_sage(*args, **kwargs):
                return alias(*args, **kwargs)

            attention_sage.__name__ = "attention_sage"
            return attention_sage

        with patch.object(sdp, "_replace_closure_cell", return_value=False):
            profile = self._profile(make_override())
        metadata = profile._attention_backend_artifact()
        self.assertTrue(metadata["closure_alias_unobservable"])
        self.assertTrue(any(w.startswith("closure_alias_unobservable:") for w in profile.warnings))
        profile._restore_all()

    def test_closure_alias_is_restored_when_aliased_callable_raises(self):
        def sageattn_alias(*args, **kwargs):
            raise RuntimeError("closure alias boom")

        sageattn_alias.__module__ = "sageattention"
        sageattn_alias.__name__ = "sageattn"

        def make_override():
            alias = sageattn_alias

            def attention_sage(*args, **kwargs):
                return alias(*args, **kwargs)

            attention_sage.__name__ = "attention_sage"
            return attention_sage

        override = make_override()
        alias_cell = next(iter(override.__closure__ or []))
        profile = self._profile(override)
        wrapped = self.patcher.model_options["transformer_options"][
            "optimized_attention_override"
        ]
        with self.assertRaisesRegex(RuntimeError, "closure alias boom"):
            wrapped(_Tensor(), _Tensor(), _Tensor(), 8)
        profile._restore_all()
        self.assertIs(alias_cell.cell_contents, sageattn_alias)

    def test_restore_runs_after_original_raises(self):
        def override(*args, **kwargs):
            raise RuntimeError("expected")

        profile = self._profile(override)
        wrapped = self.patcher.model_options["transformer_options"][
            "optimized_attention_override"
        ]
        with self.assertRaisesRegex(RuntimeError, "expected"):
            wrapped(_Tensor(), _Tensor(), _Tensor(), 8)
        profile._restore_all()
        self.assertIs(
            self.patcher.model_options["transformer_options"][
                "optimized_attention_override"
            ],
            override,
        )
        self.assertIs(self.sage.sageattn, self.originals["sageattn"])

    def test_attention_descriptor_retains_scalar_dispatch_options_only(self):
        descriptor = sdp._attention_call_descriptor(
            (_Tensor(), _Tensor(), _Tensor()),
            {
                "qk_quant_gran": "per_warp",
                "pv_accum_dtype": "fp32+fp16",
                "tensor_layout": "HND",
                "return_lse": True,
                "is_causal": False,
                "sm_scale": 0.125,
                "tensor_option": _Tensor(),
            },
        )
        self.assertEqual(descriptor["qk_quant_gran"], "per_warp")
        self.assertEqual(descriptor["pv_accum_dtype"], "fp32+fp16")
        self.assertEqual(descriptor["tensor_layout"], "HND")
        self.assertTrue(descriptor["return_lse"])
        self.assertFalse(descriptor["is_causal"])
        self.assertEqual(descriptor["sm_scale"], 0.125)
        self.assertNotIn("tensor_option", descriptor)
        json.loads(json.dumps(descriptor))

    def test_kitchen_public_seams_are_distinct_and_restored(self):
        profile = self._profile()
        q, k, v = _Tensor(), _Tensor(), _Tensor()
        self.assertEqual(self.kitchen.int8_attention(q, k, v), "kitchen-result")
        self.assertEqual(
            self.kitchen.int8_attention_masked(q, k, v, is_causal=True),
            "kitchen-masked-result",
        )
        artifact = profile._attention_backend_artifact()
        self.assertEqual(
            artifact["kitchen_public_counts"],
            {"int8_attention": 1, "int8_attention_masked": 1},
        )
        self.assertEqual(
            artifact["kitchen_public_first_calls"]["comfy_kitchen_int8_attention_masked"][
                "is_causal"
            ],
            True,
        )
        self.assertEqual(artifact["native_leaf_events"], [])
        profile._restore_all()
        self.assertIs(self.kitchen.int8_attention, self.originals["int8_attention"])
        self.assertIs(
            self.kitchen.int8_attention_masked,
            self.originals["int8_attention_masked"],
        )

    def test_one_shot_profiler_starts_before_public_call_and_filters_events(self):
        profile = self._profile(requested_backend="comfy_kitchen")
        profile._cuda_module = object()  # offline capability seam
        order = []

        class FakeProfiler:
            def __enter__(self):
                order.append("profiler_start")
                return self

            def __exit__(self, *exc):
                order.append("profiler_stop")

            def key_averages(self):
                return [
                    SimpleNamespace(
                        key="comfy_kitchen::int8_attention",
                        count=1,
                        self_cpu_time_total=2.5,
                        self_cuda_time_total=4.5,
                    ),
                    SimpleNamespace(key="aten::add", count=99),
                    SimpleNamespace(
                        key="aten::_scaled_dot_product_attention",
                        count=2,
                        cpu_time_total=3,
                    ),
                ]

        original = self.originals["int8_attention"]

        def ordered_original(*args, **kwargs):
            order.append("public_call")
            return original(*args, **kwargs)

        # Replace the fixture's original before installing the observation seam.
        setattr(self.kitchen, "int8_attention", ordered_original)
        with patch.object(sdp, "_create_attention_profiler", return_value=FakeProfiler()):
            profile._restore_all()
            profile = self._profile(requested_backend="comfy_kitchen")
            profile._cuda_module = object()
            self.assertEqual(profile._attention_profiler_attempted, False)
            self.kitchen.int8_attention(_Tensor(), _Tensor(), _Tensor(),
                                        qk_quant_gran="per_warp")

        self.assertEqual(order, ["profiler_start", "public_call", "profiler_stop"])
        self.assertEqual(profile._attention_profiler_status, "captured")
        self.assertEqual(
            [event["key"] for event in profile._native_leaf_events],
            ["comfy_kitchen::int8_attention", "aten::_scaled_dot_product_attention"],
        )
        artifact = profile._attention_backend_artifact()
        self.assertEqual(artifact["profiler_first_public_call"],
                         "comfy_kitchen_int8_attention")
        self.assertEqual(artifact["native_leaf_events"][0]["count"], 1)
        json.loads(json.dumps(artifact))
        profile._restore_all()

    def test_one_shot_profiler_wraps_active_override_once_with_bounded_events(self):
        order = []

        def sage_alias(*args, **kwargs):
            order.append("sage_call")
            return "override-result"

        sage_alias.__module__ = "sageattention"
        sage_alias.__name__ = "sageattn"

        def make_override():
            native_alias = sage_alias

            def override(*args, **kwargs):
                return native_alias(*args, **kwargs)

            override.__module__ = "kjnodes.get_sage_func"
            override.__name__ = "attention_sage"
            return override

        class FakeProfiler:
            def __enter__(self):
                order.append("profiler_start")
                return self

            def __exit__(self, *exc):
                order.append("profiler_stop")

            def key_averages(self):
                return [
                    SimpleNamespace(
                        key="sageattention::sageattn",
                        count=1,
                        self_cpu_time_total=1.0,
                    )
                ]

        profile = self._profile(override=make_override(), requested_backend="sage")
        profile._cuda_module = object()  # offline capability seam
        observed_override = self.patcher.model_options["transformer_options"][
            "optimized_attention_override"
        ]
        with patch.object(sdp, "_create_attention_profiler", return_value=FakeProfiler()):
            result = observed_override(_Tensor(), _Tensor(), _Tensor(), 8)

        self.assertEqual(result, "override-result")
        self.assertEqual(order, ["profiler_start", "sage_call", "profiler_stop"])
        self.assertEqual(profile._attention_profiler_attempted, True)
        self.assertEqual(profile._attention_profiler_status, "captured")
        self.assertEqual(profile._attention_profiler_call, "optimized_attention_override")
        self.assertEqual(len(profile._native_leaf_events), 1)
        self.assertEqual(profile._native_leaf_events[0]["key"], "sageattention::sageattn")
        self.assertEqual(profile._backend_counts["optimized_attention_override"], 1)
        self.assertEqual(profile._backend_counts["sageattention_sageattn"], 1)
        profile._restore_all()

    def test_profiler_cleanly_reports_unavailable_cuda_without_capture(self):
        profile = self._profile(requested_backend="sage")
        self.assertFalse(profile._start_attention_profiler("sageattention_sageattn"))
        self.assertEqual(profile._attention_profiler_status, "unavailable")
        self.assertEqual(profile._attention_profiler_error, "CUDA is not available")
        json.loads(json.dumps(profile._attention_backend_artifact()))
        profile._restore_all()


if __name__ == "__main__":
    unittest.main()
