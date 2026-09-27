import unittest
from pathlib import Path


OUTER_COMFYUI_PATH = Path(__file__).resolve().parents[4]
BATCH_PATH = OUTER_COMFYUI_PATH / "redeploy_modal_and_run_comfyui.bat"
PS_CHECKER_PATH = OUTER_COMFYUI_PATH / "check_comfyui.ps1"


class RedeployBatchTests(unittest.TestCase):
    def test_batch_file_exists_in_outer_comfyui_folder(self):
        self.assertTrue(BATCH_PATH.is_file(), f"Missing batch file: {BATCH_PATH}")

    def test_ps_checker_script_exists(self):
        self.assertTrue(PS_CHECKER_PATH.is_file(), f"Missing .ps1: {PS_CHECKER_PATH}")

    def test_batch_file_redeploys_modal_and_guards_comfyui_restart(self):
        source = BATCH_PATH.read_text(encoding="utf-8")
        self.assertIn("modal deploy", source)
        self.assertIn("run_nvidia_gpu.bat", source)
        self.assertIn("check_comfyui.ps1", source)
        self.assertIn("-File", source)
        self.assertNotIn("^|", source)

    def test_batch_file_hides_t4_l4_l40s(self):
        source = BATCH_PATH.read_text(encoding="utf-8")
        self.assertIn("COMFYMODAL_HIDE_GPUS=t4,l4,l40s", source)

    def test_batch_deploys_with_active_workspace_credentials(self):
        source = BATCH_PATH.read_text(encoding="utf-8")
        self.assertIn(".modal_workspaces.json", source)
        self.assertIn("active_workspace_id", source)
        self.assertIn("MODAL_TOKEN_ID", source)
        self.assertIn("MODAL_TOKEN_SECRET", source)
        self.assertIn("Could not load the active Modal workspace credentials.", source)
        self.assertLess(
            source.index("MODAL_TOKEN_SECRET"),
            source.index("modal deploy"),
            "Modal must receive the active workspace credentials before deploy",
        )

    def test_ps_checker_contents(self):
        source = PS_CHECKER_PATH.read_text(encoding="utf-8")
        self.assertIn("Get-CimInstance Win32_Process", source)
        self.assertIn("CommandLine -match", source)
        self.assertIn("ComfyUI\\\\main", source)
        self.assertIn("exit 0", source)
        self.assertIn("exit 1", source)


if __name__ == "__main__":
    unittest.main()
