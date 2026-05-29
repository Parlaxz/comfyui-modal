import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "custom_node_sync.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("custom_node_sync.py missing")
    spec = importlib.util.spec_from_file_location("custom_node_sync", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CustomNodeSyncTests(unittest.TestCase):
    def test_creates_symlink_for_new_volume_node(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            volume = root / "volume"
            comfy = root / "comfy"
            (volume / "ComfyUI-GGUF").mkdir(parents=True)
            comfy.mkdir(parents=True)

            with mock.patch.object(module.os, "symlink") as symlink_mock:
                result = module.sync_custom_nodes_into_comfy(str(volume), str(comfy))

            self.assertEqual(result["created"], ["ComfyUI-GGUF"])
            symlink_mock.assert_called_once_with(
                str(volume / "ComfyUI-GGUF"),
                str(comfy / "ComfyUI-GGUF"),
            )

    def test_removes_stale_volume_managed_symlink(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            volume = root / "volume"
            comfy = root / "comfy"
            volume.mkdir(parents=True)
            comfy.mkdir(parents=True)

            stale_link = comfy / "OldNode"
            stale_link.write_text("placeholder", encoding="utf-8")

            def fake_islink(path):
                return Path(path) == stale_link

            def fake_realpath(path):
                path = Path(path)
                if path == stale_link:
                    return str(volume / "OldNode")
                return str(path)

            with mock.patch.object(module.os.path, "islink", side_effect=fake_islink), \
                mock.patch.object(module.os.path, "realpath", side_effect=fake_realpath), \
                mock.patch.object(module.os, "unlink") as unlink_mock:
                result = module.sync_custom_nodes_into_comfy(str(volume), str(comfy))

            self.assertEqual(result["removed"], ["OldNode"])
            unlink_mock.assert_called_once_with(str(stale_link))

    def test_leaves_non_volume_directory_untouched(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            volume = root / "volume"
            comfy = root / "comfy"
            volume.mkdir(parents=True)
            comfy.mkdir(parents=True)
            (comfy / "LocalOnlyNode").mkdir(parents=True)

            result = module.sync_custom_nodes_into_comfy(str(volume), str(comfy))

            self.assertEqual(result["created"], [])
            self.assertEqual(result["removed"], [])
            self.assertTrue((comfy / "LocalOnlyNode").is_dir())

    def test_volume_state_changes_when_node_added(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            volume = Path(tmp) / "volume"
            volume.mkdir(parents=True)

            before = module.custom_node_volume_state(str(volume))
            (volume / "ComfyUI-GGUF").mkdir(parents=True)
            after = module.custom_node_volume_state(str(volume))

            self.assertNotEqual(before, after)

    def test_ignores_excluded_volume_dirs(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            volume = root / "volume"
            comfy = root / "comfy"
            (volume / "__pycache__").mkdir(parents=True)
            (volume / "RealNode").mkdir(parents=True)
            comfy.mkdir(parents=True)

            with mock.patch.object(module.os, "symlink") as symlink_mock:
                result = module.sync_custom_nodes_into_comfy(str(volume), str(comfy))

            self.assertEqual(result["created"], ["RealNode"])
            symlink_mock.assert_called_once()

    def test_missing_expected_nodes_reports_unseen_nodes(self):
        module = load_module()
        state = (("NodeA", 1, None), ("NodeB", 2, None))

        missing = module.missing_expected_nodes(state, ["NodeB", "NodeC"])

        self.assertEqual(missing, ["NodeC"])


if __name__ == "__main__":
    unittest.main()
