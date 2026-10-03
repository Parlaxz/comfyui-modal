from __future__ import annotations

import importlib
import json
import hashlib
import os
import struct
import time
from types import SimpleNamespace

import pytest

from comfymodal_runtime import golden_model_metadata_cache as cache
from comfymodal_runtime.golden_model_transport import GoldenModelTransport


pytestmark = pytest.mark.fast_unit


def _write_model(path, seed: int = 0) -> None:
    payload = bytes(((seed + value) % 256 for value in range(16)))
    header = {
        "__metadata__": {"ignored": "by design"},
        f"tensor.{seed}": {
            "dtype": "U8", "shape": [16], "data_offsets": [0, 16],
        },
    }
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(encoded)) + encoded + payload)


def test_round_trip_preserves_one_normalized_blueprint(tmp_path):
    model = tmp_path / "checkpoints" / "clip.safetensors"
    model.parent.mkdir()
    _write_model(model, 1)
    entry = cache.build_entry(model, "checkpoints/clip.safetensors")
    blob = cache._serialize({entry["path"]: entry})
    decoded = cache.deserialize(blob)

    assert decoded[entry["path"]]["tensors"] == [["tensor.1", "U8", [16], 0, 16]]
    assert decoded[entry["path"]]["header_sha256"] == entry["header_sha256"]
    assert "__metadata__" not in str(decoded[entry["path"]]["tensors"])


def test_identity_mismatch_and_changed_header_are_misses(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setenv("COMFYMODAL_MODELS_PATH", str(models))
    model = models / "checkpoints" / "clip.safetensors"
    model.parent.mkdir()
    _write_model(model, 2)
    cache_path = tmp_path / "metadata.bin"
    assert cache.publish_model_metadata(model, "checkpoints/clip.safetensors", cache_path=str(cache_path))["status"] == "ok"
    cache.hydrate(str(cache_path), force=True)
    assert cache.lookup(model, str(cache_path))["entry"] is not None

    _write_model(model, 3)
    cache.hydrate(str(cache_path), force=True)
    result = cache.lookup(model, str(cache_path))
    assert result["entry"] is None
    assert result["entry_hit"] is True
    assert result["identity_match"] is False


@pytest.mark.parametrize("mutator", [
    lambda raw: raw[:3],
    lambda raw: b"wrong-schema" + raw[12:],
    lambda raw: raw[:-7],
])
def test_corrupt_wrong_schema_and_truncated_blob_fail_soft(tmp_path, mutator):
    model = tmp_path / "clip.safetensors"
    _write_model(model)
    cache_path = tmp_path / "metadata.bin"
    entry = cache.build_entry(model, "checkpoints/clip.safetensors")
    cache_path.write_bytes(mutator(cache._serialize({entry["path"]: entry})))

    cache.hydrate(str(cache_path), force=True)
    state = cache.hydrate(str(cache_path))
    result = cache.lookup(model)
    assert result["entry"] is None
    assert state["loaded"] is False
    assert state["schema"] in {"corrupt", "absent"}


def test_unknown_model_is_a_safe_miss(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setenv("COMFYMODAL_MODELS_PATH", str(models))
    known = models / "checkpoints" / "known.safetensors"
    unknown = models / "checkpoints" / "unknown.safetensors"
    known.parent.mkdir()
    _write_model(known)
    _write_model(unknown, 4)
    cache_path = tmp_path / "metadata.bin"
    entry = cache.build_entry(known, "checkpoints/known.safetensors")
    cache_path.write_bytes(cache._serialize({entry["path"]: entry}))
    cache.hydrate(str(cache_path), force=True)

    result = cache.lookup(unknown, str(cache_path))
    assert result["entry"] is None
    assert result["reason"] == "unknown_model"


def test_three_model_hydration_is_bounded_and_compact(tmp_path):
    entries = {}
    tensor_count = 2000
    for index in range(3):
        path = f"checkpoints/model-{index}.safetensors"
        entries[path] = {
            "path": path,
            "size": 100000 + index,
            "mtime_ns": index + 1,
            "header_sha256": hashlib.sha256(f"header-{index}".encode()).hexdigest(),
            "data_start": 100,
            "data_bytes": tensor_count * 16,
            "tensors": [
                [
                    f"tensor.{index}.{tensor:04d}.{hashlib.sha256(f'{index}-{tensor}'.encode()).hexdigest()[:12]}",
                    "U8", [16], tensor * 16, 16,
                ]
                for tensor in range(tensor_count)
            ],
        }
    blob = cache._serialize(entries)
    cache_path = tmp_path / "metadata.bin"
    cache_path.write_bytes(blob)

    started = time.perf_counter_ns()
    state = cache.hydrate(str(cache_path), force=True)
    elapsed_ms = (time.perf_counter_ns() - started) / 1e6

    assert len(state["entries"]) == 3
    assert len(blob) < 100 * 1024
    assert elapsed_ms < 75.0
    assert state["hydration_ms"] < 75.0


def test_transport_uses_persistent_layout_blueprint_for_clip(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setenv("COMFYMODAL_MODELS_PATH", str(models))
    model = models / "checkpoints" / "clip.safetensors"
    model.parent.mkdir()
    _write_model(model, 8)
    cache_path = tmp_path / "metadata.bin"
    entry = cache.build_entry(model, "checkpoints/clip.safetensors")
    cache_path.write_bytes(cache._serialize({entry["path"]: entry}))
    original_lookup = cache.lookup
    monkeypatch.setattr(cache, "lookup", lambda path: original_lookup(path, str(cache_path)))

    layout = GoldenModelTransport().inspect(str(model), role="clip")

    assert layout.cache_source == "persistent"
    assert layout.metadata_cache_entry_hit is True
    assert layout.metadata_cache_identity_match is True
    assert layout.header == {}
    assert layout.tensor_map[0]["key"] == "tensor.8"


def test_corrupt_cache_falls_back_to_canonical_transport_parse(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setenv("COMFYMODAL_MODELS_PATH", str(models))
    model = models / "checkpoints" / "clip.safetensors"
    model.parent.mkdir()
    _write_model(model, 9)
    cache_path = tmp_path / "metadata.bin"
    cache_path.write_bytes(b"truncated")
    original_lookup = cache.lookup
    monkeypatch.setattr(cache, "lookup", lambda path: original_lookup(path, str(cache_path)))

    layout = GoldenModelTransport().inspect(str(model), role="clip")

    assert layout.cache_source == "runtime_parse"
    assert layout.tensor_map[0]["key"] == "tensor.9"


def _patch_precohort_runtime(monkeypatch, tmp_path, *, volume):
    from comfymodal_runtime import modal_app

    models = tmp_path / "models"
    cache_path = tmp_path / "metadata.bin"
    monkeypatch.setattr(modal_app, "MODELS_PATH", str(models))
    monkeypatch.setattr(cache, "CACHE_PATH", str(cache_path))
    cache.reset_for_tests()
    fake_serial = SimpleNamespace(
        CANONICAL_CLIP_NAME="qwen_3_4b.safetensors",
        CANONICAL_CLIP_SPEC=SimpleNamespace(folder="text_encoders"),
        CANONICAL_UNET_NAME="z_image_turbo_bf16.safetensors",
        CANONICAL_UNET_FOLDER="diffusion_models",
        CANONICAL_VAE_NAME="ae.safetensors",
        CANONICAL_VAE_FOLDER="vae",
    )
    real_import = modal_app.importlib.import_module

    def fake_import(name):
        if name == "comfyapp":
            return SimpleNamespace(runtime_config_vol=volume)
        if name == "comfymodal_runtime.golden_serial":
            return fake_serial
        if name == "comfymodal_runtime.golden_model_metadata_cache":
            return cache
        return real_import(name)

    monkeypatch.setattr(modal_app.importlib, "import_module", fake_import)
    return modal_app.ModalRuntimeEntrypoint(), models, cache_path


def test_precohort_publishes_present_models_and_skips_missing(tmp_path, monkeypatch):
    class Volume:
        commits = 0

        def commit(self):
            self.commits += 1

    runtime, models, cache_path = _patch_precohort_runtime(
        monkeypatch, tmp_path, volume=Volume()
    )
    for folder, filename in (
        ("text_encoders", "qwen_3_4b.safetensors"),
        ("diffusion_models", "z_image_turbo_bf16.safetensors"),
    ):
        path = models / folder / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_model(path)

    result = runtime.publish_model_metadata_cache(request_id="cohort")

    assert result["status"] == "ok"
    assert result["file_bytes"] == cache_path.stat().st_size
    assert result["file_bytes"] > 0
    assert result["models"]["clip"]["status"] == "ok"
    assert result["models"]["unet"]["status"] == "ok"
    assert result["models"]["vae"]["status"] == "skipped"
    state = cache.hydrate(str(cache_path), force=True)
    assert set(state["entries"]) == {
        "text_encoders/qwen_3_4b.safetensors",
        "diffusion_models/z_image_turbo_bf16.safetensors",
    }


def test_precohort_is_idempotent_and_absent_volume_is_visible(tmp_path, monkeypatch):
    class Volume:
        commits = 0

        def commit(self):
            self.commits += 1

    volume = Volume()
    runtime, models, cache_path = _patch_precohort_runtime(
        monkeypatch, tmp_path, volume=volume
    )
    for folder, filename in (
        ("text_encoders", "qwen_3_4b.safetensors"),
        ("diffusion_models", "z_image_turbo_bf16.safetensors"),
        ("vae", "ae.safetensors"),
    ):
        path = models / folder / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_model(path)

    first = runtime.publish_model_metadata_cache()
    first_blob = cache_path.read_bytes()
    second = runtime.publish_model_metadata_cache()

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert all(item["status"] == "noop" for item in second["models"].values())
    assert cache_path.read_bytes() == first_blob
    assert volume.commits == 3

    runtime_no_volume, no_volume_models, _ = _patch_precohort_runtime(
        monkeypatch, tmp_path / "no-volume", volume=None
    )
    missing_volume_model = no_volume_models / "text_encoders" / "qwen_3_4b.safetensors"
    missing_volume_model.parent.mkdir(parents=True, exist_ok=True)
    _write_model(missing_volume_model)
    degraded = runtime_no_volume.publish_model_metadata_cache()
    assert degraded["status"] == "partial"
    assert degraded["runtime_config_volume"] == "absent"


def test_a_miss_is_not_memoized_so_a_late_blob_is_still_seen(tmp_path, monkeypatch):
    """A hydrate() miss must stay re-checkable.

    The blob is published by a different container.  If an early probe that
    runs before the runtime-config Volume is reloaded pinned the cached state
    to 'absent', every later lookup in that container would report a miss even
    though the blob had since become visible.
    """
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setenv("COMFYMODAL_MODELS_PATH", str(models))
    cache_path = tmp_path / "state" / "golden_model_metadata.bin"
    cache_path.parent.mkdir()
    model = models / "checkpoints" / "clip.safetensors"
    model.parent.mkdir(parents=True)
    _write_model(model, 7)
    entry = cache.build_entry(model, "checkpoints/clip.safetensors")
    cache.reset_for_tests()

    # First probe: nothing published yet.
    early = cache.hydrate(str(cache_path))
    assert early["loaded"] is False
    assert early["schema"] == "absent"

# Another container publishes and commits the blob.  Nothing resets this
    # process's state - that reset lives in the publisher's process, not here.
    cache_path.write_bytes(cache._serialize({entry["path"]: entry}))

    later = cache.hydrate(str(cache_path))
    assert later["loaded"] is True
    assert later["schema"] == cache.SCHEMA_VERSION
    assert entry["path"] in later["entries"]

    hit = cache.lookup(model, str(cache_path))
    assert hit["entry_hit"] is True
    assert hit["identity_match"] is True
    assert hit["reason"] == "hit"
    cache.reset_for_tests()


def test_cache_path_lives_inside_the_v2_runtime_state_mount():
    """The blob must sit on the mount the V2 runtime actually provides.

    ModalRuntimeEntrypointV2 mounts the runtime-state Volume at
    RUNTIME_STATE_PATH (/mnt/comfymodal_runtime_state).  The legacy ComfyAPI
    class mounts the same Volume at /root/comfymodal_runtime_state, so a blob
    written under the legacy path from a V2 container is just a container-local
    file: it is never committed to the Volume and disappears with the container.
    """
    from comfymodal_runtime import modal_app

    assert cache.CACHE_PATH.startswith(modal_app.RUNTIME_STATE_PATH + "/")
    assert not cache.CACHE_PATH.startswith("/root/comfymodal_runtime_state/")
    assert cache.CACHE_PATH.endswith("caching_data/golden_model_metadata.bin")


def test_cache_path_follows_the_configured_runtime_state_root(monkeypatch):
    monkeypatch.setenv("COMFYMODAL_V2_STATE_VOLUME_ROOT", "/mnt/somewhere-else")
    reloaded = importlib.reload(cache)
    try:
        assert reloaded.CACHE_PATH == "/mnt/somewhere-else/caching_data/golden_model_metadata.bin"
    finally:
        monkeypatch.delenv("COMFYMODAL_V2_STATE_VOLUME_ROOT", raising=False)
        importlib.reload(cache)



def test_lookup_hits_on_stat_identity_without_rereading_the_header(tmp_path, monkeypatch):
    """A lookup must not re-read the SafeTensors header on the fast path.

    Reading the header back off the Volume cost about as much as the parse the
    cache exists to avoid (~39 ms versus ~31 ms), which made the treatment a net
    loss.  size+mtime_ns already change on any modification, so a matching stat
    is sufficient to serve the blueprint.
    """
    models = tmp_path / "models"
    models.mkdir()
    monkeypatch.setenv("COMFYMODAL_MODELS_PATH", str(models))
    model = models / "checkpoints" / "clip.safetensors"
    model.parent.mkdir(parents=True)
    _write_model(model, 11)
    cache_path = tmp_path / "state" / "golden_model_metadata.bin"
    cache_path.parent.mkdir()
    entry = cache.build_entry(model, "checkpoints/clip.safetensors")
    cache_path.write_bytes(cache._serialize({entry["path"]: entry}))
    cache.reset_for_tests()

    def _boom(*_args, **_kwargs):
        raise AssertionError("header must not be re-read when stat matches")

    monkeypatch.setattr(cache, "_header_bytes", _boom)
    cache.reset_for_tests()
    assert cache.hydrate(str(cache_path))["loaded"] is True
    hit = cache.lookup(model, str(cache_path))
    assert hit["entry_hit"] is True
    assert hit["identity_match"] is True
    assert hit["reason"] == "hit"

# A real content change must still be rejected.  Undo only the header-read
    # guard; COMFYMODAL_MODELS_PATH must stay set for canonical path resolution.
    monkeypatch.undo()
    monkeypatch.setenv("COMFYMODAL_MODELS_PATH", str(models))
    _write_model(model, 12)
    cache.reset_for_tests()
    entry2 = cache.build_entry(model, "checkpoints/clip.safetensors")
    assert entry2["header_sha256"] != entry["header_sha256"]
    miss = cache.lookup(model, str(cache_path))
    assert miss["entry_hit"] is True
    assert miss["identity_match"] is False
    assert miss["reason"] == "identity_mismatch"
    cache.reset_for_tests()
