"""Design skeletons for the active-profile/dispatch latency regressions.

These are scaffolds only.  They are skipped until the implementation exposes
the final seams needed for deterministic unit testing.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_comfyapp_runtime_state import load_module as load_comfyapp_module
from tests.test_input_image_paths import _load_init_module


DESIGN_ONLY = True
pytestmark = pytest.mark.skipif(DESIGN_ONLY, reason="design skeleton only")


REPO_ROOT = Path(__file__).resolve().parents[1]
MODAL_CLIENT_PATH = REPO_ROOT / "modal_client.py"


class _ControlledAsyncGen:
    """Async generator test double with explicit close tracking."""

    def __init__(self, items):
        self._items = list(items)
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        item = self._items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def aclose(self):
        self.closed = True


def _load_modal_client_with_fake_modal(fake_modal):
    original_modal = sys.modules.get("modal")
    sys.modules["modal"] = fake_modal
    sys.modules.pop("modal_client", None)
    try:
        return importlib.import_module("modal_client")
    finally:
        if original_modal is not None:
            sys.modules["modal"] = original_modal
        else:
            sys.modules.pop("modal", None)


@pytest.fixture
def comfyapp_module():
    return load_comfyapp_module()


@pytest.fixture
def modal_init_module():
    return _load_init_module()


@pytest.fixture
def production_on_off_profiles():
    shared = {
        "mode": "split",
        "unet": "flux.safetensors",
        "clip1": "clip_l.safetensors",
        "clip2": "t5xxl.safetensors",
        "clip_type": "flux",
        "vae": "ae.safetensors",
    }
    production_on = dict(shared, required_class_types=["Image Comparer (rgthree)", "ComfyModalProductionOutput"])
    production_off = dict(shared, required_class_types=["Image Comparer (rgthree)", "SaveImage"])
    return production_on, production_off


def test_latency_stable_key_same_for_production_on_and_off(comfyapp_module, production_on_off_profiles):
    """Identical model stacks should compute the same stable warmup key regardless of production mode."""
    pytest.skip("Implement against the final pure stable-key helper")


def test_latency_output_node_changes_do_not_change_stable_key(comfyapp_module):
    """Changing output-only node classes/IDs should not perturb the warmup cache key."""
    pytest.skip("Implement with two workflows that differ only in output nodes")


def test_latency_random_tokens_do_not_change_stable_key(comfyapp_module):
    """``profile_token``/``validation_token`` noise should be ignored by the stable key."""
    pytest.skip("Implement with payload variants differing only in random tokens")


def test_latency_timestamps_do_not_change_stable_key(comfyapp_module):
    """``created_at``/``expires_at`` changes should not trigger a new active-profile write."""
    pytest.skip("Implement with payload variants differing only in timestamp fields")


@pytest.mark.asyncio
async def test_latency_identical_profile_skips_remote_setter(modal_init_module):
    """A local stable-key cache should suppress duplicate ``set_active_warmup_profile`` calls."""
    pytest.skip("Implement around _execute_job or a small extracted active-profile helper")


@pytest.mark.asyncio
async def test_latency_changed_model_stack_calls_remote_setter_once(modal_init_module):
    """When the stable key changes, exactly one remote setter call should be made."""
    pytest.skip("Implement with two sequential jobs whose model stacks differ")


@pytest.mark.asyncio
async def test_latency_failed_remote_setter_does_not_update_local_cache(modal_init_module):
    """If the setter fails, the next identical request must retry instead of treating the key as cached."""
    pytest.skip("Implement with setter side_effect=[RuntimeError(...), {status: ok}] pattern")


def test_latency_remote_setter_skips_commit_for_stable_identical_content(comfyapp_module, tmp_path):
    """``_write_active_next_profile``/``_write_active_warmup_profile_payload`` should return unchanged without commit."""
    pytest.skip("Implement by patching ACTIVE_NEXT_PROFILE_PATH and vol.commit")


@pytest.mark.asyncio
async def test_latency_stream_completion_releases_all_gates_immediately():
    """Successful consumption of ``modal_client.run_prompt_stream`` must release semaphore/stream resources immediately."""
    pytest.skip("Implement with fake modal client + controlled async generator")


@pytest.mark.asyncio
async def test_latency_breaking_after_result_explicitly_closes_stream():
    """Caller break-after-result should trigger ``aclose()`` on the remote generator."""
    pytest.skip("Implement with controlled async generator.closed assertion")


@pytest.mark.asyncio
async def test_latency_cancellation_closes_stream():
    """Task cancellation while streaming should close the remote generator."""
    pytest.skip("Implement with cancelled consumer task and aclose assertion")


@pytest.mark.asyncio
async def test_latency_error_closes_stream():
    """Errors raised by the remote generator should still close the stream handle."""
    pytest.skip("Implement with generator raising after first item")


@pytest.mark.asyncio
async def test_latency_second_queued_request_does_not_wait_for_generator_gc():
    """A second request should start once the first stream closes, not after Python GC runs."""
    pytest.skip("Implement with semaphore-gated fake generator and two concurrent tasks")


@pytest.mark.asyncio
async def test_latency_queue_worker_survives_one_failed_job(modal_init_module):
    """``_process_queue`` should continue servicing later items after one job failure."""
    pytest.skip("Implement with patched _execute_job side_effect=[RuntimeError, None]")


def test_latency_deployment_state_reads_do_not_scan_all_custom_nodes_per_generation(modal_init_module):
    """Generation-path deploy-state checks should avoid a full custom-node fingerprint scan on every prompt."""
    pytest.skip("Implement with memoized fingerprint-status seam/call-count assertion")


@pytest.mark.asyncio
async def test_latency_timing_fields_reflect_handle_resolution_boundaries(modal_init_module):
    """Trace fields should distinguish active-profile write, handle resolution, and remote-call start."""
    pytest.skip("Implement with deterministic time.time side_effect and trace/meta assertions")


@pytest.mark.asyncio
async def test_latency_production_on_and_off_share_same_dispatch_path(modal_init_module):
    """Both production states should execute the same queue/dispatch path once execution_workflow is chosen."""
    pytest.skip("Implement by comparing call sequence/captured events for both modes")


def test_latency_production_compilation_stays_under_100ms():
    """``compile_production_workflow`` should stay below 100ms for a representative mocked workflow."""
    pytest.skip("Implement with perf_counter around a stable synthetic workflow")


def test_latency_direct_memory_production_output_remains_enabled(comfyapp_module):
    """Production/in-process path should continue using the direct sink registry instead of history/filesystem fallback."""
    pytest.skip("Implement with compile report + registry-first collection assertions")


def test_latency_no_global_model_read_serialization_introduced(comfyapp_module):
    """Distinct model reads should not be serialized behind one global lock or semaphore."""
    pytest.skip("Implement with two distinct model keys and concurrency instrumentation")
