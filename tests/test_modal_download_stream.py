"""Regression tests for ``download_model_stream`` executor-backed exhaustion.

The streaming client pulls each item from a Modal generator inside the default
thread executor.  Passing raw ``next(gen)`` to the executor leaks the normal
generator ``StopIteration`` into the executor Future, which asyncio rejects
with ``TypeError: StopIteration interacts badly with generators and cannot be
raised into a Future``.  These tests exercise the in-thread sentinel wrapper
that replaced that path.
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path

import pytest


pytestmark = pytest.mark.fast_unit

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "modal_client.py"


def _load_module():
    """Load ``modal_client`` with a minimal fake ``modal`` module."""
    fake_modal = types.ModuleType("modal")
    fake_modal.Client = types.SimpleNamespace(  # type: ignore[attr-defined]
        from_credentials=lambda token_id, token_secret: {
            "token_id": token_id,
            "token_secret": token_secret,
        },
    )
    fake_modal.Function = types.SimpleNamespace(from_name=lambda *args, **kwargs: None)  # type: ignore[attr-defined]
    original_modal = sys.modules.get("modal")
    sys.modules["modal"] = fake_modal
    try:
        spec = importlib.util.spec_from_file_location("modal_client", MODULE_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if original_modal is not None:
            sys.modules["modal"] = original_modal
        else:
            sys.modules.pop("modal", None)


class _FakeHandle:
    """Stand-in Modal function handle whose ``remote_gen`` returns *gen*."""

    def __init__(self, gen):
        self._gen = gen

    def remote_gen(self, **kwargs):
        return self._gen


WORKSPACE = {"id": "ws_dl", "token_id": "ak-dl", "token_secret": "as-dl"}


async def _collect(module, gen):
    module._workspace_function = lambda name, workspace: _FakeHandle(gen)
    items = []
    async for item in module.download_model_stream(
        url="https://example.com/model.safetensors",
        filename="model.safetensors",
        workspace=WORKSPACE,
    ):
        items.append(item)
    return items


class DownloadModelStreamExhaustionTests(unittest.TestCase):
    def test_yields_progress_and_complete_then_terminates(self):
        def stream():
            yield {"status": "progress", "downloaded": 1}
            yield {"status": "progress", "downloaded": 2}
            yield {"status": "complete", "downloaded": 3}

        module = _load_module()
        items = asyncio.run(_collect(module, stream()))

        self.assertEqual(
            items,
            [
                {"status": "progress", "downloaded": 1},
                {"status": "progress", "downloaded": 2},
                {"status": "complete", "downloaded": 3},
            ],
        )

    def test_empty_generator_terminates_without_items(self):
        def stream():
            return
            yield  # pragma: no cover - keeps this a generator

        module = _load_module()
        items = asyncio.run(_collect(module, stream()))

        self.assertEqual(items, [])

    def test_exhausted_generator_would_raise_stopiteration_raw(self):
        """Pin the contract the sentinel wrapper exists to absorb."""
        def stream():
            yield {"status": "complete"}

        gen = stream()
        self.assertEqual(next(gen), {"status": "complete"})
        with self.assertRaises(StopIteration):
            next(gen)

    def test_exhaustion_helper_returns_sentinel_not_raises(self):
        module = _load_module()

        def stream():
            yield {"status": "complete"}

        gen = stream()
        self.assertEqual(module._next_download_item(gen), {"status": "complete"})
        self.assertIs(module._next_download_item(gen), module._DOWNLOAD_STREAM_EXHAUSTED)


if __name__ == "__main__":
    unittest.main()
