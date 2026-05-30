import unittest

from workflow_metadata import extract_model_stack, prompt_sha256, summarize_prompt_fields


WORKFLOW_A = {
    "3": {"class_type": "KSampler", "inputs": {
        "seed": 7, "steps": 20, "cfg": 3.5,
        "sampler_name": "euler", "scheduler": "normal", "denoise": 1,
    }},
    "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024}},
    "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-9b-fp8.safetensors"}},
    "11": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp8mixed.safetensors"}},
    "12": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
}

WORKFLOW_B = {
    "12": WORKFLOW_A["12"],
    "11": WORKFLOW_A["11"],
    "10": WORKFLOW_A["10"],
    "4": WORKFLOW_A["4"],
    "3": WORKFLOW_A["3"],
}


class WorkflowMetadataTests(unittest.TestCase):
    def test_prompt_hash_is_stable_across_key_order(self):
        self.assertEqual(prompt_sha256(WORKFLOW_A), prompt_sha256(WORKFLOW_B))

    def test_prompt_summary_extracts_common_fields(self):
        summary = summarize_prompt_fields(WORKFLOW_A)
        self.assertEqual(summary["seed"], 7)
        self.assertEqual(summary["steps"], 20)
        self.assertEqual(summary["cfg"], 3.5)
        self.assertEqual(summary["width"], 1024)
        self.assertEqual(summary["height"], 1024)

    def test_extract_model_stack_collects_flux_base_stack(self):
        stack = extract_model_stack(WORKFLOW_A)
        self.assertIn("flux-2-klein-9b-fp8.safetensors", stack["unet"])
        self.assertIn("qwen_3_8b_fp8mixed.safetensors", stack["clip"])
        self.assertIn("flux2-vae.safetensors", stack["vae"])

        # Cross-role separation: each value appears only in its own bucket
        self.assertNotIn("flux-2-klein-9b-fp8.safetensors", stack["clip"])
        self.assertNotIn("flux-2-klein-9b-fp8.safetensors", stack["vae"])
        self.assertNotIn("qwen_3_8b_fp8mixed.safetensors", stack["unet"])
        self.assertNotIn("qwen_3_8b_fp8mixed.safetensors", stack["vae"])
        self.assertNotIn("flux2-vae.safetensors", stack["unet"])
        self.assertNotIn("flux2-vae.safetensors", stack["clip"])
