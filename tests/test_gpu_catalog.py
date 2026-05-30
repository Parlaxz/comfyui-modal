import unittest

from gpu_catalog import DEFAULT_GPU, GPU_VALUES, get_available_gpu_options, normalize_gpu_value


class GpuCatalogTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
