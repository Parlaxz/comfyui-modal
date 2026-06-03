import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from comfyapp import (
    choose_sage_runtime_mode,
    list_sageattention_extension_files,
    patch_kjnodes_get_sage_func,
)


class SageAttentionRestorePolicyTests(unittest.TestCase):
    def test_list_sageattention_extension_files_finds_any_compiled_extension(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sageattention"
            root.mkdir(parents=True)
            (root / "_fused.cpython-311-x86_64-linux-gnu.so").write_bytes(b"x")
            files = list_sageattention_extension_files(str(Path(tmp)))
            self.assertEqual([p.name for p in files], ["_fused.cpython-311-x86_64-linux-gnu.so"])

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

    def test_patch_kjnodes_get_sage_func_uses_attention_pytorch_when_baked_cuda_unavailable(self):
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


if __name__ == "__main__":
    unittest.main()
