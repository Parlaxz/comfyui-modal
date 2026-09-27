import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_input_image_paths import _load_init_module


class DeployStateBookkeepingTests(unittest.TestCase):
    def test_record_manual_deploy_state_persists_command_and_timestamp(self):
        module = _load_init_module()
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / ".deployed_state.json"
            legacy_path = Path(tmp) / ".deployed_version"
            custom_nodes = Path(tmp) / "custom_nodes"
            (custom_nodes / "example-node").mkdir(parents=True)
            (custom_nodes / "example-node" / "requirements.txt").write_text("numpy\n", encoding="utf-8")
            with (
                patch.object(module, "_DEPLOY_STATE_JSON_FILE", str(state_path)),
                patch.object(module, "_DEPLOY_STATE_FILE", str(legacy_path)),
                patch.object(module, "_custom_nodes_root", return_value=str(custom_nodes)),
            ):
                payload = module._record_manual_deploy_state(deployment_command='modal deploy "comfyapp.py"')

            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["comfyapp_version"], module._get_comfyapp_version())
            self.assertEqual(saved["deployment_command"], 'modal deploy "comfyapp.py"')
            self.assertTrue(saved["custom_nodes_fingerprint"])
            self.assertTrue(saved["deployed_at"])
            self.assertEqual(saved, payload)


if __name__ == "__main__":
    unittest.main()
