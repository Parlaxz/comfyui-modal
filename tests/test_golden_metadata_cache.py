"""Single-file restore cache for parsed safetensors metadata.

Covers the correctness contract (equivalence with the original parser, identity,
fallback, dynamic models) and measures the restore hydration budget, which the
optimization is only allowed to claim if every accepted restore stays under
75 ms end to end.
"""

from __future__ import annotations

import json
import os
import struct
import time

import pytest

from comfymodal_runtime import golden_metadata_cache as gmc
from comfymodal_runtime import golden_model_transport as transport

pytestmark = pytest.mark.fast_unit

DTYPES = ["F32", "F16", "BF16", "I64"]


def _write_safetensors(path: str, tensor_count: int, *, name_prefix: str = "model") -> None:
    """Write a minimal but structurally valid safetensors file."""
    header: dict[str, object] = {}
    offset = 0
    for index in range(tensor_count):
        name = f"{name_prefix}.blocks.{index}.weight"
        shape = [64, 64] if index % 3 else [128, 32]
        length = shape[0] * shape[1] * 2
        header[name] = {
            "dtype": DTYPES[index % len(DTYPES)],
            "shape": shape,
            "data_offsets": [offset, offset + length],
        }
        offset += length
    header["__metadata__"] = {"format": "pt"}
    raw = json.dumps(header).encode("utf-8")
    with open(path, "wb") as handle:
        handle.write(struct.pack("<Q", len(raw)))
        handle.write(raw)
        handle.write(b"\0" * offset)


@pytest.fixture()
def model_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(gmc.ENV_CACHE_ROOT, str(tmp_path / "state"))
    gmc.reset_for_tests()
    yield tmp_path
    gmc.reset_for_tests()


def _cache_file() -> str:
    return gmc.cache_path()


def _publish(model_dir, names=("clip", "unet", "vae"), tensors=600):
    """Parse and publish like a real request would, then return the layouts."""
    layouts = {}
    for name in names:
        path = str(model_dir / f"{name}.safetensors")
        _write_safetensors(path, tensors, name_prefix=name)
        layouts[path] = transport._parse_layout(path, transport._file_identity(path))
        gmc.cache().put(layouts[path])
    assert gmc.cache().publish()
    return layouts


# ── equivalence with the original parser ──────────────────────────────────


def test_cached_layout_is_exactly_equal_to_the_original_parse(model_dir):
    layouts = _publish(model_dir)
    gmc.reset_for_tests()
    assert gmc.cache().hydrate()["total_ms"] >= 0.0

    for path, original in layouts.items():
        identity = transport._file_identity(path)
        cached = gmc.cache().get(path, identity)
        assert cached is not None, path
        assert cached.path == original.path
        assert tuple(cached.identity) == tuple(original.identity)
        assert cached.data_start == original.data_start
        assert cached.data_bytes == original.data_bytes
        assert len(cached.tensor_map) == len(original.tensor_map)
        for got, want in zip(cached.tensor_map, original.tensor_map):
            assert got["key"] == want["key"]
            assert got["dtype"] == want["dtype"]
            assert list(got["shape"]) == list(want["shape"])
            assert got["offset"] == want["offset"]
            assert got["length"] == want["length"]
        # The header dict is rebuilt from the normalized rows, so it must agree.
        assert set(cached.header) == set(original.header)
        assert cached.header["__metadata__"] == original.header["__metadata__"]
        for key, info in original.header.items():
            if key == "__metadata__":
                continue
            assert cached.header[key]["dtype"] == info["dtype"]
            assert list(cached.header[key]["shape"]) == list(info["shape"])
            assert cached.header[key]["data_offsets"] == info["data_offsets"]


def test_one_normalized_representation_is_stored(model_dir):
    """The persisted rows must not duplicate the raw header dict."""
    _publish(model_dir, names=("clip",), tensors=50)
    gmc.reset_for_tests()
    gmc.cache().hydrate()
    record = next(iter(gmc.cache().records.values()))

    assert set(record) == {"path", "identity", "data_start", "data_bytes", "meta", "rows"}
    assert isinstance(record["rows"], tuple)
    row = record["rows"][0]
    assert isinstance(row, tuple) and len(row) == 5


# ── identity ──────────────────────────────────────────────────────────────


def test_unknown_model_is_a_clean_miss(model_dir):
    path = str(model_dir / "new.safetensors")
    _write_safetensors(path, 40)
    identity = transport._file_identity(path)
    assert gmc.cache().get(path, identity) is None
    # The caller then runs the original parser and uses the result normally.
    layout = transport._parse_layout(path, identity)
    gmc.cache().put(layout)
    assert gmc.cache().get(path, identity) is not None


def test_same_path_changed_content_cannot_reuse_stale_metadata(model_dir):
    """Rewriting the file under the same name must invalidate the entry."""
    path = str(model_dir / "clip.safetensors")
    _write_safetensors(path, 100, name_prefix="clip")
    stale_identity = transport._file_identity(path)
    gmc.cache().put(transport._parse_layout(path, stale_identity))
    assert gmc.cache().get(path, stale_identity) is not None

    # Different content, same pathname. Size and mtime both change.
    time.sleep(0.01)
    _write_safetensors(path, 250, name_prefix="clip_rewritten")
    fresh_identity = transport._file_identity(path)
    assert fresh_identity != stale_identity
    assert gmc.cache().get(path, fresh_identity) is None


def test_identity_mismatch_on_any_component_is_a_miss(model_dir):
    path = str(model_dir / "unet.safetensors")
    _write_safetensors(path, 60)
    identity = transport._file_identity(path)
    gmc.cache().put(transport._parse_layout(path, identity))

    for index in range(4):
        perturbed = list(identity)
        perturbed[index] += 1
        assert gmc.cache().get(path, tuple(perturbed)) is None


def test_hit_performs_no_payload_read(model_dir, monkeypatch):
    """A cache hit must cost a stat, not a Volume data read."""
    _publish(model_dir, names=("clip",), tensors=60)
    gmc.reset_for_tests()
    gmc.cache().hydrate()
    path = next(iter(gmc.cache().records))
    identity = transport._file_identity(path)

    opened = []
    real_open = open

    def tracking_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", tracking_open)
    assert gmc.cache().get(path, identity) is not None
    monkeypatch.undo()

    assert opened == []


# ── failure policy ───────────────────────────────────────────────────────


def test_missing_cache_file_is_not_an_error(model_dir):
    result = gmc.cache().hydrate()
    assert result["total_ms"] >= 0.0
    assert gmc.cache().records == {}
    assert gmc.cache().get(str(model_dir / "x"), (1, 2, 3, 4)) is None


def test_corrupt_cache_file_is_not_an_error(model_dir):
    _publish(model_dir, names=("clip",), tensors=30)
    gmc.reset_for_tests()
    os.makedirs(os.path.dirname(_cache_file()), exist_ok=True)
    with open(_cache_file(), "wb") as handle:
        handle.write(b"not a pickle at all")

    result = gmc.cache().hydrate()
    assert result["total_ms"] >= 0.0
    assert gmc.cache().records == {}
    assert gmc.cache().loaded_from_disk is False


def test_foreign_schema_version_is_rejected(model_dir):
    import pickle

    os.makedirs(os.path.dirname(_cache_file()), exist_ok=True)
    with open(_cache_file(), "wb") as handle:
        pickle.dump({"schema": gmc.CACHE_SCHEMA_VERSION + 99, "records": {"x": {}}}, handle)

    gmc.cache().hydrate()
    assert gmc.cache().records == {}


def test_publish_failure_is_counted_not_raised(model_dir):
    # A regular file where a directory is needed: makedirs must fail.
    blocker = model_dir / "not_a_dir"
    blocker.write_text("x")
    gmc.cache().publish_failures = 0
    assert gmc.cache().publish(path=str(blocker / "sub" / "z.bin")) is False
    assert gmc.cache().publish_failures == 1


# ── storage shape and size ────────────────────────────────────────────────


def test_single_cache_file_not_a_forest(model_dir):
    _publish(model_dir)
    produced = sorted(os.listdir(gmc.cache_dir()))
    assert produced == [gmc.CACHE_BASENAME]


def test_cache_file_size_and_per_model_statistics(model_dir):
    _publish(model_dir, tensors=600)
    size = os.path.getsize(_cache_file())
    gmc.reset_for_tests()
    gmc.cache().hydrate()
    stats = gmc.cache().telemetry()
    assert stats["models"] == 3
    # One file holding three models stays small; this is metadata, not weights.
    assert size < 2_000_000, size
    assert stats["loaded_from_disk"] is True


# ── hydration budget ──────────────────────────────────────────────────────


@pytest.mark.parametrize("tensors", [600])
def test_restore_hydration_is_under_75ms_on_every_observation(model_dir, tensors):
    """Minimum five independent restores; every one must clear 75 ms."""
    _publish(model_dir, tensors=tensors)
    size = os.path.getsize(_cache_file())

    observations = []
    for _ in range(7):
        fresh = gmc.reset_for_tests()
        started = time.perf_counter()
        fresh.hydrate()
        observations.append((time.perf_counter() - started) * 1000.0)
        assert len(fresh.records) == 3

    ordered = sorted(observations)
    report = {
        "cache_file_bytes": size,
        "min_ms": round(ordered[0], 3),
        "p50_ms": round(ordered[len(ordered) // 2], 3),
        "max_ms": round(ordered[-1], 3),
        "mean_ms": round(sum(ordered) / len(ordered), 3),
        "observations": [round(value, 3) for value in observations],
    }
    print("\nRESTORE HYDRATION:", report)
    assert len(observations) >= 5
    assert report["max_ms"] < 75.0, report
    assert report["p50_ms"] < 75.0, report


def test_hydration_reports_its_own_breakdown(model_dir):
    _publish(model_dir)
    gmc.reset_for_tests()
    breakdown = gmc.cache().hydrate()
    assert "open_read_ms" in breakdown
    assert "deserialize_ms" in breakdown
    assert "total_ms" in breakdown
    assert breakdown["models"] == 3.0
    telemetry = gmc.cache().telemetry()
    assert telemetry["hydration_breakdown_ms"]["total_ms"] >= 0.0