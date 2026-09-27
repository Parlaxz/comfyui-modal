import json
import tempfile
import unittest
from pathlib import Path

from ra11f.real_harness import (
    SCHEMA_VERSION,
    _make_projection,
    MonotonicPackageController,
    compare_scoped,
    package_audits,
    package_selection,
    workflow_class_ids,
)


class RA11FRealPackageUnitTests(unittest.TestCase):
    def test_controller_is_monotonic_and_complete_fallback_is_sticky(self):
        controller = MonotonicPackageController()
        first = controller.plan(["pkg-b", "pkg-a"])
        controller.record("pkg-a", True)
        controller.record("pkg-b", False)
        self.assertEqual(first, ["pkg-a", "pkg-b"])
        self.assertEqual(controller.plan(["pkg-a", "pkg-b"]), [])
        self.assertEqual(controller.plan(["pkg-a", "pkg-c"], complete=True), ["pkg-c"])
        self.assertEqual(controller.plan(["pkg-c"], complete=False), [])
        self.assertTrue(controller.snapshot()["no_unload_reload"])

    def test_workflow_class_ids_are_real_string_ids_and_stable(self):
        prompt = {"7": {"class_type": "Any Switch (rgthree)"}, "2": {"class_type": "CLIPLoader"}, "x": {"class_id": "CLIPLoader"}}
        self.assertEqual(workflow_class_ids(prompt), ["Any Switch (rgthree)", "CLIPLoader"])

    def test_unknown_class_requires_complete_discovery_fallback(self):
        selection = package_selection(
            {"1": {"class_type": "KnownReal"}, "2": {"class_type": "UnknownReal"}},
            {"KnownReal": "real-package"},
        )
        self.assertEqual(selection["selected_packages"], ["real-package"])
        self.assertEqual(selection["unknown_class_ids"], ["UnknownReal"])
        self.assertTrue(selection["fallback"])

    def test_projection_is_discovery_only_and_uses_full_owner_observation(self):
        state = {"class_owner": {"RealA": "pkg-a", "RealB": "pkg-b", "Builtin": ""}}
        a = _make_projection(state, "projection_a")
        b = _make_projection(state, "projection_b")
        self.assertTrue(a["discovery_only"])
        self.assertNotEqual(a["selected_packages_expected"], b["selected_packages_expected"])
        self.assertNotIn("Builtin", a["prompt"])

    def test_compare_scoped_ignores_full_only_packages_but_detects_real_delta(self):
        full = {"state": {
            "class_owner": {"A": "pkg-a", "B": "pkg-b"},
            "class_mappings": {"A": {"owner": "pkg-a"}, "B": {"owner": "pkg-b"}},
            "RELATIVE_PYTHON_MODULE": {"A": "custom_nodes.pkg-a", "B": "custom_nodes.pkg-b"},
            "display_mappings": {"A": "A", "B": "B"},
            "import_order": ["pkg-a", "pkg-b"],
            "package_observations": [{"package_id": "pkg-a", "imported_modules": ["pkg_a"]}, {"package_id": "pkg-b", "imported_modules": ["pkg_b"]}],
            "LOADED_MODULE_DIRS": {"pkg-a": "<sandbox>/custom_nodes/pkg-a", "pkg-b": "<sandbox>/custom_nodes/pkg-b"},
            "EXTENSION_WEB_DIRS": {}, "filesystem": {"created": ["custom_nodes/pkg-a/__pycache__/x.pyc", "custom_nodes/pkg-b/x"]},
        }}
        selective = {"state": {
            "class_owner": {"A": "pkg-a"},
            "class_mappings": {"A": {"owner": "pkg-a"}},
            "RELATIVE_PYTHON_MODULE": {"A": "custom_nodes.pkg-a"},
            "display_mappings": {"A": "A"},
            "import_order": ["pkg-a"],
            "package_observations": [{"package_id": "pkg-a", "imported_modules": ["pkg_a"]}],
            "LOADED_MODULE_DIRS": {"pkg-a": "<sandbox>/custom_nodes/pkg-a"},
            "EXTENSION_WEB_DIRS": {}, "filesystem": {"created": ["custom_nodes/pkg-a/__pycache__/x.pyc"]},
        }}
        comparison = compare_scoped(full, selective, ["pkg-a"])
        self.assertTrue(comparison["exact_scoped_match"])
        selective["state"]["display_mappings"]["A"] = "changed"
        self.assertFalse(compare_scoped(full, selective, ["pkg-a"])["exact_scoped_match"])

    def test_package_audit_assigns_no_p_levels_and_flags_source(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "real-package"
            package.mkdir()
            (package / "__init__.py").write_text("import importlib\nPath('x').write_text('x')\n", encoding="utf-8")
            records = [{"package_id": "real-package", "install_path": str(package)}]
            audit = package_audits(records)[0]
            self.assertEqual(audit["proof_level"], "not_assigned")
            self.assertFalse(audit["safe_to_narrow"])
            self.assertTrue(audit["flags"]["dynamic_imports"])
            self.assertTrue(audit["flags"]["filesystem_writes"])

    def test_schema_constant_is_json_safe(self):
        self.assertEqual(json.loads(json.dumps({"schema_version": SCHEMA_VERSION}))["schema_version"], SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
