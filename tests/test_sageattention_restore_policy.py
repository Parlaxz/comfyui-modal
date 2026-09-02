import unittest
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from comfymodal_runtime.sage_policy import (
    build_sage_runtime_identity,
    choose_sage_runtime_mode,
    list_sageattention_extension_files,
    sage_runtime_cache_usable,
    sage_runtime_identity_matches,
    select_public_sageattention_callable,
)


class SageAttentionRestorePolicyTests(unittest.TestCase):
    def test_list_sageattention_extension_files_finds_any_compiled_extension(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sageattention"
            root.mkdir(parents=True)
            (root / "_fused.cpython-311-x86_64-linux-gnu.so").write_bytes(b"x")
            files = list_sageattention_extension_files(str(Path(tmp)))
            self.assertEqual([p.name for p in files], ["_fused.cpython-311-x86_64-linux-gnu.so"])

    def test_list_accepts_v22_sm89_native_family_without_sm120_name(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sageattention"
            root.mkdir(parents=True)
            (root / "_fused.cpython-311-x86_64-linux-gnu.so").write_bytes(b"fused")
            (root / "_qattn_sm89.cpython-311-x86_64-linux-gnu.so").write_bytes(b"sm89")
            self.assertEqual(
                [p.name for p in list_sageattention_extension_files(tmp)],
                ["_fused.cpython-311-x86_64-linux-gnu.so", "_qattn_sm89.cpython-311-x86_64-linux-gnu.so"],
            )

    def test_public_dispatcher_is_selected_over_private_symbols(self):
        calls = []

        class FakeSage:
            sageattn_qk_int8_pv_fp16_cuda = object()

            @staticmethod
            def sageattn(*args, **kwargs):
                calls.append((args, kwargs))

        name, callable_, kwargs = select_public_sageattention_callable(FakeSage)
        self.assertEqual(name, "sageattn")
        self.assertIs(callable_, FakeSage.sageattn)
        self.assertEqual(kwargs, {"tensor_layout": "HND", "is_causal": False})

    def test_runtime_identity_changes_when_artifact_changes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sageattention"
            root.mkdir(parents=True)
            extension = root / "_qattn_sm89.so"
            extension.write_bytes(b"build-a")
            first = build_sage_runtime_identity(
                site_packages_root=tmp,
                gpu_name="RTX PRO 6000",
                capability=(12, 0),
                sage_version="2.2.0",
                torch_version="2.13.0+cu130",
                torch_cuda="13.0",
            )
            extension.write_bytes(b"build-b")
            second = build_sage_runtime_identity(
                site_packages_root=tmp,
                gpu_name="RTX PRO 6000",
                capability=(12, 0),
                sage_version="2.2.0",
                torch_version="2.13.0+cu130",
                torch_cuda="13.0",
            )
            self.assertFalse(sage_runtime_identity_matches(first, second))

    def test_runtime_identity_changes_when_policy_or_gpu_changes(self):
        base = build_sage_runtime_identity(gpu_name="A", capability=(8, 0))
        other_gpu = build_sage_runtime_identity(gpu_name="B", capability=(8, 0))
        other_policy = dict(base, policy_version="different-policy")
        other_policy["identity_digest"] = ""
        self.assertFalse(sage_runtime_identity_matches(base, other_gpu))
        self.assertFalse(sage_runtime_identity_matches(base, other_policy))

    def test_strict_mode_never_reuses_negative_cache(self):
        identity = build_sage_runtime_identity(gpu_name="A", capability=(12, 0))
        negative = dict(identity, mode="triton_fallback")
        positive = dict(identity, mode="baked_cuda")
        self.assertTrue(sage_runtime_cache_usable(negative, identity))
        self.assertFalse(sage_runtime_cache_usable(negative, identity, strict=True))
        self.assertTrue(sage_runtime_cache_usable(positive, identity, strict=True))

    def test_choose_sage_runtime_mode_uses_fallback_when_extensions_missing(self):
        mode, reason = choose_sage_runtime_mode(enabled=True, extension_files=[], import_ok=False, smoke_ok=False)
        self.assertEqual(mode, "triton_fallback")
        self.assertEqual(reason, "compiled-extensions-missing")

    def test_choose_sage_runtime_mode_requires_smoke_test(self):
        mode, reason = choose_sage_runtime_mode(
            enabled=True,
            extension_files=[Path("/tmp/sageattention/_fused.so")],
            import_ok=True,
            smoke_ok=False,
        )
        self.assertEqual(mode, "triton_fallback")
        self.assertEqual(reason, "smoke-test-failed")

    def test_choose_sage_runtime_mode_prefers_baked_cuda_when_extensions_exist_import_passes_and_smoke_passes(self):
        mode, reason = choose_sage_runtime_mode(
            enabled=True,
            extension_files=[Path("/tmp/sageattention/_fused.so")],
            import_ok=True,
            smoke_ok=True,
        )
        self.assertEqual(mode, "baked_cuda")
        self.assertEqual(reason, "compiled-extensions-usable")

    @pytest.mark.heavy_local
    def test_patch_kjnodes_get_sage_func_uses_attention_pytorch_when_baked_cuda_unavailable(self):
        from comfyapp import patch_kjnodes_get_sage_func
        class FakeModule:
            def __init__(self):
                self.attention_pytorch = lambda q, k, v, heads, **kwargs: "pytorch"

                def _wrap_attn(fn):
                    fn.__wrapped__ = fn
                    return fn

                self.wrap_attn = _wrap_attn

            def get_sage_func(self, sage_attention, allow_compile=False):
                return lambda *args, **kwargs: "sage"

        module = FakeModule()
        patched = patch_kjnodes_get_sage_func(module, baked_cuda_available=False)
        self.assertTrue(patched)
        q = {"dummy": "q"}
        k = {"dummy": "k"}
        v = {"dummy": "v"}
        result = module.get_sage_func("sageattn_qk_int8_pv_fp16_cuda")(q, k, v, heads=8)
        self.assertEqual(result, "pytorch")

    @pytest.mark.heavy_local
    def test_patch_kjnodes_get_sage_func_preserves_explicit_pytorch_selection(self):
        from comfyapp import patch_kjnodes_get_sage_func
        calls = []

        class FakeModule:
            attention_pytorch = staticmethod(lambda *args, **kwargs: "pytorch")
            wrap_attn = staticmethod(lambda fn: fn)

            @staticmethod
            def get_sage_func(sage_attention, allow_compile=False):
                calls.append((sage_attention, allow_compile))
                return lambda *args, **kwargs: "explicit-pytorch"

        module = FakeModule()
        self.assertTrue(patch_kjnodes_get_sage_func(module, baked_cuda_available=True))
        selected = module.get_sage_func("pytorch")

        self.assertEqual(selected(None, None, None, heads=8), "explicit-pytorch")
        self.assertEqual(calls, [("pytorch", False)])

    @pytest.mark.heavy_local
    def test_patch_kjnodes_rejects_fallback_in_strict_mode(self):
        from comfyapp import patch_kjnodes_get_sage_func
        class FakeModule:
            attention_pytorch = lambda *args, **kwargs: "pytorch"
            wrap_attn = staticmethod(lambda fn: fn)
            get_sage_func = lambda *args, **kwargs: "sage"

        with self.assertRaisesRegex(RuntimeError, "rejected"):
            patch_kjnodes_get_sage_func(FakeModule(), baked_cuda_available=False, strict=True)


class SageAttentionImportBlockerPatternTests(unittest.TestCase):
    """Test the _is_cuda_module pattern used by both import blockers.

    The pattern is replicated here because _BlockCudaModuleImport is nested
    inside _force_cpu_during_snapshot / _force_triton_during_snapshot and is
    not directly importable.
    """

    @staticmethod
    def _is_cuda_module(name: str) -> bool:
        return (
            name.endswith("_cuda")
            or name.startswith("cuda_")
            or "_cuda_" in name
            or name.startswith("sageattn._")
            or name.startswith("sageattention._")
        )

    # --- Modules that SHOULD be blocked ---

    def test_blocks_sageattn_cuda_ext(self):
        self.assertTrue(self._is_cuda_module("sageattn_qk_int8_pv_fp16_cuda"))

    def test_blocks_sageattn_fp8_cuda_ext(self):
        self.assertTrue(self._is_cuda_module("sageattn_qk_int8_pv_fp8_cuda"))

    def test_blocks_sageattn_native_submodule(self):
        self.assertTrue(self._is_cuda_module("sageattn._qattn_sm120"))

    def test_blocks_sageattn_generic_underscore(self):
        self.assertTrue(self._is_cuda_module("sageattn._C"))

    def test_blocks_sageattention_native_submodule(self):
        self.assertTrue(self._is_cuda_module("sageattention._C"))

    def test_blocks_generic_cuda_suffix(self):
        self.assertTrue(self._is_cuda_module("foo_cuda"))

    def test_blocks_cuda_prefix(self):
        self.assertTrue(self._is_cuda_module("cuda_foo"))

    def test_blocks_infix_cuda(self):
        self.assertTrue(self._is_cuda_module("foo_cuda_bar"))

    # --- Modules that should NOT be blocked ---

    def test_allows_sageattn_package(self):
        self.assertFalse(self._is_cuda_module("sageattn"))

    def test_allows_sageattention_package(self):
        self.assertFalse(self._is_cuda_module("sageattention"))

    def test_allows_torch_c(self):
        self.assertFalse(self._is_cuda_module("torch._C"))

    def test_allows_random_module(self):
        self.assertFalse(self._is_cuda_module("numpy"))

    def test_allows_comfyui_core(self):
        self.assertFalse(self._is_cuda_module("comfy.sd"))


if __name__ == "__main__":
    unittest.main()
