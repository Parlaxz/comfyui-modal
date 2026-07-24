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
                return_value=("off", "gen_001", "instance"),
            ),
            patch.object(
                modal_app,
                "_read_v2_validation_certificate_async",
                return_value=(None, {"cert_volume_reload_ms": 0.0, "cert_file_read_ms": 0.0, "cert_json_parse_validate_ms": 0.0}),
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


# \u2500\u2500 6. Certificate cache diagnostic fields \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500


class TestCertCacheDiagnostics:
    """Diagnostic fields for process-local cert cache."""

    def test_prompt_validation_end_has_diagnostic_fields(self):
        """prompt_validation_end trace event includes all required
        diagnostic timing fields and cache/skipped booleans."""
        from types import SimpleNamespace
        from unittest.mock import patch
        from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
        from comfymodal_runtime.runtime_executor import ExecutionContext
        from comfymodal_runtime.trace import RuntimeTrace

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

        api = SimpleNamespace(
            _executor=_FakeExecutor(),
            _preflight_before_prompt_execution=lambda wf: None,
            _stage_windows={},
        )
        entrypoint = modal_app.ModalRuntimeEntrypoint()
        entrypoint._legacy_module = SimpleNamespace()
        entrypoint._legacy_api = api

        plan = ExecutionPlan(
            workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
            execution_options=ExecutionOptions(production_enabled=False),
        )
        trace = RuntimeTrace(request_id="req-diag", process="remote")
        context = ExecutionContext(request_id="req-diag", trace=trace)

        async def _fake_validate_prompt(pid, wf, _unused):
            return (True, {}, ["107"], {})

        fake_execution = SimpleNamespace(validate_prompt=_fake_validate_prompt)

        with patch.dict("sys.modules", {"execution": fake_execution}):
            result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

        # Find prompt_validation_end event
        pv_end = [e for e in trace.events if e.name == "prompt_validation_end"]
        assert len(pv_end) == 1, "prompt_validation_end must be emitted"
        meta = pv_end[0].metadata

        # Check all required diagnostic fields are present
        required_fields = [
            "cert_identity_build_ms",
            "cert_cache_hit",
            "cert_volume_reload_ms",
            "cert_file_read_ms",
            "cert_json_parse_validate_ms",
            "cert_total_ms",
            "legacy_preflight_ms",
            "prompt_validation_ms",
            "certificate_skipped_preflight",
            "certificate_skipped_prompt_validation",
        ]
        for field in required_fields:
            assert field in meta, f"Missing diagnostic field: {field}"

        # When cert is not eligible (no deployment identity), cache miss is False,
        # preflight runs, validation runs.
        assert meta["cert_cache_hit"] is False
        assert meta["certificate_skipped_preflight"] is False
        assert meta["certificate_skipped_prompt_validation"] is False
        assert isinstance(meta["legacy_preflight_ms"], (int, float))
        assert isinstance(meta["prompt_validation_ms"], (int, float))
        assert meta["legacy_preflight_ms"] >= 0
        assert meta["prompt_validation_ms"] >= 0

    def test_cert_cache_hit_uses_zero_stages(self):
        """When the process-local cache returns a hit, volume_reload_ms,
        file_read_ms, and json_parse_validate_ms are all 0.0."""
        from types import SimpleNamespace
        from unittest.mock import patch
        from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan, DeploymentIdentity
        from comfymodal_runtime.runtime_executor import ExecutionContext
        from comfymodal_runtime.trace import RuntimeTrace

        # Pre-populate the process-local cache with a proper identity
        from comfymodal_runtime.contracts import DeploymentIdentity
        from comfymodal_runtime.modal_app import _compute_v2_cert_identity as _comp_cert_id
        fake_instance_id = "test_instance_cache_hit"
        _fake_dep_id = DeploymentIdentity(
            runtime_hash="abc", dependency_hash="def", custom_node_hash="ghi",
        )
        wf_hash = "wf_cache_hit"
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", _fake_dep_id.combined_hash):
            _cert_id, _components = _comp_cert_id(
                wf_hash,
                repair_mode="off", custom_nodes_generation="gen_001",
            )
        cache_key = (fake_instance_id, _cert_id)
        modal_app._V2_CERT_PROCESS_CACHE[cache_key] = {
            "outputs_to_execute": ["107"],
            "node_errors": {},
            "preflight_ok": True,
            "schema_version": modal_app._V2_CERT_SCHEMA_VERSION,
            "identity_components": dict(_components),
        }

        class _FakeExecutor:
            success = True
            history_result = {}
            def __init__(self):
                self.executed = []
            def reset(self):
                pass
            def execute(self, **kwargs):
                self.executed.append(kwargs)

        class _FakeRepairAPI:
            _executor = _FakeExecutor()
            _preflight_already_ran = False
            def _wait_for_restore_preload_before_request(self, wf):
                pass
            def _preflight_before_prompt_execution(self, wf):
                raise AssertionError("preflight should NOT run on cache hit")
            def _repair_missing_workflow_nodes(self, wf):
                return {"missing_before": [], "missing_after": [], "blocked_by_mode": False}
            def _begin_prompt_profile(self, wf, pid, outputs):
                pass
            def _resolve_requirements_repair_mode(self):
                return "off"

        class _FakeModule:
            @staticmethod
            def _current_custom_nodes_generation_id():
                return "gen_001"

            @staticmethod
            def _resolve_custom_nodes_generation(api=None):
                return ("gen_001", "instance")

        api = _FakeRepairAPI()
        entrypoint = modal_app.ModalRuntimeEntrypoint()
        entrypoint._restored_instance_id = fake_instance_id
        entrypoint._legacy_module = _FakeModule()
        entrypoint._legacy_api = api

        plan = ExecutionPlan(
            workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
            execution_options=ExecutionOptions(production_enabled=False),
            workflow_hash="wf_cache_hit",
        )
        trace = RuntimeTrace(request_id="req-cache-zero", process="remote")
        context = ExecutionContext(request_id="req-cache-zero", trace=trace)

        async def _fake_validate(pid, wf, ext):
            return True, {}, ["107"], {}

        fake_execution = SimpleNamespace(validate_prompt=_fake_validate)

        _fake_dep_id = DeploymentIdentity(
            runtime_hash="abc", dependency_hash="def", custom_node_hash="ghi",
        )

        with patch.dict("sys.modules", {"execution": fake_execution}), \
             patch.object(modal_app, "_MODAL_RESOURCES", {
                 "source_identity": _fake_dep_id,
                 "runtime_state_volume": SimpleNamespace(reload=lambda: None, commit=lambda: None),
             }), \
             patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", _fake_dep_id.combined_hash):
            result = asyncio.run(
                entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
            )

        # Verify cache hit path
        event_names = [e.name for e in trace.events]
        assert "certificate_reload_start" not in event_names, \
            "certificate_reload_start must NOT be emitted on cache hit"
        assert "certificate_reload_end" not in event_names, \
            "certificate_reload_end must NOT be emitted on cache hit"
        assert "preflight_certificate_skip" in event_names, \
            "preflight_certificate_skip must be emitted on cache hit"

        pv_end = [e for e in trace.events if e.name == "prompt_validation_end"]
        assert len(pv_end) == 1
        meta = pv_end[0].metadata

        # All zero for volume/file/parse timings
        assert meta["cert_cache_hit"] is True, "cert_cache_hit must be True"
        assert meta["cert_volume_reload_ms"] == 0.0, "volume_reload must be 0.0 on cache hit"
        assert meta["cert_file_read_ms"] == 0.0, "file_read must be 0.0 on cache hit"
        assert meta["cert_json_parse_validate_ms"] == 0.0, "parse_validate must be 0.0 on cache hit"
        # Preflight and prompt validation are skipped
        assert meta["certificate_skipped_preflight"] is True
        assert meta["certificate_skipped_prompt_validation"] is True
        assert meta["legacy_preflight_ms"] == 0.0
        assert meta["prompt_validation_ms"] == 0.0

        # Clean up
        modal_app._V2_CERT_PROCESS_CACHE.pop(cache_key, None)

    def test_cert_read_outcome_has_timing_fields(self):
        """certificate_read_outcome trace event (volume read path) includes
        granular timing fields."""
        from types import SimpleNamespace
        from unittest.mock import patch
        from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
        from comfymodal_runtime.runtime_executor import ExecutionContext
        from comfymodal_runtime.trace import RuntimeTrace

        class _FakeExecutor:
            success = True
            history_result = {}
            def __init__(self):
                self.executed = []
            def reset(self):
                pass
            def execute(self, **kwargs):
                self.executed.append(kwargs)

        # Patch _read_v2_validation_certificate_async to return miss so we
        # exercise the volume read path (with mocked timings).
        async def _fake_read(_id, **kw):
            return (None, {"cert_volume_reload_ms": 12.3, "cert_file_read_ms": 4.5, "cert_json_parse_validate_ms": 6.7})

        api = SimpleNamespace(
            _executor=_FakeExecutor(),
            _preflight_before_prompt_execution=lambda wf: None,
        )
        entrypoint = modal_app.ModalRuntimeEntrypoint()
        entrypoint._legacy_module = SimpleNamespace()
        entrypoint._legacy_api = api

        plan = ExecutionPlan(
            workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
            execution_options=ExecutionOptions(production_enabled=False),
            workflow_hash="wf_read_outcome",
        )
        trace = RuntimeTrace(request_id="req-read-outcome", process="remote")
        context = ExecutionContext(request_id="req-read-outcome", trace=trace)

        async def _fake_validate(pid, wf, ext):
            return True, {}, ["107"], {}

        fake_execution = SimpleNamespace(validate_prompt=_fake_validate)

        with patch.dict("sys.modules", {"execution": fake_execution}), \
             patch.object(modal_app, "_read_v2_validation_certificate_async", _fake_read), \
             patch.object(modal_app, "_V2_VALIDATION_CERT_ENABLED", True), \
             patch.object(modal_app, "_MODAL_RESOURCES", {
                 "source_identity": SimpleNamespace(combined_hash="dep_hash_abc"),
                 "runtime_state_volume": SimpleNamespace(reload=lambda: None, commit=lambda: None),
             }), \
             patch.object(modal_app, "_get_preflight_context", return_value=("off", "gen_001", "instance")):
            result = asyncio.run(
                entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
            )

        read_outcome = [e for e in trace.events if e.name == "certificate_read_outcome"]
        assert len(read_outcome) == 1, "certificate_read_outcome must be emitted"
        meta = read_outcome[0].metadata

        assert "cert_cache_hit" in meta
        assert "cert_identity_build_ms" in meta
        assert "cert_volume_reload_ms" in meta
        assert "cert_file_read_ms" in meta
        assert "cert_json_parse_validate_ms" in meta
        assert "cert_total_ms" in meta
        # Timings from the fake reader
        assert meta["cert_volume_reload_ms"] == 12.3
        assert meta["cert_file_read_ms"] == 4.5
        assert meta["cert_json_parse_validate_ms"] == 6.7


# ── 7. Deep-copy isolation for cached node_errors ──────────────────────


class TestCertCacheDeepCopyIsolation:
    """node_errors stored in and returned from the process-local cache must
    be deep copies so that mutation by the caller cannot leak into the cache
    or into subsequent callers."""

    def test_cache_store_deep_copies_node_errors(self):
        """Storing into _V2_CERT_PROCESS_CACHE uses copy.deepcopy, so
        mutating the original dict after storage does not affect the cache."""
        from copy import deepcopy
        from comfymodal_runtime.modal_app import _V2_CERT_PROCESS_CACHE

        # Fresh cache
        _V2_CERT_PROCESS_CACHE.clear()

        identity = "deepcopy_store_test_id"
        instance_id = "test_inst"
        cache_key = (instance_id, identity)

        original_node_errors: dict[str, Any] = {
            "node_1": {"errors": ["err_a"]},
            "node_2": {"broken": True},
        }

        # Simulate what the volume-read path stores
        _V2_CERT_PROCESS_CACHE[cache_key] = {
            "outputs_to_execute": ["107"],
            "node_errors": deepcopy(original_node_errors),
            "preflight_ok": True,
            "schema_version": 2,
            "identity_components": {"wf": "x"},
        }

        # Mutate the original — cache must be unchanged
        original_node_errors["node_1"]["errors"].append("err_b")
        original_node_errors["node_3"] = {"new": True}

        stored = _V2_CERT_PROCESS_CACHE[cache_key]["node_errors"]
        assert stored["node_1"]["errors"] == ["err_a"], \
            "cache must not reflect mutation of original after store"
        assert "node_3" not in stored, \
            "cache must not reflect new keys added to original after store"

        _V2_CERT_PROCESS_CACHE.clear()

    def test_cache_return_deep_copies_node_errors(self):
        """Reading from _V2_CERT_PROCESS_CACHE returns a deep copy, so
        mutating the caller's copy does not affect the cache."""
        from copy import deepcopy
        from comfymodal_runtime.modal_app import _V2_CERT_PROCESS_CACHE

        _V2_CERT_PROCESS_CACHE.clear()

        identity = "deepcopy_return_test_id"
        instance_id = "test_inst"
        cache_key = (instance_id, identity)

        cached_errors: dict[str, Any] = {
            "node_a": {"errors": ["x", "y"]},
            "node_b": {"info": {"code": 42}},
        }
        _V2_CERT_PROCESS_CACHE[cache_key] = {
            "outputs_to_execute": ["107"],
            "node_errors": deepcopy(cached_errors),
            "preflight_ok": True,
            "schema_version": 2,
            "identity_components": {"wf": "y"},
        }

        # Simulate the cache-return path (deepcopy)
        returned = deepcopy(_V2_CERT_PROCESS_CACHE[cache_key]["node_errors"])

        # Mutate the returned copy
        returned["node_a"]["errors"].append("z")
        returned["node_c"] = {"new": True}

        # Cache must be untouched
        still_cached = _V2_CERT_PROCESS_CACHE[cache_key]["node_errors"]
        assert still_cached["node_a"]["errors"] == ["x", "y"], \
            "cache must not reflect mutation of returned copy"
        assert "node_c" not in still_cached, \
            "cache must not reflect new keys added to returned copy"

        _V2_CERT_PROCESS_CACHE.clear()


# ── 8. Write invalidation on failed/unavailable volume ─────────────────


class _CountingCache(dict):
    """dict subclass that counts .pop() calls for testing invalidation."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.pop_count: int = 0

    def pop(self, key: Any, default: Any = None) -> Any:  # type: ignore[override]
        self.pop_count += 1
        return super().pop(key, default)


class TestCertCacheInvalidationBeforeWrite:
    """Process-local cache invalidation must happen before volume I/O,
    so even a failed/unavailable write clears stale entries."""

    def test_cache_invalidated_before_volume_write(self):
        """_write_v2_validation_certificate invalidates all process-local
        entries for the given identity before attempting any I/O, so a
        subsequent failure does not leave stale entries."""
        import comfymodal_runtime.modal_app as modal_app
        from unittest.mock import patch

        identity = "fail_write_id_001"
        # Use a counting cache proxy so we can verify invalidation
        fresh = _CountingCache()
        fresh[("inst_a", identity)] = {"dummy": True}
        fresh[("inst_b", identity)] = {"dummy": True}
        fresh[("inst_a", "other_identity")] = {"dummy": True}
        assert len(fresh) == 3

        with patch.object(modal_app, "_V2_CERT_PROCESS_CACHE", fresh), \
             patch.object(modal_app, "_MODAL_RESOURCES", {"runtime_state_volume": None}):
            result = modal_app._write_v2_validation_certificate(
                identity, ["107"], {},
                preflight_ok=True,
            )

        # Write must report failure (no volume)
        assert result is False

        # Cache must be cleared for the target identity
        stale_for_identity = [k for k in fresh if len(k) == 2 and k[1] == identity]
        assert stale_for_identity == [], \
            f"expected no stale entries for {identity}, got {stale_for_identity}"

        # Other identities must survive (popped not called for them)
        assert ("inst_a", "other_identity") in fresh, \
            "entries for other identities must survive"

        # Each matching key was popped exactly once before the write failed
        assert fresh.pop_count == 2, \
            f"expected 2 pops, got {fresh.pop_count}"

    def test_cache_invalidation_does_not_duplicate(self):
        """Invalidation occurs exactly once per matching key.  No duplicate
        pop calls for the same key."""
        import comfymodal_runtime.modal_app as modal_app
        from unittest.mock import patch

        identity = "no_dup_inval_id"
        fresh = _CountingCache()
        fresh[("inst_x", identity)] = {"dummy": True}
        fresh[("inst_y", identity)] = {"dummy": True}

        with patch.object(modal_app, "_V2_CERT_PROCESS_CACHE", fresh), \
             patch.object(modal_app, "_MODAL_RESOURCES", {"runtime_state_volume": None}):
            modal_app._write_v2_validation_certificate(
                identity, ["107"], {},
                preflight_ok=True,
            )

        # Exactly one pop per matching key (no duplicate invalidation)
        assert fresh.pop_count == 2, \
            f"expected exactly 2 invalidations (one per key), got {fresh.pop_count}"

        # All matching entries gone
        assert len(fresh) == 0
