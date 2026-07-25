import os
import unittest

from gpu_catalog import (
    DEFAULT_GPU,
    GPU_CATALOG,
    GPU_VALUES,
    _clear_hidden_cache,
    get_available_gpu_options,
    get_default_gpu,
    get_supported_gpus,
    gpu_supports_bf16,
    is_gpu_hidden,
    is_supported_gpu,
    normalize_gpu_value,
)


class GpuCatalogTests(unittest.TestCase):
    # ── env-var helpers ──────────────────────────────────────────────
    _ENV_KEY = "COMFYMODAL_HIDE_GPUS"

    def setUp(self):
        self._old_env = os.environ.get(self._ENV_KEY)
        _clear_hidden_cache()

    def tearDown(self):
        _clear_hidden_cache()
        if self._old_env is None:
            os.environ.pop(self._ENV_KEY, None)
        else:
            os.environ[self._ENV_KEY] = self._old_env

    # ── baseline ─────────────────────────────────────────────────────
    def test_default_gpu_is_a10g(self):
        self.assertEqual(DEFAULT_GPU, "a10g")

    def test_catalog_contains_expected_single_gpu_values(self):
        self.assertEqual(
            GPU_VALUES,
            [
                "t4",
                "l4",
                "a10g",
                "l40s",
                "rtx-pro-6000",
                "a100",
                "a100-40gb",
                "a100-80gb",
                "h100",
                "h200",
                "b200",
            ],
        )

    def test_normalize_gpu_value_lowercases_and_strips(self):
        self.assertEqual(normalize_gpu_value("  A100-80GB  "), "a100-80gb")

    def test_available_gpu_options_are_value_label_pairs(self):
        self.assertIn({"value": "a10g", "label": "A10G"}, get_available_gpu_options())

    # ── hidden GPU behaviour ─────────────────────────────────────────
    def test_default_env_no_hidden_gpus(self):
        """With no env var, nothing is hidden."""
        self.assertEqual(len(get_supported_gpus()), len(GPU_CATALOG))

    def test_is_gpu_hidden_returns_false_when_not_hidden(self):
        self.assertFalse(is_gpu_hidden("a10g"))

    def test_hidden_gpu_is_excluded_from_supported(self):
        os.environ[self._ENV_KEY] = "t4,l4,l40s"
        _clear_hidden_cache()
        self.assertNotIn("t4", get_supported_gpus())
        self.assertNotIn("l4", get_supported_gpus())
        self.assertNotIn("l40s", get_supported_gpus())
        self.assertIn("a10g", get_supported_gpus())

    def test_hidden_gpu_is_excluded_from_available_options(self):
        os.environ[self._ENV_KEY] = "t4"
        _clear_hidden_cache()
        options = get_available_gpu_options()
        self.assertNotIn("t4", [o["value"] for o in options])
        self.assertIn("a10g", [o["value"] for o in options])

    def test_is_gpu_hidden_returns_true_for_hidden(self):
        os.environ[self._ENV_KEY] = "h100"
        _clear_hidden_cache()
        self.assertTrue(is_gpu_hidden("h100"))
        self.assertFalse(is_gpu_hidden("a10g"))

    def test_is_supported_gpu_false_for_hidden(self):
        os.environ[self._ENV_KEY] = "b200"
        _clear_hidden_cache()
        self.assertFalse(is_supported_gpu("b200"))
        self.assertTrue(is_supported_gpu("a10g"))

    def test_get_default_gpu_falls_back_when_default_hidden(self):
        os.environ[self._ENV_KEY] = "a10g"
        _clear_hidden_cache()
        default = get_default_gpu()
        self.assertNotEqual(default, "a10g")
        self.assertIn(default, [e["value"] for e in GPU_CATALOG])

    def test_get_default_gpu_unchanged_when_default_not_hidden(self):
        os.environ[self._ENV_KEY] = "t4"
        _clear_hidden_cache()
        self.assertEqual(get_default_gpu(), "a10g")

    def test_normalize_gpu_value_handles_edge_cases(self):
        self.assertEqual(normalize_gpu_value(""), "")
        self.assertEqual(normalize_gpu_value(None), "")

    def test_gpu_catalog_structure(self):
        for entry in GPU_CATALOG:
            self.assertIn("value", entry)
            self.assertIn("label", entry)
            self.assertIn("modal_gpu", entry)
            self.assertIn("class_name", entry)
            self.assertIn("profile", entry)

    # ── BF16 capability tests ─────────────────────────────────────────
    def test_gpu_supports_bf16_lowercase_canonical_name(self):
        self.assertTrue(gpu_supports_bf16("rtx-pro-6000"))

    def test_gpu_supports_bf16_modal_cased_name(self):
        self.assertTrue(gpu_supports_bf16("RTX-PRO-6000"))

    def test_gpu_supports_bf16_a10(self):
        self.assertTrue(gpu_supports_bf16("A10"))

    def test_gpu_supports_bf16_a100(self):
        self.assertTrue(gpu_supports_bf16("A100"))

    def test_gpu_supports_bf16_a100_40gb(self):
        self.assertTrue(gpu_supports_bf16("a100-40gb"))

    def test_gpu_supports_bf16_a100_80gb(self):
        self.assertTrue(gpu_supports_bf16("a100-80gb"))

    def test_gpu_supports_bf16_l4(self):
        self.assertTrue(gpu_supports_bf16("L4"))

    def test_gpu_supports_bf16_l40s(self):
        self.assertTrue(gpu_supports_bf16("L40S"))

    def test_gpu_supports_bf16_h100(self):
        self.assertTrue(gpu_supports_bf16("H100"))

    def test_gpu_supports_bf16_h200(self):
        self.assertTrue(gpu_supports_bf16("H200"))

    def test_gpu_supports_bf16_b200(self):
        self.assertTrue(gpu_supports_bf16("B200"))

    def test_gpu_supports_bf16_t4_is_false(self):
        self.assertFalse(gpu_supports_bf16("T4"))

    def test_gpu_supports_bf16_unknown_gpu_is_false(self):
        self.assertFalse(gpu_supports_bf16("k80"))

    def test_gpu_supports_bf16_no_cuda_calls(self):
        """Prove the helper is a pure static lookup — no torch.cuda APIs."""
        import unittest.mock as mock
        import torch
        with mock.patch.object(torch.cuda, "is_bf16_supported",
                               side_effect=RuntimeError("CUDA called")):
            # These must succeed without calling torch.cuda
            self.assertTrue(gpu_supports_bf16("A100"))
            self.assertFalse(gpu_supports_bf16("T4"))

    def test_gpu_supports_bf16_every_catalog_gpu(self):
        """Every GPU in GPU_CATALOG has a known BF16 capability classification."""
        for entry in GPU_CATALOG:
            value = entry["value"]
            result = gpu_supports_bf16(value)
            self.assertIsInstance(result, bool, f"GPU {value} has no BF16 classification")


if __name__ == "__main__":
    unittest.main()
