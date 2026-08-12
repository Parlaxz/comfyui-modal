"""Tests for the ``execute_plan`` inherit no-op gate.

When the effective requested env profile is the deploy default ``inherit``
(no request-carried ``env_profile`` and no ``COMFYMODAL_V2_ENV_PROFILE``)
AND no warmup-profile consumer is active (``COMFYMODAL_V2_CPU_MODEL_SNAPSHOT``,
``COMFYMODAL_PERSISTENT_CLIP_CACHE``, ``ENABLE_WARMUP``), the pre-submission
profile checker/setter calls are SKIPPED entirely (decision
``skipped_inherit_noop``, ``profile_setter_performed=False``).  The full
checker/setter path still runs for explicit profile changes
(``production``/``diagnostic``) or active consumer flags, and the Modal
submission always happens regardless.

Mirrors the style of ``test_v2_local_pre_submit_optimization.py``.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import unittest
from unittest.mock import patch

from canonical_execution import (
    _reset_profile_prep_cache,
    _reset_restore_publish_cache,
    build_execution_plan,
    execute_plan,
)
from comfymodal_runtime.modal_transport import ModalTransport
from comfymodal_runtime.trace import RuntimeTrace
from warmup_profile import (
    _reset_last_stable_profile_cache,
    active_next_publication_required,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ── Counting doubles ─────────────────────────────────────────────────────────


class _CountingSetter:
    """Async setter that counts invocations and reports a successful write."""

    def __init__(self):
        self.invoke_count = 0

    async def __call__(self, payload, *, workspace=None):
        self.invoke_count += 1
        return {"status": "written", "changed": True}


class _CountingChecker:
    """Async checker that counts invocations; ``matched`` is configurable."""

    def __init__(self, matched: bool = True):
        self.invoke_count = 0
        self._matched = matched

    async def __call__(self, stable_key, *, workspace=None):
        self.invoke_count += 1
        return {"matched": self._matched, "profile_token": "t"}


# ═══════════════════════════════════════════════════════════════════════════
# TestInheritNoopGate — execute_plan level
# ═══════════════════════════════════════════════════════════════════════════


class TestInheritNoopGate(unittest.TestCase):
    """The inherit no-op gate skips checker/setter while submission proceeds."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()
        _reset_restore_publish_cache()

    def _run_execute_plan(
        self,
        setter=None,
        checker=None,
        env_extra=None,
        request_env_profile=None,
        trace=None,
    ):
        """Run ``execute_plan`` under a controlled env and return the result.

        The effective requested env profile is resolved by ``execute_plan``
        as: ``request_metadata.request_origin_info.env_profile`` first, the
        process ``COMFYMODAL_V2_ENV_PROFILE`` second, and the deploy default
        ``"inherit"`` otherwise.  Any env var not explicitly supplied via
        *env_extra* is removed so a stale host value cannot change the
        decision.  A flag records whether the submission stream was iterated.
        """
        env_extra = dict(env_extra or {})
        self._stream_iterated = False

        async def _stream(**kwargs):
            self._stream_iterated = True
            yield {"type": "result", "data": {"images": [], "outputs": {}}}

        async def _run():
            plan = build_execution_plan(
                {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
                prompt_id="inherit_noop_test",
                validate=False,
                request_metadata=(
                    {"request_origin_info": {"env_profile": request_env_profile}}
                    if request_env_profile else None
                ),
            )
            transport = ModalTransport(prompt_stream_fn=_stream)
            return await execute_plan(
                plan,
                transport=transport,
                profile_setter=setter,
                profile_checker=checker,
                workspace={"id": "ws_inherit_noop"},
                trace=trace,
            )

        with patch.dict(os.environ, env_extra, clear=False):
            # Ensure default inherit when not explicitly provided.
            if "COMFYMODAL_V2_ENV_PROFILE" not in env_extra:
                os.environ.pop("COMFYMODAL_V2_ENV_PROFILE", None)
            # Neutralize consumer flags that could leak from the host env.
            for _flag in (
                "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT",
                "COMFYMODAL_PERSISTENT_CLIP_CACHE",
                "ENABLE_WARMUP",
                "DISABLE_ACTIVE_NEXT_WRITE",
            ):
                if _flag not in env_extra:
                    os.environ.pop(_flag, None)
            return asyncio.run(_run())

    # ── default inherit: gate active ────────────────────────────────────────

    def test_inherit_default_skips_checker_and_setter(self):
        """Default (inherit, no consumers) skips checker and setter but the
        submission stream is still consumed and the result is returned."""
        setter = _CountingSetter()
        checker = _CountingChecker()
        result = self._run_execute_plan(setter=setter, checker=checker)

        self.assertEqual(setter.invoke_count, 0,
                         "inherit default must never invoke the setter")
        self.assertEqual(checker.invoke_count, 0,
                         "inherit default must never invoke the checker")
        self.assertTrue(self._stream_iterated,
                        "submission stream must still be consumed")
        self.assertIn("trace", result)

        md = result["trace"].get("metadata", {})
        self.assertIs(md.get("profile_setter_performed"), False)
        self.assertIs(md.get("profile_checker_performed"), False)
        self.assertEqual(md.get("active_profile_publish_decision"),
                         "skipped_inherit_noop")
        self.assertIs(md.get("profile_override_applied"), False)
        self.assertEqual(md.get("profile_requested_env"), "inherit")
        total_ms = md.get("active_profile_total_ms", 9999)
        self.assertLess(total_ms, 5000,
                        "noop gate must not add meaningful latency")

    def test_inherit_noop_emits_trace_event(self):
        """The trace carries ``active_profile_inherit_noop`` and an
        ``active_next_profile_end`` event with decision ``skipped_inherit_noop``."""
        trace = RuntimeTrace(request_id="inherit_noop_events", process="local")
        self._run_execute_plan(setter=_CountingSetter(), trace=trace)

        names = [e.name for e in trace.events]
        self.assertIn("active_profile_inherit_noop", names)
        end_events = [e for e in trace.events if e.name == "active_next_profile_end"]
        self.assertEqual(len(end_events), 1,
                         "exactly one active_next_profile_end event")
        self.assertEqual(end_events[0].metadata.get("decision"),
                         "skipped_inherit_noop")

    def test_inherit_noop_breakdown_line(self):
        """The ``[active_profile.publish]`` console line reports the skip."""
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            self._run_execute_plan(setter=_CountingSetter())
        output = captured.getvalue()
        self.assertIn("[active_profile.publish]", output)
        self.assertIn("decision=skipped_inherit_noop", output)

    # ── explicit profile changes / consumers: full path kept ───────────────

    def test_production_keeps_setter(self):
        """``COMFYMODAL_V2_ENV_PROFILE=production`` keeps the full path."""
        setter = _CountingSetter()
        # Non-matching checker so the setter is actually reached (a matching
        # checker would short-circuit before the setter).
        checker = _CountingChecker(matched=False)
        self._run_execute_plan(
            setter=setter,
            checker=checker,
            env_extra={"COMFYMODAL_V2_ENV_PROFILE": "production"},
        )
        self.assertEqual(setter.invoke_count, 1)

    def test_inherit_with_cpu_snapshot_keeps_setter(self):
        """inherit env + ``COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`` consumer."""
        setter = _CountingSetter()
        self._run_execute_plan(
            setter=setter,
            env_extra={"COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "1"},
        )
        self.assertEqual(setter.invoke_count, 1)

    def test_inherit_with_persistent_cache_keeps_setter(self):
        """inherit env + ``COMFYMODAL_PERSISTENT_CLIP_CACHE=1`` consumer."""
        setter = _CountingSetter()
        self._run_execute_plan(
            setter=setter,
            env_extra={"COMFYMODAL_PERSISTENT_CLIP_CACHE": "1"},
        )
        self.assertEqual(setter.invoke_count, 1)

    # ── request-carried env profile ─────────────────────────────────────────

    def test_request_carried_production_keeps_setter(self):
        """A request-carried ``env_profile=production`` runs the full path
        even though the process env defaults to inherit."""
        setter = _CountingSetter()
        self._run_execute_plan(setter=setter, request_env_profile="production")
        self.assertEqual(setter.invoke_count, 1)

    def test_request_carried_inherit_skips_even_if_env_production(self):
        """Request-carried ``inherit`` is a no-op override: even with the
        process env pinned to production the setter is skipped.  Deployments
        that need the volume-published active-next profile must set a
        consumer flag (``COMFYMODAL_V2_CPU_MODEL_SNAPSHOT`` etc.)."""
        setter = _CountingSetter()
        self._run_execute_plan(
            setter=setter,
            request_env_profile="inherit",
            env_extra={"COMFYMODAL_V2_ENV_PROFILE": "production"},
        )
        self.assertEqual(setter.invoke_count, 0)


# ═══════════════════════════════════════════════════════════════════════════
# TestActiveNextPublicationRequired — decision table unit tests
# ═══════════════════════════════════════════════════════════════════════════


class TestActiveNextPublicationRequired(unittest.TestCase):
    """Decision table for ``warmup_profile.active_next_publication_required``."""

    def setUp(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()

    def tearDown(self):
        _reset_profile_prep_cache()
        _reset_last_stable_profile_cache()

    def _required(self, env=None, env_profile_param=None) -> bool:
        env = dict(env or {})
        with patch.dict(os.environ, env, clear=False):
            # Remove stale keys not explicitly supplied so the decision is
            # driven only by the case under test.
            for _key in (
                "COMFYMODAL_V2_ENV_PROFILE",
                "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT",
                "COMFYMODAL_PERSISTENT_CLIP_CACHE",
                "ENABLE_WARMUP",
                "DISABLE_ACTIVE_NEXT_WRITE",
            ):
                if _key not in env:
                    os.environ.pop(_key, None)
            return active_next_publication_required(env_profile_param)

    def test_default_no_env_false(self):
        self.assertIs(self._required(), False)

    def test_env_profile_empty_false(self):
        self.assertIs(self._required({"COMFYMODAL_V2_ENV_PROFILE": ""}), False)

    def test_env_profile_inherit_false(self):
        self.assertIs(self._required({"COMFYMODAL_V2_ENV_PROFILE": "inherit"}), False)

    def test_env_profile_production_true(self):
        self.assertIs(self._required({"COMFYMODAL_V2_ENV_PROFILE": "production"}), True)

    def test_env_profile_diagnostic_true(self):
        self.assertIs(self._required({"COMFYMODAL_V2_ENV_PROFILE": "diagnostic"}), True)

    def test_inherit_with_cpu_snapshot_true(self):
        self.assertIs(
            self._required({
                "COMFYMODAL_V2_ENV_PROFILE": "inherit",
                "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "1",
            }),
            True,
        )

    def test_inherit_with_persistent_clip_cache_true(self):
        self.assertIs(
            self._required({
                "COMFYMODAL_V2_ENV_PROFILE": "inherit",
                "COMFYMODAL_PERSISTENT_CLIP_CACHE": "1",
            }),
            True,
        )

    def test_inherit_with_warmup_true(self):
        self.assertIs(
            self._required({
                "COMFYMODAL_V2_ENV_PROFILE": "inherit",
                "ENABLE_WARMUP": "1",
            }),
            True,
        )

    def test_inherit_with_disabled_write_false(self):
        self.assertIs(
            self._required({
                "COMFYMODAL_V2_ENV_PROFILE": "inherit",
                "DISABLE_ACTIVE_NEXT_WRITE": "1",
            }),
            False,
        )

    def test_env_profile_param_overrides_env(self):
        """The *env_profile* parameter wins over the process env."""
        # param "production" with env inherit → required
        self.assertIs(self._required({"COMFYMODAL_V2_ENV_PROFILE": "inherit"},
                                     env_profile_param="production"), True)
        # param "inherit" with env production → not required (no consumer)
        self.assertIs(self._required({"COMFYMODAL_V2_ENV_PROFILE": "production"},
                                     env_profile_param="inherit"), False)


if __name__ == "__main__":
    unittest.main()
