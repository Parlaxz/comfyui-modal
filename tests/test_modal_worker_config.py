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
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn('target_inputs=profile["target_inputs"]', source)
        self.assertIn('max_inputs=profile["max_inputs"]', source)

    def test_comfyapp_registers_gpu_classes_from_catalog(self):
        source = COMFYAPP_PATH.read_text(encoding="utf-8")
        self.assertIn("from gpu_catalog import", source)
        self.assertIn("globals()[class_name] = Generated", source)
        self.assertIn('"ComfyAPI"', source)
