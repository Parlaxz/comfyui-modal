"""Focused tests for V2 observability and async cert reload fixes.

Covers:
  1. ``ModalMountedStateVolume.reload_async()`` — native aio path and fallback.
  2. ``_V2_STAGE_MAP`` now includes cachedit, noise_inject, model_sampling,
     model_patch, sampler_setup entries.
  3. Stage-window timestamp capture works without ``COMFYMODAL_PROFILING``.
  4. Precise trace boundaries for cert reload/read, output-chain, and
     image-conversion work.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
from comfymodal_runtime.runtime_executor import ExecutionContext
from comfymodal_runtime.runtime_state import ModalMountedStateVolume
from comfymodal_runtime.trace import RuntimeTrace

import comfymodal_runtime.modal_app as modal_app


# ── Helpers ────────────────────────────────────────────────────────────


class _ReloadHandle:
    """Callable handle that also exposes ``.aio()`` — mimics Modal Function handles."""

    def __init__(self, parent: Any) -> None:
        self._parent = parent

    def __call__(self) -> None:
        self._parent._reload_calls += 1

    async def aio(self) -> None:
        self._parent._reload_aio_calls += 1


class _FakeModalVolume:
    """Fake Modal Volume whose ``.reload`` is a callable with ``.aio()``."""

    def __init__(self) -> None:
        self._reload_calls: int = 0
        self._reload_aio_calls: int = 0
        self.reload = _ReloadHandle(self)

    def commit(self) -> None:
        pass


class _FakeModalVolumeNoAio:
    """Fake Modal Volume WITHOUT ``.aio`` on reload — tests fallback path."""

    def __init__(self) -> None:
        self._reload_calls: int = 0
        self.reload = self._sync_reload

    def _sync_reload(self) -> None:
        self._reload_calls += 1

    def commit(self) -> None:
        pass


class _FakeExecutor:
    success = True
    history_result = {}

    def __init__(self):
        self.executed = []
        self.sync_called = False

    def reset(self):
        pass

    def execute(self, **kwargs):
        self.sync_called = True
        self.executed.append(kwargs)


def _make_api(
    stage_windows: dict[str, dict[str, float]] | None = None,
) -> SimpleNamespace:
    executor = _FakeExecutor()
    if stage_windows is None:
        stage_windows = {}
    return SimpleNamespace(
        _executor=executor,
        _begin_prompt_profile=lambda workflow, prompt_id, outputs_to_execute: None,
        _stage_windows=stage_windows,
    )


async def _fake_validate_prompt(pid: str, wf: Any, _unused: Any) -> tuple:
    """Async fake that matches the real ``execution.validate_prompt`` signature."""
    return (True, {}, ["107"], {})


def _run_execute(
    api: Any,
    *,
    stage_windows: dict[str, dict[str, float]] | None = None,
) -> tuple[dict[str, Any], RuntimeTrace]:
    """Run ``_execute_v2_prompt_executor`` with minimal wiring and return
    ``(result, trace)``.  Uses ``asyncio.run()`` internally."""
    if stage_windows is not None:
        api._stage_windows = stage_windows

    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()
    entrypoint._legacy_api = api

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="req-obs", process="remote")
    context = ExecutionContext(request_id="req-obs", trace=trace)

    fake_execution = SimpleNamespace(
        validate_prompt=_fake_validate_prompt,
    )

    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    return result, trace


# ── 1. ModalMountedStateVolume.reload_async() ─────────────────────────


class TestReloadAsync:
    """ModalMountedStateVolume.reload_async() behavior."""

    def test_reload_async_uses_aio_when_available(self):
        """When the modal volume's reload has an .aio coroutine, it is used."""
        fake_vol = _FakeModalVolume()
        vol = ModalMountedStateVolume("/tmp/test-root", fake_vol)

        asyncio.run(vol.reload_async())

        assert fake_vol._reload_aio_calls == 1, "aio must be called once"
        assert fake_vol._reload_calls == 0, "sync reload must NOT be called"

    def test_reload_async_falls_back_when_no_aio(self):
        """When the volume lacks .aio, asyncio.to_thread(self.reload) runs."""
        fake_vol = _FakeModalVolumeNoAio()
        vol = ModalMountedStateVolume("/tmp/test-root", fake_vol)

        asyncio.run(vol.reload_async())

        assert fake_vol._reload_calls == 1, "sync reload must be called as fallback"

    def test_reload_async_noop_when_no_reload(self):
        """When the volume has no reload at all, reload_async does nothing."""
        fake_vol = SimpleNamespace(commit=lambda: None)
        vol = ModalMountedStateVolume("/tmp/test-root", fake_vol)

        # Should not raise
        asyncio.run(vol.reload_async())

    def test_async_reload_reused_across_calls(self):
        """Calling reload_async twice uses aio each time when available."""
        fake_vol = _FakeModalVolume()
        vol = ModalMountedStateVolume("/tmp/test-root", fake_vol)

        async def run_twice():
            await vol.reload_async()
            await vol.reload_async()

        asyncio.run(run_twice())

        assert fake_vol._reload_aio_calls == 2, "aio must be called each time"
        assert fake_vol._reload_calls == 0


# ── 2. _V2_STAGE_MAP additions ────────────────────────────────────────


class TestV2StageMapAdditions:
    """New _V2_STAGE_MAP entries for cachedit, noise_inject, model_sampling,
    model_patch, sampler_setup."""

    def test_new_stages_are_mapped(self):
        """cachedit, noise_inject, model_sampling, model_patch, sampler_setup
        appear in _stage_timings when present in api._stage_windows."""
        fake_now = time.time()
        windows = {
            "unet_load":      {"start": fake_now - 20.0, "end": fake_now - 19.0},
            "clip_load":      {"start": fake_now - 19.0, "end": fake_now - 18.0},
            "vae_load":       {"start": fake_now - 18.0, "end": fake_now - 17.0},
            "clip_encode":    {"start": fake_now - 17.0, "end": fake_now - 15.0},
            "sampler":        {"start": fake_now - 15.0, "end": fake_now - 5.0},
            "vae_decode":     {"start": fake_now - 5.0,  "end": fake_now - 4.0},
            "cachedit":       {"start": fake_now - 4.0,  "end": fake_now - 3.5},
            "noise_inject":   {"start": fake_now - 3.5,  "end": fake_now - 3.0},
            "model_sampling": {"start": fake_now - 3.0,  "end": fake_now - 2.5},
            "model_patch":    {"start": fake_now - 2.5,  "end": fake_now - 2.0},
            "sampler_setup":  {"start": fake_now - 2.0,  "end": fake_now - 1.5},
        }
        api = _make_api(windows)
        result, trace = _run_execute(api)

        stages = result.get("_stage_timings", {})

        # Legacy stages still present
        assert stages.get("t6_sampler_start") == fake_now - 15.0
        assert stages.get("t7_vae_decode_end") == fake_now - 4.0

        # New stages
        assert stages.get("t8_cachedit_start") == fake_now - 4.0
        assert stages.get("t8_cachedit_end") == fake_now - 3.5
        assert stages.get("t8_noise_inject_start") == fake_now - 3.5
        assert stages.get("t8_noise_inject_end") == fake_now - 3.0
        assert stages.get("t4d_model_sampling_start") == fake_now - 3.0
        assert stages.get("t4d_model_sampling_end") == fake_now - 2.5
        assert stages.get("t4e_model_patch_start") == fake_now - 2.5
        assert stages.get("t4e_model_patch_end") == fake_now - 2.0
        assert stages.get("t8_sampler_setup_start") == fake_now - 2.0
        assert stages.get("t8_sampler_setup_end") == fake_now - 1.5

    def test_new_stages_absent_when_not_in_windows(self):
        """When stage_windows lacks the new keys, _stage_timings omits them."""
        fake_now = time.time()
        windows = {
            "unet_load": {"start": fake_now - 10.0, "end": fake_now - 9.0},
            "sampler":   {"start": fake_now - 5.0,  "end": fake_now - 1.0},
        }
        api = _make_api(windows)
        result, trace = _run_execute(api)

        stages = result.get("_stage_timings", {})
        assert stages.get("t6_sampler_start") == fake_now - 5.0
        # New keys must not appear
        assert "t8_cachedit_start" not in stages
        assert "t8_noise_inject_start" not in stages
        assert "t4d_model_sampling_start" not in stages
        assert "t4e_model_patch_start" not in stages
        assert "t8_sampler_setup_start" not in stages


# ── 3. Stage windows without PROFILING ────────────────────────────────


class TestStageWindowsWithoutProfiling:
    """Stage-window timestamp capture works without COMFYMODAL_PROFILING."""

    def test_stage_timings_in_result_when_no_profiling(self):
        """_stage_timings appears in result even when profiling would be off
        (the stage window capture runs unconditionally in _begin_profiled_node
        before the PROFILING_ENABLED guard)."""
        fake_now = time.time()
        windows = {
            "sampler":    {"start": fake_now - 3.0,  "end": fake_now - 1.0},
            "vae_decode": {"start": fake_now - 1.0,  "end": fake_now},
        }
        api = _make_api(windows)
        result, trace = _run_execute(api)

        stages = result.get("_stage_timings", {})
        assert stages.get("t6_sampler_start") == fake_now - 3.0
        assert stages.get("t6_sampler_end") == fake_now - 1.0
        assert stages.get("t7_vae_decode_start") == fake_now - 1.0
        assert stages.get("t7_vae_decode_end") == fake_now

    def test_stage_timings_empty_when_no_windows(self):
        """When _stage_windows is empty or absent, _stage_timings is absent."""
        api = _make_api()
        api._stage_windows = {}
        result, trace = _run_execute(api)
        assert "_stage_timings" not in result, (
            "no _stage_timings when stage_windows is empty"
        )

    def test_stage_timings_partial_window(self):
        """Partial windows (start only, no end) still forward start (each field
        is added independently — partial windows are not silently dropped)."""
        fake_now = time.time()
        windows = {
            "sampler": {"start": fake_now - 3.0},  # no end
        }
        api = _make_api(windows)
        result, trace = _run_execute(api)
        stages = result.get("_stage_timings", {})
        # The V2 map adds start/end independently, so a partial window
        # still contributes its start field.
        assert stages.get("t6_sampler_start") == fake_now - 3.0
        # End should be absent because the window has no end field.
        assert "t6_sampler_end" not in stages


# ── 4. Trace boundary events ──────────────────────────────────────────


class TestTraceBoundaries:
    """Precise trace.emit boundaries for cert, output-chain, conversion."""

    def test_output_chain_trace_events(self):
        """output_chain_start/end are emitted during execution."""
        api = _make_api()
        result, trace = _run_execute(api)

        event_names = [e.name for e in trace.events]
        assert "output_chain_start" in event_names
        assert "output_chain_end" in event_names

        chain_end = [e for e in trace.events if e.name == "output_chain_end"]
        assert len(chain_end) == 1
        assert chain_end[0].metadata.get("attempts", 0) > 0

    def test_output_conversion_events_not_emitted_when_original_format(self):
        """When output_format is 'original', no conversion events are emitted."""
        plan = ExecutionPlan(
            workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
            execution_options=ExecutionOptions(
                production_enabled=False,
                output_conversion_options={"format": "original"},
            ),
        )
        entrypoint = modal_app.ModalRuntimeEntrypoint()
        entrypoint._legacy_module = SimpleNamespace()
        entrypoint._legacy_api = _make_api()

        trace = RuntimeTrace(request_id="req-conv", process="remote")
        context = ExecutionContext(request_id="req-conv", trace=trace)

        fake_execution = SimpleNamespace(
            validate_prompt=_fake_validate_prompt,
        )
        api = _make_api()

        with patch.dict("sys.modules", {"execution": fake_execution}):
            asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

        event_names = [e.name for e in trace.events]
        assert "output_conversion_start" not in event_names
        assert "output_conversion_end" not in event_names

    def test_output_conversion_events_not_emitted_without_items(self):
        """Conversion events are NOT emitted when there are no output items
        (the condition at line 1286 requires selected.success and items)."""
        plan = ExecutionPlan(
            workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
            execution_options=ExecutionOptions(
                production_enabled=False,
                output_conversion_options={"format": "webp", "quality": 80},
            ),
        )
        entrypoint = modal_app.ModalRuntimeEntrypoint()
        entrypoint._legacy_module = SimpleNamespace()
        entrypoint._legacy_api = _make_api()

        trace = RuntimeTrace(request_id="req-conv-webp", process="remote")
        context = ExecutionContext(request_id="req-conv-webp", trace=trace)

        fake_execution = SimpleNamespace(
            validate_prompt=_fake_validate_prompt,
        )
        api = _make_api()

        with patch.dict("sys.modules", {"execution": fake_execution}):
            asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

        event_names = [e.name for e in trace.events]
        # No output items exist in the test — conversion condition is False
        assert "output_conversion_start" not in event_names

    def test_certificate_trace_events(self):
        """certificate_reload_start and certificate_read_outcome appear when
        cert is eligible."""
        plan = ExecutionPlan(
            workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
            execution_options=ExecutionOptions(production_enabled=False),
        )
        entrypoint = modal_app.ModalRuntimeEntrypoint()
        entrypoint._legacy_module = SimpleNamespace()

        # API must expose _preflight_before_prompt_execution and
        # _preflight_already_ran must be False for cert path to be entered.
        api = _make_api()
        api._preflight_before_prompt_execution = lambda workflow: None

        trace = RuntimeTrace(request_id="req-cert", process="remote")
        context = ExecutionContext(request_id="req-cert", trace=trace)

        fake_execution = SimpleNamespace(
            validate_prompt=_fake_validate_prompt,
        )

        # Patch _read_v2_validation_certificate_async to return None
        # (cert miss) so the trace events are deterministic regardless
        # of whether any on-disk cert file happens to exist.
        with (
            patch.dict("sys.modules", {"execution": fake_execution}),
            patch.object(modal_app, "_V2_VALIDATION_CERT_ENABLED", True),
            patch.object(modal_app, "_MODAL_RESOURCES", {
                "runtime_state_volume": SimpleNamespace(
                    reload=lambda: None,
                    commit=lambda: None,
                ),
                "source_identity": SimpleNamespace(combined_hash="dep_hash_abc"),
            }),
            patch.object(
                modal_app,
                "_get_preflight_context",
                return_value=("off", "gen_001"),
            ),
            patch.object(
                modal_app,
                "_read_v2_validation_certificate_async",
                return_value=None,
            ),
        ):
            asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

        event_names = [e.name for e in trace.events]
        assert "certificate_reload_start" in event_names
        assert "certificate_read_outcome" in event_names

        outcome = [e for e in trace.events if e.name == "certificate_read_outcome"]
        assert len(outcome) >= 1
        # Expected miss because we patched the read to return None
        assert outcome[0].metadata.get("hit") is False
        assert outcome[0].metadata.get("cert_identity", "") != ""

    def test_output_collect_trace_event(self):
        """output_collect_start and output_collect_end still appear."""
        api = _make_api()
        result, trace = _run_execute(api)

        event_names = [e.name for e in trace.events]
        assert "output_collect_start" in event_names
        assert "output_collect_end" in event_names

        collect_end = [e for e in trace.events if e.name == "output_collect_end"]
        assert len(collect_end) == 1
        assert "strategy" in collect_end[0].metadata
        assert "items" in collect_end[0].metadata


# ── 5. _V2_STAGE_MAP module constant ──────────────────────────────────


class TestV2StageMapConstant:
    """The _V2_STAGE_MAP tuple includes all expected entries."""

    def test_all_expected_entries_present(self):
        """_V2_STAGE_MAP contains all legacy and new entries."""
        expected_keys = {
            "unet_load", "clip_load", "vae_load", "clip_encode",
            "sampler", "vae_decode",
            "cachedit", "noise_inject", "model_sampling", "model_patch",
            "sampler_setup",
        }
        actual_keys = {entry[0] for entry in modal_app._V2_STAGE_MAP}
        assert expected_keys.issubset(actual_keys), (
            f"missing keys: {expected_keys - actual_keys}"
        )

    def test_entry_format(self):
        """Each entry is a 3-tuple of (stage_key, start_key, end_key)."""
        for entry in modal_app._V2_STAGE_MAP:
            assert isinstance(entry, tuple) and len(entry) == 3
            stage, sk, ek = entry
            assert isinstance(stage, str) and stage
            assert isinstance(sk, str) and sk
            assert isinstance(ek, str) and ek
            assert sk.endswith("_start"), f"{sk} must end with _start"
            assert ek.endswith("_end"), f"{ek} must end with _end"

    def test_no_duplicate_stage_keys(self):
        """No two entries share the same stage key."""
        keys = [entry[0] for entry in modal_app._V2_STAGE_MAP]
        assert len(keys) == len(set(keys)), f"duplicate stage keys: {keys}"
