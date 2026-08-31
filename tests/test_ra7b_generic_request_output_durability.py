"""Focused tests for generic request-output durability policy branching."""

from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace

from comfymodal_runtime import modal_app
from comfymodal_runtime.output_delivery import (
    Attempt,
    OutputItem,
    attempt_to_descriptor_result,
)
from comfymodal_runtime.output_durability import resolve_output_durability


def _attempt() -> Attempt:
    return Attempt(
        strategy="registry",
        success=True,
        items=(OutputItem(
            node_id="save",
            output_key="images",
            filename="result.png",
            raw_bytes=b"inline result bytes",
            mime_type="image/png",
            file_ext=".png",
        ),),
        total_items=1,
        total_raw_bytes=len(b"inline result bytes"),
    )


def test_generic_off_skips_all_persistence_and_returns_inline_bytes(monkeypatch):
    entrypoint = object.__new__(modal_app.ModalRuntimeEntrypoint)
    attempt = _attempt()
    calls: list[str] = []

    async def forbidden_persistence(attempt):
        calls.append("persist")
        raise AssertionError("off mode must not invoke generated-output persistence")

    setattr(entrypoint, "_persist_output_assets", forbidden_persistence)

    def forbidden_fs(*_args, **_kwargs):
        calls.append("filesystem")
        raise AssertionError("off mode must not touch generated-output filesystem")

    monkeypatch.setattr(modal_app.Path, "mkdir", forbidden_fs)
    monkeypatch.setattr(modal_app.Path, "write_bytes", forbidden_fs)
    monkeypatch.setattr(modal_app.os, "replace", forbidden_fs)
    monkeypatch.setattr(modal_app.os, "fsync", forbidden_fs)

    class Volume:
        def commit(self):
            calls.append("commit")
            raise AssertionError("off mode must not commit the output Volume")

    monkeypatch.setattr(modal_app, "_MODAL_RESOURCES", {
        "runtime_state_volume": Volume(),
    }, raising=False)

    persisted, commit_task, diag = asyncio.run(
        entrypoint._persist_output_assets_for_policy(
            attempt, resolve_output_durability({}),
        )
    )
    result = attempt_to_descriptor_result(persisted, legacy_data=True)

    assert calls == []
    assert commit_task is None
    assert diag["persistence_status"] == "NOT RUN"
    assert diag["commit_status"] == "NOT RUN"
    assert base64.b64decode(result["images"][0]["data"]) == b"inline result bytes"
    assert result["include_base64"] is True

    entrypoint._deferred_commit_pending = False
    assert asyncio.run(entrypoint._finalize_deferred_commit()) is None


def test_generic_strict_delegates_to_existing_persistence_task():
    entrypoint = object.__new__(modal_app.ModalRuntimeEntrypoint)
    attempt = _attempt()
    calls: list[str] = []

    async def existing_persistence(attempt):
        calls.append("persist")
        task = asyncio.create_task(asyncio.sleep(0))
        return attempt, task, {"commit_ms": 3.5, "commit_status": "pending"}

    setattr(entrypoint, "_persist_output_assets", existing_persistence)

    async def exercise():
        persisted, commit_task, diag = await entrypoint._persist_output_assets_for_policy(
            attempt,
            SimpleNamespace(mode="strict", durability_requested=True),
        )
        if commit_task is not None:
            await commit_task
        return persisted, commit_task, diag

    persisted, commit_task, diag = asyncio.run(exercise())

    assert persisted is attempt
    assert calls == ["persist"]
    assert commit_task is not None
    assert diag == {"commit_ms": 3.5, "commit_status": "pending"}
