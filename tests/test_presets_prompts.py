import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "presets.py"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("presets.py missing")
    spec = importlib.util.spec_from_file_location("presets", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _callable(module, name):
    fn = getattr(module, name, None)
    if fn is None:
        raise AssertionError(f"presets.py missing public function: {name}")
    return fn


class PromptPresetCRUDTests(unittest.TestCase):
    def test_create_prompt_preset(self):
        module = load_module()
        create = _callable(module, "create_prompt_preset")
        list_p = _callable(module, "list_prompt_presets")
        with tempfile.TemporaryDirectory() as tmp:
            preset = create(root=tmp, name="My Prompts",
                            shared_negative="blurry",
                            items=[
                                {"id": "p1", "label": "cat", "text": "a cat",
                                 "negative": None, "enabled": True},
                                {"id": "p2", "label": "dog", "text": "a dog",
                                 "negative": None, "enabled": True},
                            ])
            self.assertEqual(preset["name"], "My Prompts")
            self.assertEqual(len(preset["items"]), 2)
            presets = list_p(root=tmp)
            self.assertEqual(len(presets), 1)

    def test_load_prompt_preset_round_trip(self):
        module = load_module()
        create = _callable(module, "create_prompt_preset")
        get_p = _callable(module, "get_prompt_preset")
        with tempfile.TemporaryDirectory() as tmp:
            create(root=tmp, name="X", shared_negative="",
                   items=[{"id": "p1", "label": "x", "text": "x", "negative": None, "enabled": True}])
            preset = get_p(root=tmp, preset_id=list(_callable(module, "list_prompt_presets")(root=tmp))[0]["id"])
            self.assertEqual(preset["items"][0]["text"], "x")

    def test_rename_prompt_preset(self):
        module = load_module()
        create = _callable(module, "create_prompt_preset")
        rename = _callable(module, "rename_prompt_preset")
        get_p = _callable(module, "get_prompt_preset")
        list_p = _callable(module, "list_prompt_presets")
        with tempfile.TemporaryDirectory() as tmp:
            create(root=tmp, name="Old", shared_negative="",
                   items=[{"id": "p1", "label": "x", "text": "x", "negative": None, "enabled": True}])
            pid = list_p(root=tmp)[0]["id"]
            rename(root=tmp, preset_id=pid, new_name="New")
            self.assertEqual(get_p(root=tmp, preset_id=pid)["name"], "New")

    def test_duplicate_prompt_preset(self):
        module = load_module()
        create = _callable(module, "create_prompt_preset")
        duplicate = _callable(module, "duplicate_prompt_preset")
        list_p = _callable(module, "list_prompt_presets")
        with tempfile.TemporaryDirectory() as tmp:
            create(root=tmp, name="Source", shared_negative="",
                   items=[{"id": "p1", "label": "x", "text": "hello", "negative": None, "enabled": True}])
            src_id = list_p(root=tmp)[0]["id"]
            duplicate(root=tmp, preset_id=src_id, new_name="Copy")
            self.assertEqual(len(list_p(root=tmp)), 2)

    def test_delete_prompt_preset(self):
        module = load_module()
        create = _callable(module, "create_prompt_preset")
        delete = _callable(module, "delete_prompt_preset")
        list_p = _callable(module, "list_prompt_presets")
        with tempfile.TemporaryDirectory() as tmp:
            create(root=tmp, name="X", shared_negative="",
                   items=[{"id": "p1", "label": "x", "text": "x", "negative": None, "enabled": True}])
            pid = list_p(root=tmp)[0]["id"]
            delete(root=tmp, preset_id=pid)
            self.assertEqual(list_p(root=tmp), [])


class PromptPresetReorderTests(unittest.TestCase):
    def test_reorder_items(self):
        module = load_module()
        create = _callable(module, "create_prompt_preset")
        reorder = _callable(module, "reorder_prompt_items")
        get_p = _callable(module, "get_prompt_preset")
        list_p = _callable(module, "list_prompt_presets")
        with tempfile.TemporaryDirectory() as tmp:
            create(root=tmp, name="X", shared_negative="",
                   items=[
                       {"id": "p1", "label": "a", "text": "a", "negative": None, "enabled": True},
                       {"id": "p2", "label": "b", "text": "b", "negative": None, "enabled": True},
                       {"id": "p3", "label": "c", "text": "c", "negative": None, "enabled": True},
                   ])
            pid = list_p(root=tmp)[0]["id"]
            reorder(root=tmp, preset_id=pid, new_order=["p3", "p1", "p2"])
            preset = get_p(root=tmp, preset_id=pid)
            self.assertEqual([i["id"] for i in preset["items"]], ["p3", "p1", "p2"])


class PromptPresetDuplicateDetectionTests(unittest.TestCase):
    def test_detect_exact_duplicates(self):
        module = load_module()
        create = _callable(module, "create_prompt_preset")
        detect = _callable(module, "detect_prompt_duplicates")
        list_p = _callable(module, "list_prompt_presets")
        with tempfile.TemporaryDirectory() as tmp:
            create(root=tmp, name="X", shared_negative="neg",
                   items=[
                       {"id": "p1", "label": "a", "text": "hello", "negative": None, "enabled": True},
                       {"id": "p2", "label": "b", "text": "hello", "negative": None, "enabled": True},  # dup of p1
                       {"id": "p3", "label": "c", "text": "world", "negative": None, "enabled": True},
                   ])
            pid = list_p(root=tmp)[0]["id"]
            groups = detect(root=tmp, preset_id=pid)
            self.assertEqual(len(groups), 1)
            self.assertEqual(sorted(groups[0]), ["p1", "p2"])

    def test_disabled_items_excluded_from_duplicate_check(self):
        module = load_module()
        create = _callable(module, "create_prompt_preset")
        detect = _callable(module, "detect_prompt_duplicates")
        list_p = _callable(module, "list_prompt_presets")
        with tempfile.TemporaryDirectory() as tmp:
            create(root=tmp, name="X", shared_negative="",
                   items=[
                       {"id": "p1", "label": "a", "text": "x", "negative": None, "enabled": True},
                       {"id": "p2", "label": "b", "text": "x", "negative": None, "enabled": False},
                   ])
            pid = list_p(root=tmp)[0]["id"]
            groups = detect(root=tmp, preset_id=pid)
            self.assertEqual(groups, [])


class PromptImportTests(unittest.TestCase):
    def test_import_plain_text(self):
        module = load_module()
        imp = _callable(module, "import_prompts_from_text")
        with tempfile.TemporaryDirectory() as tmp:
            items = imp(text="a cat\na dog\na bird", shared_negative="blurry")
            self.assertEqual(len(items), 3)
            self.assertEqual(items[0]["text"], "a cat")
            self.assertEqual(items[0]["negative"], None)
            self.assertEqual(items[1]["label"], "a dog")


if __name__ == "__main__":
    unittest.main()
