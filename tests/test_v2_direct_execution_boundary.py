"""Regression coverage for the request-scoped V2 execution boundary."""

from __future__ import annotations

import asyncio

from canonical_execution import build_execution_plan, execute_plan
from comfymodal_runtime.modal_transport import ModalTransport


def test_execute_plan_submits_before_any_legacy_publisher_can_run():
    """A legacy publisher must be ignored; the first remote seam is execution."""
    observed: list[dict] = []

    class LegacyPublisher:
        def publish(self, _plan):
            raise AssertionError("restore-plan publication must not be called")

    async def stream(**kwargs):
        observed.append(kwargs)
        yield {"type": "result", "data": {"images": [], "outputs": {}}}

    async def run():
        plan = build_execution_plan(
            {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}},
            prompt_id="direct-boundary",
            validate=False,
        )
        result = await execute_plan(
            plan,
            transport=ModalTransport(prompt_stream_fn=stream),
            restore_publisher=LegacyPublisher(),
        )
        assert result["outputs"] == {}

    asyncio.run(run())
    assert len(observed) == 1
    assert observed[0]["workflow"] == {"1": {"class_type": "KSampler", "inputs": {"seed": 1}}}
    assert observed[0]["production_report"] == {}


def test_execute_plan_attaches_request_scoped_model_and_prefill_identity():
    observed: list[dict] = []

    async def stream(**kwargs):
        observed.append(kwargs)
        yield {"type": "result", "data": {"images": [], "outputs": {}}}

    async def run():
        plan = build_execution_plan(
            {
                "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
                "2": {"class_type": "KSampler", "inputs": {"seed": 1}},
            },
            prompt_id="identity-boundary",
            validate=False,
        )
        await execute_plan(plan, transport=ModalTransport(prompt_stream_fn=stream))

    asyncio.run(run())
    request_metadata = observed[0]["trace"].get("metadata", {})
    assert request_metadata.get("request_model_identity_hash")
    assert request_metadata.get("request_prefill_identity_hash")
