"""Design skeletons for the production output-contract regressions.

These tests are intentionally skipped for now.
Set ``DESIGN_ONLY = False`` and replace each ``pytest.skip``/stub body with
real assertions as the fixes land.
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_input_image_paths import _load_init_module


DESIGN_ONLY = True
pytestmark = pytest.mark.skipif(DESIGN_ONLY, reason="design skeleton only")


def _remote_entry(
    filename: str,
    payload: bytes,
    *,
    node_id: str = "107",
    output_key: str,
    comparison_side: str,
    output_index: int,
    mime_type: str = "image/png",
    file_ext: str = ".png",
    image_format: str = "png",
) -> dict:
    return {
        "filename": filename,
        "data": base64.b64encode(payload).decode("ascii"),
        "node_id": node_id,
        "output_key": output_key,
        "comparison_side": comparison_side,
        "output_index": output_index,
        "mime_type": mime_type,
        "file_ext": file_ext,
        "format": image_format,
        "width": 64,
        "height": 64,
    }


class _FakePromptQueue:
    """Minimal PromptQueue stand-in for _finish_job/_execute_job tests."""

    def __init__(self):
        self.queue = []
        self.history = {}
        self.currently_running = {}
        self.server = MagicMock()
        self.mutex = MagicMock()

    def task_done(self, item_id, history_result, status=None, process_item=None):
        prompt = self.currently_running.pop(item_id)
        if process_item is not None:
            prompt = process_item(prompt)
        self.history[prompt[1]] = {
            "prompt": prompt,
            "outputs": {},
            "status": status,
        }
        self.history[prompt[1]].update(history_result)


@pytest.fixture
def modal_init_module():
    return _load_init_module()


@pytest.fixture
def dual_output_result():
    a_bytes = b"image-a-bytes"
    b_bytes = b"image-b-bytes"
    a_remote = _remote_entry(
        "compare_a.png",
        a_bytes,
        output_key="a_images",
        comparison_side="a",
        output_index=0,
    )
    b_remote = _remote_entry(
        "compare_b.webp",
        b_bytes,
        output_key="b_images",
        comparison_side="b",
        output_index=1,
        mime_type="image/webp",
        file_ext=".webp",
        image_format="webp",
    )
    result = {
        "images": [a_remote, b_remote],
        "outputs": {
            "107": {
                "a_images": [a_remote],
                "b_images": [b_remote],
            }
        },
    }
    return {
        "result": result,
        "a": a_remote,
        "b": b_remote,
        "a_bytes": a_bytes,
        "b_bytes": b_bytes,
    }


@pytest.fixture
def fake_prompt_queue():
    return _FakePromptQueue()


def _queue_item(prompt_id: str, workflow: dict | None = None, extra_data: dict | None = None):
    workflow = workflow or {"107": {"class_type": "Image Comparer (rgthree)", "inputs": {}}}
    extra_data = extra_data or {
        "client_id": "client-1",
        "workflow_hash": "hash-1",
        "prompt_summary": {"seed": 7, "width": 64, "height": 64},
        "model_stack": {},
        "trace": {},
        "gpu": "a10g",
        "modal_options": {},
        "execution_workflow": workflow,
        "production_report": {"enabled": True},
    }
    return (1, prompt_id, workflow, extra_data, list(workflow.keys()), {})


def test_output_contract_decodes_two_files_from_remote_result(modal_init_module, dual_output_result, tmp_path):
    """Call ``_materialize_modal_outputs`` and assert two remote payloads decode into two materialized entries."""
    pytest.skip("Implement with direct _materialize_modal_outputs assertions")


def test_output_contract_writes_exactly_two_files_to_disk(modal_init_module, dual_output_result, tmp_path):
    """Assert only A and B are written under ``tmp_path`` and no extra artifact appears."""
    pytest.skip("Implement with tmp_path directory listing + written_files assertions")


def test_output_contract_preserves_a_and_b_bytes_exactly(modal_init_module, dual_output_result, tmp_path):
    """Read the two written files back and compare byte-for-byte with source payloads."""
    pytest.skip("Implement with Path.read_bytes equality checks")


def test_output_contract_live_descriptors_point_to_existing_files(modal_init_module, dual_output_result, tmp_path):
    """``materialized_outputs`` descriptors should contain live ``path`` values that exist on disk."""
    pytest.skip("Implement with summary['materialized_outputs'] path existence assertions")


def test_output_contract_event_output_matches_rgthree_contract(modal_init_module, dual_output_result, tmp_path):
    """``event_outputs['107']`` must expose ``a_images`` and ``b_images`` only, without duplicate B in ``images``."""
    pytest.skip("Implement with captured executed-event payload assertions")


def test_output_contract_history_a_images_contains_a_descriptor(modal_init_module, dual_output_result, tmp_path):
    """History outputs for node 107 should retain the A descriptor in ``a_images``."""
    pytest.skip("Implement via _execute_job/_finish_job integration with fake queue")


def test_output_contract_history_b_images_contains_b_descriptor(modal_init_module, dual_output_result, tmp_path):
    """History outputs for node 107 should retain the B descriptor in ``b_images``."""
    pytest.skip("Implement via _execute_job/_finish_job integration with fake queue")


def test_output_contract_history_images_contains_primary_b_descriptor(modal_init_module, dual_output_result, tmp_path):
    """History outputs should also expose native ComfyUI ``images`` channel containing B only."""
    pytest.skip("Implement once the history-normalization seam is fixed")


def test_output_contract_no_third_file_is_written(modal_init_module, dual_output_result, tmp_path):
    """Guard against accidental duplicate flat-image materialization or synthetic third output."""
    pytest.skip("Implement with directory count and stable identity checks")


def test_output_contract_no_duplicate_b_event_is_emitted(modal_init_module, dual_output_result, tmp_path):
    """Ensure only one executed event is emitted for node 107 and B appears once across all event keys."""
    pytest.skip("Implement with captured events and flattened filename counts")


def test_output_contract_primary_output_is_b(modal_init_module, dual_output_result, tmp_path):
    """Primary output selection must prefer rgthree side B / ``b_images``."""
    pytest.skip("Implement with summary['primary_output'] assertions")


def test_output_contract_auto_save_saves_b_only(modal_init_module, dual_output_result, tmp_path):
    """Patch ``save_output_image`` and assert exactly one save call using B bytes."""
    pytest.skip("Implement with patched save_output_image call inspection")


def test_output_contract_auto_save_extension_matches_real_bytes(modal_init_module, dual_output_result, tmp_path):
    """When B is WebP, auto-save should receive ``file_ext='.webp'`` and the original WebP bytes."""
    pytest.skip("Implement with webp fixture and patched save_output_image kwargs")


@pytest.mark.asyncio
async def test_output_contract_finish_job_called_exactly_once(modal_init_module, dual_output_result, fake_prompt_queue, tmp_path):
    """Patch ``_finish_job`` around ``_execute_job`` and assert one success finalization call."""
    pytest.skip("Implement with patched run_prompt_stream + fake queue")


@pytest.mark.asyncio
async def test_output_contract_prompt_history_reports_success(modal_init_module, dual_output_result, fake_prompt_queue, tmp_path):
    """History entry status should resolve to success/completed=True after the job finishes."""
    pytest.skip("Implement with fake PromptQueue history inspection")


@pytest.mark.asyncio
async def test_output_contract_history_entry_references_existing_files(modal_init_module, dual_output_result, fake_prompt_queue, tmp_path):
    """After ``_execute_job``, every history output descriptor should reference a real file on disk."""
    pytest.skip("Implement with fake queue history + Path existence checks")


@pytest.mark.asyncio
async def test_output_contract_next_queued_job_runs_after_success(modal_init_module, dual_output_result, fake_prompt_queue, tmp_path):
    """A successful first job must not block a second queued job from executing/finalizing."""
    pytest.skip("Implement with _process_queue task, two enqueued items, and ordered call assertions")


@pytest.mark.asyncio
async def test_output_contract_post_notification_exception_cannot_skip_history_finalization(modal_init_module, dual_output_result, fake_prompt_queue, tmp_path):
    """Force a late ``_send``/notification failure and assert history finalization still occurs."""
    pytest.skip("Implement with side_effect on _send after materialization")


@pytest.mark.asyncio
async def test_output_contract_notify_started_nameerror_not_possible(modal_init_module, dual_output_result, fake_prompt_queue, tmp_path):
    """Regression guard: success path should not reference undefined ``_notify_started`` or equivalent late local."""
    pytest.skip("Implement with _execute_job smoke run and explicit failure message assertions")


@pytest.mark.asyncio
async def test_output_contract_production_off_behavior_unchanged(modal_init_module, dual_output_result, fake_prompt_queue, tmp_path):
    """Run the same job with production disabled and assert legacy/native output delivery stays stable."""
    pytest.skip("Implement as A/B comparison: production disabled vs enabled on identical result payload")
