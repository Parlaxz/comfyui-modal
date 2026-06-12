import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "modal_client.py"


class _FakeRemoteCallable:
    def __init__(self, label, calls):
        self.label = label
        self.calls = calls

    def remote(self, *args, **kwargs):
        self.calls.append((self.label, args, kwargs))
        return {"label": self.label, "args": args, "kwargs": kwargs}


def load_module(fake_modal):
    original_modal = sys.modules.get("modal")
    sys.modules["modal"] = fake_modal
    try:
        spec = importlib.util.spec_from_file_location("modal_client", MODULE_PATH)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if original_modal is not None:
            sys.modules["modal"] = original_modal
        else:
            sys.modules.pop("modal", None)


class ModalClientWorkspaceTests(unittest.TestCase):
    def test_list_models_uses_explicit_workspace_client(self):
        calls = []
        fake_modal = types.SimpleNamespace()
        fake_modal.Client = types.SimpleNamespace(
            from_credentials=lambda token_id, token_secret: {"token_id": token_id, "token_secret": token_secret},
        )
        fake_modal.Function = types.SimpleNamespace(
            from_name=lambda app_name, name, client=None: _FakeRemoteCallable(f"{name}:{client['token_id']}", calls),
        )
        fake_modal.Cls = types.SimpleNamespace(from_name=lambda *args, **kwargs: lambda: None)

        module = load_module(fake_modal)
        workspace = {"id": "ws_a", "token_id": "ak-a", "token_secret": "as-a"}
        result = asyncio.run(module.list_models(workspace=workspace))

        self.assertEqual(result["label"], "list_models_cpu:ak-a")
        self.assertEqual(calls[0][0], "list_models_cpu:ak-a")

    def test_workspace_resolver_is_used_when_workspace_kwarg_missing(self):
        calls = []
        fake_modal = types.SimpleNamespace()
        fake_modal.Client = types.SimpleNamespace(
            from_credentials=lambda token_id, token_secret: {"token_id": token_id, "token_secret": token_secret},
        )
        fake_modal.Function = types.SimpleNamespace(
            from_name=lambda app_name, name, client=None: _FakeRemoteCallable(f"{name}:{client['token_id']}", calls),
        )
        fake_modal.Cls = types.SimpleNamespace(from_name=lambda *args, **kwargs: lambda: None)

        module = load_module(fake_modal)
        module.set_workspace_resolver(lambda: {"id": "ws_b", "token_id": "ak-b", "token_secret": "as-b"})
        result = asyncio.run(module.health_check())

        self.assertEqual(result["label"], "health_cpu:ak-b")


if __name__ == "__main__":
    unittest.main()
