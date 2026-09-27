import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = REPO_ROOT / "__init__.py"


class ModuleBootstrapTests(unittest.TestCase):
    def test_node_dir_is_added_to_sys_path_before_local_helper_import(self):
        source = INIT_PATH.read_text(encoding="utf-8")

        import_index = source.index("from local_placeholders import")
        node_dir_index = source.index("_NODE_DIR = os.path.dirname(os.path.abspath(__file__))")
        sys_path_index = source.index("sys.path.insert(0, _NODE_DIR)")

        self.assertLess(node_dir_index, import_index)
        self.assertLess(sys_path_index, import_index)


if __name__ == "__main__":
    unittest.main()
