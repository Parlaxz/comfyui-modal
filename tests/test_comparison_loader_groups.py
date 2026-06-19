import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COMPARISON_PATH = REPO_ROOT / "comparison.py"


def load_comparison():
    spec = importlib.util.spec_from_file_location("comparison", COMPARISON_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def minimal_workflow_api() -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "u_old.safetensors"}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "c_old.safetensors"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "v_old.safetensors"}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello"}},
    }


class ProfileLoaderGroupsTests(unittest.TestCase):
    def test_create_profile_v1_migrates_to_v2(self):
        comp = load_comparison()
        with tempfile.TemporaryDirectory() as tmp:
            comp.create_profile(
                comfyui_root=tmp,
                name="Test",
                workflow_api=minimal_workflow_api(),
                adapter=None,
            )
            profiles = comp.list_profiles(tmp)
            self.assertEqual(len(profiles), 1)
            p = profiles[0]
            # On read, list_profiles must auto-migrate to v2
            self.assertEqual(p["schema_version"], 2)
            self.assertIn("loader_target_groups", p)
            self.assertIn("lora_slots", p)
            self.assertIn("subprofiles", p)

    def test_update_profile_preserves_loader_groups(self):
        comp = load_comparison()
        with tempfile.TemporaryDirectory() as tmp:
            comp.create_profile(
                comfyui_root=tmp, name="Test", workflow_api=minimal_workflow_api(),
            )
            profiles = comp.list_profiles(tmp)
            pid = profiles[0]["id"]
            # Add a loader group, then update the profile with no group change.
            groups = [{
                "id": "g_main", "label": "Main",
                "unet": [{"node_id": "1", "field": "unet_name"}],
                "clip": [{"node_id": "2", "field": "clip_name1"}],
                "vae": [{"node_id": "3", "field": "vae_name"}],
            }]
            updates = {
                "name": "Renamed",
                "loader_target_groups": groups,
            }
            comp.update_profile(comfyui_root=tmp, profile_id=pid, updates=updates)
            refreshed = comp.get_profile(tmp, pid)
            self.assertEqual(refreshed["loader_target_groups"][0]["id"], "g_main")

    def test_workflow_injection_round_trip_with_existing_profile(self):
        comp = load_comparison()
        with tempfile.TemporaryDirectory() as tmp:
            comp.create_profile(
                comfyui_root=tmp, name="Test", workflow_api=minimal_workflow_api(),
            )
            profiles = comp.list_profiles(tmp)
            pid = profiles[0]["id"]
            # Latest workflow is what's on disk in workflow_api.json
            workflow = comp._load_workflow_api(comp._profiles_root(tmp), pid)
            group = profiles[0]["loader_target_groups"][0]
            comp.inject_loader_group(workflow, group, {
                "unet": "u_new.safetensors",
                "clip": "c_new.safetensors",
                "vae": "v_new.safetensors",
            })
            self.assertEqual(workflow["1"]["inputs"]["unet_name"], "u_new.safetensors")
            self.assertEqual(workflow["2"]["inputs"]["clip_name1"], "c_new.safetensors")
            self.assertEqual(workflow["3"]["inputs"]["vae_name"], "v_new.safetensors")


if __name__ == "__main__":
    unittest.main()
