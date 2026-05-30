import ast
import unittest
from pathlib import Path


COMFYAPP_PATH = Path(__file__).resolve().parents[1] / "comfyapp.py"


def _decorator_base_name(deco: ast.expr) -> str | None:
    """Return the trailing name of a decorator, handling both
    ``ast.Attribute`` (e.g. ``modal.concurrent``) and ``ast.Name`` (e.g. ``concurrent``)."""
    if isinstance(deco, ast.Call):
        func = deco.func
    else:
        func = deco
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _ast_literal_value(node: ast.expr):
    """Safely extract the literal value from an AST expression node."""
    if isinstance(node, ast.Constant):
        return node.value
    # Fallbacks for older Python AST representations
    if isinstance(node, ast.Str):
        return node.s
    if isinstance(node, ast.Num):
        return node.n
    return None


class ModalWorkerConfigTests(unittest.TestCase):
    def test_all_gpu_classes_use_single_prompt_concurrency(self):
        tree = ast.parse(COMFYAPP_PATH.read_text(encoding="utf-8"))
        targets = {"ComfyAPI", "ComfyAPI_A100", "ComfyAPI_T4"}
        found = {}
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in targets:
                for deco in node.decorator_list:
                    if _decorator_base_name(deco) == "concurrent":
                        kwargs = {kw.arg: _ast_literal_value(kw.value) for kw in deco.keywords}
                        found[node.name] = kwargs
        self.assertEqual(found["ComfyAPI"]["target_inputs"], 1)
        self.assertEqual(found["ComfyAPI"]["max_inputs"], 1)
        self.assertEqual(found["ComfyAPI_A100"]["target_inputs"], 1)
        self.assertEqual(found["ComfyAPI_A100"]["max_inputs"], 1)
        self.assertEqual(found["ComfyAPI_T4"]["target_inputs"], 1)
        self.assertEqual(found["ComfyAPI_T4"]["max_inputs"], 1)
