from __future__ import annotations

from types import SimpleNamespace

import pytest

import studio_golden_run
from studio_golden_run import GoldenStageEventStore
from tools.v2_control import profile_catalog


pytestmark = pytest.mark.fast_unit


def _profile():
    return profile_catalog.GoldenProfile(
        name="golden-test",
        owner="test",
        target={
            "app": "configured-app",
            "class": "ModalRuntimeEntrypointV2",
            "method": "run_golden_studio_stream",
        },
        resources={"gpu": "H100", "cpu": 12, "memory_mb": 24576},
        config=SimpleNamespace(),  # type: ignore[arg-type]
        receipt=SimpleNamespace(deploy_fingerprint="deploy-test"),  # type: ignore[arg-type]
    )


class _Harness:
    """Fake bundle/prep/history/materialize seam + capturing Modal handle."""

    def __init__(self, monkeypatch, events):
        self.calls = 0
        self.begun = []
        self.completed = []
        self.failed = []
        monkeypatch.setattr(studio_golden_run, "resolve_golden_profile", lambda name: _profile())
        captured = {}
        self.captured = captured

        class RemoteGenerator:
            def aio(inner_self, payload, **kwargs):
                captured["payload"] = payload

                async def gen():
                    for event in events:
                        yield event

                return gen()

        self.handle = SimpleNamespace(
            **{studio_golden_run.STUDIO_BATCH_METHOD: SimpleNamespace(remote_gen=RemoteGenerator())}
        )

        import studio_workflow_run

        monkeypatch.setattr(
            studio_workflow_run,
            "resolve_workflow_run_bundle",
            lambda *args, **kwargs: {
                "status": "ok",
                "defaults": {},
                "control_schema": {},
                "executable_prompt": {},
                "mapping": None,
                "version": {},
            },
        )

        def fake_merge(defaults, controls, schema):
            controls = dict(controls)
            if controls.get("bad"):
                return {"errors": [{"field": "seed", "message": "bad seed"}], "values": {}}
            return {"errors": [], "values": controls}

        monkeypatch.setattr(studio_workflow_run, "merge_workflow_controls", fake_merge)
        monkeypatch.setattr(
            studio_golden_run,
            "_prepare_variant_prompt",
            lambda bundle, values, options: ({"workflow": {"echo": dict(values)}}, {"h": 1}, []),
        )
        monkeypatch.setattr(
            studio_golden_run, "_canonical_golden_fast_path", lambda workflow: "slow" not in workflow.get("echo", {})
        )
        harness = self

        def fake_begin(request_id, profile, controls, method=""):
            harness.begun.append(request_id)
            return (request_id + "-run", request_id + "-gen")

        def fake_complete(run_id, materialized, timings=None):
            harness.completed.append(run_id)

        def fake_fail(run_id, error):
            harness.failed.append(run_id)

        monkeypatch.setattr(studio_golden_run, "_begin_golden_history", fake_begin)
        monkeypatch.setattr(studio_golden_run, "_complete_golden_history", fake_complete)
        monkeypatch.setattr(studio_golden_run, "_fail_golden_history", fake_fail)
        monkeypatch.setattr(
            studio_golden_run,
            "_materialize_image",
            lambda result, request_id: {"output_paths": ["img_" + request_id + ".png"]},
        )
        monkeypatch.setattr(studio_golden_run, "_golden_stage_timings", lambda events: {})

    def factory(self, *_args):
        self.calls += 1
        return self.handle


def _ok_events(*vids):
    events = []
    for vid in vids:
        events.append({"type": "variant_start", "variant_request_id": vid})
        events.append({"type": "variant_result", "variant_request_id": vid, "data": {"images": []}})
    events.append({"type": "batch_result", "results": [{"variant_request_id": vid} for vid in vids]})
    return events


def _call_kwargs(tmp_path, variants, **overrides):
    kwargs = {
        "workflow_id": "wf",
        "version_id": "wv",
        "variants": variants,
        "request_id": "batch-1",
        "node_dir": tmp_path,
        "profile_name": "golden-test",
    }
    kwargs.update(overrides)
    return kwargs


@pytest.mark.asyncio
async def test_batch_rejects_empty_variants(monkeypatch, tmp_path) -> None:
    harness = _Harness(monkeypatch, [])
    store = GoldenStageEventStore(max_events=8, max_runs=4, ttl_seconds=60)
    result = await studio_golden_run.run_golden_workflow_batch(
        **_call_kwargs(tmp_path, [], event_store=store, handle_factory=harness.factory)
    )
    assert result["status"] == "error"
    assert result["error_code"] == "BATCH_VARIANTS_REQUIRED"
    assert harness.calls == 0


@pytest.mark.asyncio
async def test_batch_has_no_variant_cap(monkeypatch, tmp_path) -> None:
    vids = [f"v-{i}" for i in range(60)]
    events = _ok_events(*vids)
    harness = _Harness(monkeypatch, events)
    store = GoldenStageEventStore(max_events=128, max_runs=4, ttl_seconds=60)
    variants = [{"request_id": vid, "controls": {"seed": i}} for i, vid in enumerate(vids)]
    result = await studio_golden_run.run_golden_workflow_batch(
        **_call_kwargs(tmp_path, variants, event_store=store, handle_factory=harness.factory)
    )
    assert result["status"] == "ok"
    assert [entry["request_id"] for entry in result["results"]] == vids
    assert harness.calls == 1
    assert len(harness.captured["payload"]["variants"]) == 60


@pytest.mark.asyncio
async def test_batch_rejects_malformed_variants(monkeypatch, tmp_path) -> None:
    store = GoldenStageEventStore(max_events=8, max_runs=4, ttl_seconds=60)
    bad_batches = [
        [{"request_id": "v-1"}],  # missing controls
        [{"request_id": "v-1", "controls": {"seed": 1}}, {"request_id": "v-1", "controls": {}}],  # dup ids
        [{"request_id": "not valid!!", "controls": {}}],  # bad id
        ["nope"],  # not a mapping
    ]
    for variants in bad_batches:
        harness = _Harness(monkeypatch, [])
        result = await studio_golden_run.run_golden_workflow_batch(
            **_call_kwargs(tmp_path, variants, event_store=store, handle_factory=harness.factory)
        )
        assert result["status"] == "error", variants
        assert harness.calls == 0


@pytest.mark.asyncio
async def test_batch_runs_variants_in_one_container_call(monkeypatch, tmp_path) -> None:
    events = _ok_events("v-1", "v-2")
    harness = _Harness(monkeypatch, events)
    store = GoldenStageEventStore(max_events=16, max_runs=4, ttl_seconds=60)
    variants = [
        {"request_id": "v-1", "controls": {"seed": 1}},
        {"request_id": "v-2", "controls": {"seed": 2}},
    ]
    result = await studio_golden_run.run_golden_workflow_batch(
        **_call_kwargs(tmp_path, variants, event_store=store, handle_factory=harness.factory)
    )
    assert result["status"] == "ok"
    # Exactly one Modal invocation for the whole batch.
    assert harness.calls == 1
    payload = harness.captured["payload"]
    assert payload["request_id"] == "batch-1"
    assert len(payload["variants"]) == 2
    # Same prep seam per variant: each prompt carries its own controls.
    assert payload["variants"][0]["prompt"] == {"echo": {"seed": 1}}
    assert payload["variants"][1]["prompt"] == {"echo": {"seed": 2}}
    assert payload["variants"][0]["request_id"] == "v-1"
    # Ordered results shaped like single-run responses.
    assert [entry["request_id"] for entry in result["results"]] == ["v-1", "v-2"]
    assert all(entry["status"] == "ok" for entry in result["results"])
    assert result["results"][0]["runId"] == "v-1"
    assert result["results"][0]["historyGenerationId"] == "v-1-gen"
    assert result["results"][0]["output_paths"] == ["img_v-1.png"]
    # History opened and completed per variant.
    assert harness.begun == ["v-1", "v-2"]
    assert harness.completed == ["v-1-run", "v-2-run"]
    assert harness.failed == []
    assert store.read("batch-1")["terminal"] is True


@pytest.mark.asyncio
async def test_batch_variant_prep_failure_is_an_entry(monkeypatch, tmp_path) -> None:
    events = _ok_events("v-2")
    harness = _Harness(monkeypatch, events)
    store = GoldenStageEventStore(max_events=16, max_runs=4, ttl_seconds=60)
    variants = [
        {"request_id": "v-1", "controls": {"bad": True}},
        {"request_id": "v-2", "controls": {"seed": 2}},
    ]
    result = await studio_golden_run.run_golden_workflow_batch(
        **_call_kwargs(tmp_path, variants, event_store=store, handle_factory=harness.factory)
    )
    assert result["status"] == "ok"
    assert [entry["request_id"] for entry in result["results"]] == ["v-1", "v-2"]
    assert result["results"][0]["status"] == "error"
    assert "seed" in result["results"][0]["message"]
    assert result["results"][1]["status"] == "ok"
    # No history opened for the prep-failed variant; one Modal call anyway.
    assert harness.begun == ["v-2"]
    assert harness.calls == 1
    assert len(harness.captured["payload"]["variants"]) == 1


@pytest.mark.asyncio
async def test_batch_transport_failure_fails_begun_histories(monkeypatch, tmp_path) -> None:
    harness = _Harness(monkeypatch, [])

    def exploding_factory(*_args):
        raise RuntimeError("modal down")

    store = GoldenStageEventStore(max_events=8, max_runs=4, ttl_seconds=60)
    variants = [{"request_id": "v-1", "controls": {"seed": 1}}]
    result = await studio_golden_run.run_golden_workflow_batch(
        **_call_kwargs(tmp_path, variants, event_store=store, handle_factory=exploding_factory)
    )
    assert result["status"] == "error"
    assert "modal down" in result["message"]
    # Lazy history: the factory exploded before any variant started, so no
    # half-open records exist to fail.
    assert harness.begun == []
    assert harness.failed == []


@pytest.mark.asyncio
async def test_batch_missing_variant_result_is_an_error_entry(monkeypatch, tmp_path) -> None:
    events = [
        {"type": "variant_start", "variant_request_id": "v-1"},
        {"type": "variant_result", "variant_request_id": "v-1", "data": {"images": []}},
        {"type": "variant_start", "variant_request_id": "v-2"},
        {"type": "batch_result", "results": []},
    ]
    harness = _Harness(monkeypatch, events)
    store = GoldenStageEventStore(max_events=16, max_runs=4, ttl_seconds=60)
    variants = [
        {"request_id": "v-1", "controls": {"seed": 1}},
        {"request_id": "v-2", "controls": {"seed": 2}},
    ]
    result = await studio_golden_run.run_golden_workflow_batch(
        **_call_kwargs(tmp_path, variants, event_store=store, handle_factory=harness.factory)
    )
    assert result["status"] == "ok"
    assert result["results"][0]["status"] == "ok"
    assert result["results"][1]["status"] == "error"
    assert "missing from batch result" in result["results"][1]["message"]
    assert harness.failed == ["v-2-run"]


@pytest.mark.asyncio
async def test_batch_stream_yields_entries_incrementally_in_order(monkeypatch, tmp_path) -> None:
    events = _ok_events("v-1", "v-2")
    harness = _Harness(monkeypatch, events)
    store = GoldenStageEventStore(max_events=16, max_runs=4, ttl_seconds=60)
    variants = [
        {"request_id": "v-0", "controls": {"bad": True}},
        {"request_id": "v-1", "controls": {"seed": 1}},
        {"request_id": "v-2", "controls": {"seed": 2}},
    ]
    seen = []
    async for event in studio_golden_run.run_golden_workflow_batch_stream(
        **_call_kwargs(tmp_path, variants, event_store=store, handle_factory=harness.factory)
    ):
        seen.append(event)
    # Prep failure first, then batch_start, then start+result per variant as
    # each completes, then the batch summary last.
    assert seen[0]["request_id"] == "v-0" and seen[0]["status"] == "error"
    assert seen[1] == {"type": "batch_start", "request_id": "batch-1", "variant_count": 2}
    entries = [event for event in seen if "runId" in event and event.get("request_id") != "v-0"]
    assert [entry["request_id"] for entry in entries] == ["v-1", "v-2"]
    assert all(entry["status"] == "ok" for entry in entries)
    assert seen[-1]["type"] == "batch_result"
    assert [item["request_id"] for item in seen[-1]["results"]] == ["v-1", "v-2"]
    # Histories completed per variant as its entry was yielded.
    assert harness.completed == ["v-1-run", "v-2-run"]


@pytest.mark.asyncio
async def test_batch_skipped_variant_leaves_no_history(monkeypatch, tmp_path) -> None:
    events = [
        {"type": "variant_start", "variant_request_id": "v-1"},
        {"type": "variant_result", "variant_request_id": "v-1", "data": {"images": []}},
        {"type": "variant_skipped", "variant_request_id": "v-2"},
        {"type": "batch_result", "results": []},
    ]
    harness = _Harness(monkeypatch, events)
    store = GoldenStageEventStore(max_events=16, max_runs=4, ttl_seconds=60)
    variants = [
        {"request_id": "v-1", "controls": {"seed": 1}},
        {"request_id": "v-2", "controls": {"seed": 2}},
    ]
    seen = []
    async for event in studio_golden_run.run_golden_workflow_batch_stream(
        **_call_kwargs(tmp_path, variants, event_store=store, handle_factory=harness.factory)
    ):
        seen.append(event)
    kinds = [(event.get("type", "entry"), event.get("request_id")) for event in seen]
    assert ("variant_skipped", "v-2") in [(event.get("type"), event.get("variant_request_id")) for event in seen]
    # Skipped variant: passed through, never begun, never completed.
    assert harness.begun == ["v-1"]
    assert harness.completed == ["v-1-run"]
    assert harness.failed == []


@pytest.mark.asyncio
async def test_batch_cancelled_finalizes_without_missing_errors(monkeypatch, tmp_path) -> None:
    events = [
        {"type": "variant_start", "variant_request_id": "v-1"},
        {"type": "variant_result", "variant_request_id": "v-1", "data": {"images": []}},
        {"type": "batch_cancelled", "request_id": "batch-1", "results": []},
    ]
    harness = _Harness(monkeypatch, events)
    store = GoldenStageEventStore(max_events=16, max_runs=4, ttl_seconds=60)
    variants = [
        {"request_id": "v-1", "controls": {"seed": 1}},
        {"request_id": "v-2", "controls": {"seed": 2}},
    ]
    seen = []
    async for event in studio_golden_run.run_golden_workflow_batch_stream(
        **_call_kwargs(tmp_path, variants, event_store=store, handle_factory=harness.factory)
    ):
        seen.append(event)
    assert "batch_cancelled" in [event.get("type") for event in seen]
    # v-2 never started: skipped (requeueable), never begun, no error entry.
    assert seen[-1]["type"] == "variant_skipped"
    assert seen[-1]["variant_request_id"] == "v-2"
    assert harness.begun == ["v-1"]
    assert all(event.get("request_id") != "v-2" or event.get("type") == "variant_skipped" for event in seen)


@pytest.mark.asyncio
async def test_batch_non_fast_path_variant_is_flagged(monkeypatch, tmp_path) -> None:
    events = _ok_events("v-1")
    harness = _Harness(monkeypatch, events)
    store = GoldenStageEventStore(max_events=16, max_runs=4, ttl_seconds=60)
    variants = [
        {"request_id": "v-1", "controls": {"seed": 1}},
        {"request_id": "v-2", "controls": {"slow": True}},
    ]
    result = await studio_golden_run.run_golden_workflow_batch(
        **_call_kwargs(tmp_path, variants, event_store=store, handle_factory=harness.factory)
    )
    assert result["status"] == "ok"
    assert result["results"][0]["status"] == "ok"
    assert result["results"][1]["status"] == "error"
    assert result["results"][1]["error_code"] == "BATCH_FAST_PATH_REQUIRED"
    assert harness.begun == ["v-1"]
