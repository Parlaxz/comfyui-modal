import asyncio
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "modal_client.py"


class _RemoteTarget:
    """Simulate ``handle.remote`` — a callable with an ``.aio`` async variant."""

    def __init__(self, label: str, calls: list, *, aio_delay: float = 0.0):
        self._label = label
        self._calls = calls
        self._aio_delay = aio_delay

    def __call__(self, *args, **kwargs):
        self._calls.append((self._label, args, kwargs))
        return {"label": self._label, "args": args, "kwargs": kwargs}

    @property
    def aio(self):
        """Async variant — returns an awaitable with optional delay."""
        _label = self._label
        _calls = self._calls
        _delay = self._aio_delay

        class _AioCallable:
            async def __call__(_self, *args, **kwargs):
                if _delay > 0:
                    await asyncio.sleep(_delay)
                _calls.append((_label, args, kwargs))
                return {"label": _label, "args": args, "kwargs": kwargs}

        return _AioCallable()


class _FakeRemoteCallable:
    """Fake Modal function handle — ``.remote`` returns a ``_RemoteTarget``.

    Modal API shape::

        handle.remote(...)        # sync
        handle.remote.aio(...)    # async
    """

    def __init__(self, label, calls, *, aio_delay=0.0):
        self._remote = _RemoteTarget(label, calls, aio_delay=aio_delay)

    @property
    def remote(self):
        return self._remote


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
            from_name=lambda app_name, name, client=None, environment_name=None: _FakeRemoteCallable(f"{name}:{client['token_id']}", calls),
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
            from_name=lambda app_name, name, client=None, environment_name=None: _FakeRemoteCallable(f"{name}:{client['token_id']}", calls),
        )
        fake_modal.Cls = types.SimpleNamespace(from_name=lambda *args, **kwargs: lambda: None)

        module = load_module(fake_modal)
        module.set_workspace_resolver(lambda: {"id": "ws_b", "token_id": "ak-b", "token_secret": "as-b"})
        result = asyncio.run(module.health_check())

        self.assertEqual(result["label"], "health_cpu:ak-b")


class TestWarmupProfileAsyncAPI(unittest.TestCase):
    """Tests for the new async warmup profile API in modal_client.

    Covers:
    1. ``set_active_warmup_profile`` uses ``handle.remote.aio()`` (not
       ``asyncio.to_thread`` + ``.remote()``).
    2. ``check_active_warmup_profile`` uses ``handle.remote.aio()``.
    3. ``_workspace_function`` cache key includes environment.
    4. TimeoutError propagates with clear context.
    5. Modal-exception re-raises with phase/workspace/app context.
    """

    def _make_fake_modal(self, calls, *, aio_delay=0.0):
        """Build a fake ``modal`` module with tracking for Function.from_name.

        When *aio_delay* > 0 the fake remote target sleeps before returning.
        """
        fake_modal = types.SimpleNamespace()
        fake_modal.Client = types.SimpleNamespace(
            from_credentials=lambda token_id, token_secret: {"token_id": token_id, "token_secret": token_secret},
        )
        fake_modal.Function = types.SimpleNamespace(
            from_name=lambda app_name, name, client=None, environment_name=None: (
                _FakeRemoteCallable(f"{name}:{client['token_id']}:env={environment_name}", calls, aio_delay=aio_delay)
            ),
        )
        return fake_modal

    # ── 1. set_active_warmup_profile uses remote.aio ──────────────────

    def test_set_active_warmup_profile_uses_remote_aio(self):
        """set_active_warmup_profile must call handle.remote.aio(),
        not convert to thread."""
        calls = []
        module = load_module(self._make_fake_modal(calls))
        workspace = {"id": "ws_a", "token_id": "ak-a", "token_secret": "as-a"}
        result = asyncio.run(module.set_active_warmup_profile(
            {"mode": "test"}, workspace=workspace,
        ))
        # The label includes env=None (no env var set)
        self.assertEqual(result["label"], "set_active_warmup_profile:ak-a:env=None")
        self.assertEqual(len(calls), 1)

    # ── 2. check_active_warmup_profile uses remote.aio ────────────────

    def test_check_active_warmup_profile_uses_remote_aio(self):
        """check_active_warmup_profile must call handle.remote.aio()."""
        calls = []
        module = load_module(self._make_fake_modal(calls))
        workspace = {"id": "ws_a", "token_id": "ak-a", "token_secret": "as-a"}
        result = asyncio.run(module.check_active_warmup_profile(
            "stable-key-abc", workspace=workspace,
        ))
        self.assertEqual(result["label"], "check_active_warmup_profile:ak-a:env=None")
        self.assertEqual(len(calls), 1)

    # ── 3. Environment-aware cache key ────────────────────────────────

    def test_workspace_function_cache_key_includes_environment(self):
        """_workspace_function must produce distinct cache entries for
        different environments (same name, same workspace)."""
        from_name_calls: list[tuple[str, str | None]] = []
        fake_modal = types.SimpleNamespace()
        fake_modal.Client = types.SimpleNamespace(
            from_credentials=lambda token_id, token_secret: {"token_id": token_id, "token_secret": token_secret},
        )
        fake_modal.Function = types.SimpleNamespace(
            from_name=lambda app_name, name, client=None, environment_name=None: (
                from_name_calls.append((name, environment_name)),
                _FakeRemoteCallable(f"{name}:{client['token_id']}:env={environment_name}", []),
            )[1],
        )
        module = load_module(fake_modal)
        workspace = {"id": "ws_a", "token_id": "ak-a", "token_secret": "as-a"}
        fn = module._workspace_function

        # First lookup: env="staging"
        h1 = fn("test_func", workspace, environment_name="staging")
        self.assertEqual(len(from_name_calls), 1, "First lookup must call from_name")
        self.assertEqual(from_name_calls[0], ("test_func", "staging"))

        # Second lookup: same env → cache hit (no from_name call)
        h2 = fn("test_func", workspace, environment_name="staging")
        self.assertEqual(len(from_name_calls), 1, "Same env must be cache hit")
        self.assertIs(h1, h2, "Same env must return same handle")

        # Third lookup: different env → cache miss (new from_name call)
        h3 = fn("test_func", workspace, environment_name="production")
        self.assertEqual(len(from_name_calls), 2, "Different env must be cache miss")
        self.assertEqual(from_name_calls[1], ("test_func", "production"))
        self.assertIsNot(h1, h3, "Different env must return different handle")

        # Fourth lookup: production again → cache hit
        h4 = fn("test_func", workspace, environment_name="production")
        self.assertEqual(len(from_name_calls), 2, "Production again must be cache hit")
        self.assertIs(h3, h4, "Production again must return same handle")

    # ── 4. TimeoutError propagation (via env-var timeout + aio_delay) ─

    def test_set_active_warmup_profile_timeout_propagates(self):
        """TimeoutError from setter must propagate with phase/app context."""
        calls = []
        module = load_module(self._make_fake_modal(calls, aio_delay=999))
        workspace = {"id": "ws_t", "token_id": "ak-t", "token_secret": "as-t"}
        with patch.dict(os.environ, {"COMFYMODAL_PROFILE_SETTER_TIMEOUT": "0.01"}, clear=False):
            with self.assertRaises(TimeoutError) as ctx:
                asyncio.run(module.set_active_warmup_profile(
                    {"mode": "test"}, workspace=workspace,
                ))
        msg = str(ctx.exception)
        self.assertIn("set_active_warmup_profile", msg,
                      "TimeoutError must identify the phase")
        self.assertIn(module.APP_NAME, msg,
                      "TimeoutError must identify the app name")

    def test_check_active_warmup_profile_timeout_propagates(self):
        """TimeoutError from checker must propagate with phase/app context."""
        calls = []
        module = load_module(self._make_fake_modal(calls, aio_delay=999))
        workspace = {"id": "ws_t", "token_id": "ak-t", "token_secret": "as-t"}
        with patch.dict(os.environ, {"COMFYMODAL_PROFILE_CHECKER_TIMEOUT": "0.01"}, clear=False):
            with self.assertRaises(TimeoutError) as ctx:
                asyncio.run(module.check_active_warmup_profile(
                    "stable-key-abc", workspace=workspace,
                ))
        msg = str(ctx.exception)
        self.assertIn("check_active_warmup_profile", msg,
                      "TimeoutError must identify the phase")
        self.assertIn(module.APP_NAME, msg,
                      "TimeoutError must identify the app name")

    # ── 5. _workspace_function passes environment_name to Modal SDK ────

    def test_workspace_function_passes_environment_name_to_sdk(self):
        """_workspace_function must forward environment_name to
        modal.Function.from_name."""
        captured_env: list[str | None] = []
        fake_modal = types.SimpleNamespace()
        fake_modal.Client = types.SimpleNamespace(
            from_credentials=lambda token_id, token_secret: {"token_id": token_id, "token_secret": token_secret},
        )
        fake_modal.Function = types.SimpleNamespace(
            from_name=lambda app_name, name, client=None, environment_name=None: (
                captured_env.append(environment_name),
                _FakeRemoteCallable(f"{name}", []),
            )[1],
        )
        module = load_module(fake_modal)
        workspace = {"id": "ws_e", "token_id": "ak-e", "token_secret": "as-e"}

        # Call with explicit environment
        module._workspace_function("test_func", workspace, environment_name="my-env")
        self.assertIn("my-env", captured_env,
                      "environment_name must be forwarded to Modal SDK")


class TestWarmupProfileCheckerTimeoutPropagation(unittest.TestCase):
    """Test that TimeoutError from checker is NOT swallowed in warmup_profile's
    fail-open path, but ordinary exceptions are."""

    def setUp(self):
        import warmup_profile
        warmup_profile._last_stable_profile_cache.clear()
        warmup_profile._last_cache_app_identity = ""
        warmup_profile._last_cache_ws_id = ""

    async def _do_prepare(self, checker=None, setter=None) -> dict:
        from warmup_profile import prepare_active_next_profile as _prepare
        import hashlib
        import json
        wf = {"2": {"class_type": "CLIPLoader",
                     "inputs": {"clip_name": "clip_l.safetensors", "type": "stable_diffusion"}}}
        ws = {"id": "ws_test"}
        return await _prepare(
            wf,
            hashlib.sha256(json.dumps(wf, sort_keys=True).encode()).hexdigest(),
            workspace=ws,
            setter=setter or _make_async_setter(),
            checker=checker,
        )

    # ── TimeoutError must propagate ──────────────────────────────────

    def test_checker_timeout_propagates_through_fail_open(self):
        """TimeoutError from checker must NOT be swallowed — it must
        propagate so the caller sees a hung platform."""
        async def _timeout_checker(stable_key, *, workspace=None):
            raise TimeoutError("checker timed out")

        with self.assertRaises(TimeoutError):
            asyncio.run(self._do_prepare(checker=_timeout_checker))

    # ── Ordinary exception is fail-open ──────────────────────────────

    def test_checker_other_exception_fails_open(self):
        """A non-Timeout exception from checker must be swallowed and
        the setter called instead."""
        call_counter = []
        setter = _make_async_setter(call_counter=call_counter)

        async def _failing_checker(stable_key, *, workspace=None):
            raise RuntimeError("checker internal error")

        result = asyncio.run(self._do_prepare(
            checker=_failing_checker,
            setter=setter,
        ))
        self.assertEqual(result["status"], "written",
                         "Failing checker must fail-open to setter")
        self.assertEqual(len(call_counter), 1,
                         "Setter must be called after checker failure")


def _make_async_setter(
    return_status: str = "written",
    call_counter: list | None = None,
):
    from unittest.mock import AsyncMock
    mock = AsyncMock(return_value={"status": return_status, "changed": True})
    if call_counter is not None:
        mock.side_effect = lambda *a, **kw: (
            call_counter.append(1),
            {"status": return_status, "changed": True},
        )[1]
    return mock


if __name__ == "__main__":
    unittest.main()
