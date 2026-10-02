import asyncio
import base64
import hashlib
from pathlib import Path

import pytest

from comfymodal_runtime.output_durability import (
    ConfigurationError,
    ReadyOutputArtifact,
    resolve_output_durability,
)


def test_output_durability_selector_defaults_to_off_and_accepts_strict():
    assert resolve_output_durability({}).mode == "off"
    assert resolve_output_durability({"COMFYMODAL_OUTPUT_DURABILITY": " off "}).durability_requested is False
    strict = resolve_output_durability({"COMFYMODAL_OUTPUT_DURABILITY": "STRICT"})
    assert strict.mode == "strict"
    assert strict.durability_requested is True


def test_output_durability_selector_rejects_invalid_explicit_value():
    with pytest.raises(ConfigurationError) as excinfo:
        resolve_output_durability({"COMFYMODAL_OUTPUT_DURABILITY": "maybe"})
    assert str(excinfo.value) == (
        "configuration error: COMFYMODAL_OUTPUT_DURABILITY must be off or strict"
    )


def test_ready_output_artifact_validates_observed_identity():
    payload = b"encoded png bytes"
    artifact = ReadyOutputArtifact(
        raw_bytes=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
        filename="asset.png",
    )
    assert artifact.byte_count == len(payload)
    with pytest.raises(RuntimeError, match="output_sha_mismatch"):
        ReadyOutputArtifact(payload, "0" * 64, len(payload), "asset.png")


def test_final_result_fields_default_to_result_ready_off_mode():
    from comfymodal_runtime import golden_serial as gs

    result = gs.GoldenFinalResult(
        request_id="off-default",
        image_sha256="a" * 64,
        asset_path="",
        volume_rel_path="",
        true_durable=False,
        seriality_violation_count=0,
        executed_nodes=[],
    )
    assert result.output_durability_mode == "off"
    assert result.durability_requested is False
    assert result.result_durable is False


def test_off_result_is_ready_not_durable_and_has_inline_bytes(tmp_path):
    from comfymodal_runtime import golden_serial as gs

    payload = b"encoded png bytes"
    digest = hashlib.sha256(payload).hexdigest()
    session = object.__new__(gs.GoldenSession)
    session.durability_requested = False
    session.pending_durability = None
    session.output_artifact = ReadyOutputArtifact(
        payload, digest, len(payload), "asset.png", width=2, height=3
    )
    session.recorder = gs.GoldenTelemetryRecorder()
    session.recorder.output_durability_mode = "off"
    session.recorder.durability_requested = False
    session.recorder.begin_stage("golden_output")
    session.recorder.end_stage("golden_output", ready=True)
    session.recorder.mark_first_result_ready()
    session.request = gs.GoldenRequest(request_id="r1", prompt={})
    session.runner = None

    result = session.build_final_result()
    assert result.true_durable is False
    assert result.result_durable is False
    assert result.output_durability_mode == "off"
    assert base64.b64decode(result.image_data) == payload
    assert result.byte_count == len(payload)
    assert gs.EVENT_FIRST_RESULT_READY in [event["name"] for event in session.recorder.events]
    telemetry = session.recorder.to_json_dict()
    assert telemetry["result_durable"] is False
    assert not any(stage["name"] == "golden_durable_commit" for stage in telemetry["stages"])

    from comfymodal_runtime.result_delivery import materialize_modal_result

    materialized = materialize_modal_result(
        {
            "images": [{
                "filename": result.filename,
                "node_id": result.output_node_id,
                "output_key": "images",
                "mime_type": result.mime_type,
                "byte_count": result.byte_count,
                "asset_id": result.image_sha256,
                "data": result.image_data,
            }],
        },
        output_dir=str(tmp_path),
        prompt_id="r1",
    )
    assert materialized["image_count"] == 1
    assert Path(materialized["written_files"][0]).read_bytes() == payload


def test_durability_apis_reject_off_before_commit_or_marker(tmp_path):
    from comfymodal_runtime import golden_serial as gs

    payload = b"durability test"
    asset = tmp_path / "asset.png"
    asset.write_bytes(payload)
    pending = gs.PendingDurability(
        asset_abs_path=str(asset),
        volume_rel_path="asset.png",
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
        sidecar_path=str(tmp_path / "asset.json"),
        volume_mount_root=str(tmp_path),
    )

    class Volume:
        def __init__(self):
            self.calls = 0

        def commit(self):
            self.calls += 1

    recorder = gs.GoldenTelemetryRecorder()
    with pytest.raises(RuntimeError, match="output_durability_strict"):
        recorder.mark_true_durable()
    assert gs.EVENT_TRUE_FIRST_DURABLE_RESULT not in {
        event["name"] for event in recorder.events
    }

    volume = Volume()
    with pytest.raises(RuntimeError, match="output_durability_strict"):
        asyncio.run(
            gs.golden_durable_commit(
                volume,
                pending,
                recorder,
                expected_sha256=pending.sha256,
            )
        )
    assert volume.calls == 0
    assert pending.committed is False
    assert gs.EVENT_VOLUME_COMMIT_START not in {
        event["name"] for event in recorder.events
    }

    strict_recorder = gs.GoldenTelemetryRecorder()
    strict_recorder.output_durability_mode = "strict"
    strict_recorder.durability_requested = True
    strict_volume = Volume()
    asyncio.run(
        gs.golden_durable_commit(
            strict_volume,
            pending,
            strict_recorder,
            expected_sha256=pending.sha256,
        )
    )
    strict_recorder.mark_true_durable()
    assert strict_volume.calls == 1
    names = [event["name"] for event in strict_recorder.events]
    assert names.index(gs.EVENT_VOLUME_COMMIT_COMPLETE) < names.index(
        gs.EVENT_TRUE_FIRST_DURABLE_RESULT
    )


def test_direct_off_golden_output_stays_in_memory(tmp_path, monkeypatch):
    from comfymodal_runtime import golden_serial as gs
    import torch

    class Switch:
        FUNCTION = "go"

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"any_02": ("*",)}, "optional": {}}

        def go(self, any_02):
            return (any_02,)

    class SaveImage:
        FUNCTION = "save_images"

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"images": ("IMAGE",)}, "optional": {}}

        def save_images(self, images):
            raise AssertionError("SaveImage must not execute")

    prompt = {
        "decode": {"class_type": "VAEDecode", "inputs": {}},
        "switch": {
            "class_type": "Any Switch (rgthree)",
            "inputs": {"any_02": ["decode", 0]},
        },
        "save": {
            "class_type": "SaveImage",
            "inputs": {"images": ["switch", 0]},
        },
    }
    node_map = gs.GoldenNodeMap("clip", "encode", "unet", "vae", "sampler", "decode")
    runner = gs.GoldenSerialRunner(
        prompt,
        node_classes={"Any Switch (rgthree)": Switch, "SaveImage": SaveImage},
    )
    runner.seed("decode", [[torch.rand(1, 4, 4, 3)]])
    session = object.__new__(gs.GoldenSession)
    session.durability_requested = False
    session.pending_durability = None
    session.output_artifact = None
    session.recorder = gs.GoldenTelemetryRecorder()
    session.recorder.output_durability_mode = "off"
    session.recorder.durability_requested = False
    session.request = gs.GoldenRequest(request_id="off-output", prompt=prompt)
    session.contract = gs.GoldenWorkflowContract(expected_output_png_sha256="")
    session.runner = runner
    session.node_map = node_map
    session.output_root = str(tmp_path / "output_assets")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("off output must not write or fsync")

    monkeypatch.setattr(gs.os, "fsync", forbidden)
    monkeypatch.setattr(gs.os, "replace", forbidden)
    monkeypatch.setattr(gs.tempfile, "mkstemp", forbidden)

    artifact = asyncio.run(gs.golden_output(session))
    assert isinstance(artifact, gs.ReadyOutputArtifact)
    assert session.pending_durability is None
    assert not (tmp_path / "output_assets").exists()
    assert gs.EVENT_FIRST_RESULT_READY in {
        event["name"] for event in session.recorder.events
    }
