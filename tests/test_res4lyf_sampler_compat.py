import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RES4LYF_ROOT = REPO_ROOT.parent / "RES4LYF"
RES4LYF_BETA_SAMPLERS = RES4LYF_ROOT / "beta" / "samplers.py"
RES4LYF_TXT2IMG_EXAMPLE = RES4LYF_ROOT / "example_workflows" / "hidream txt2img.json"


class Res4lyfSamplerCompatTests(unittest.TestCase):
    def test_example_workflow_still_uses_fixed_noise_widget_slot(self):
        text = RES4LYF_TXT2IMG_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn('"widgets_values":[0.5,"multistep/res_3m","bong_tangent",20,-1,1,4,0,"fixed","standard",true]', text)

    def test_clownshark_sampler_beta_preserves_noise_type_init_between_seed_and_sampler_mode(self):
        text = RES4LYF_BETA_SAMPLERS.read_text(encoding="utf-8")
        pattern = re.compile(
            r'"seed"\s*:\s*\("INT".*?'
            r'"noise_type_init"\s*:\s*\(NOISE_GENERATOR_NAMES_SIMPLE,\s*\{"default":\s*"fixed"\}\),.*?'
            r'"sampler_mode"\s*:\s*\(\[\'unsample\',\s*\'standard\',\s*\'resample\'\]',
            re.DOTALL,
        )
        self.assertRegex(text, pattern)


if __name__ == "__main__":
    unittest.main()
