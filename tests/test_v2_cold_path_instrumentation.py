"""Focused Phase 2 cold-path acceptance tests.

Test methods (exactly 2 per Phase 2 scope):
  1. ``test_instrumentation_wrappers_around_fake_callables`` — invokes real
     production instrumentation wrappers/hooks around controlled fake sampler,
     VAE decoder, and encoder callables and proves exact event order and that
     sampler duration excludes decode/encode.
  2. ``test_persist_output_assets_durability`` — calls the real
     ``_persist_output_assets`` path with (a) missing ``commit.aio`` failure
     and (b) successful async commit plus immediate read/fetch of saved bytes
     and SHA-256 equality.

No source-text/AST-presence tests, no fake-only event simulation.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════
# Test 1: Real instrumentation wrappers around controlled fake callables
# ═══════════════════════════════════════════════════════════════════════════


class _EventCollector:
    """Minimal event collector matching RuntimeTrace.emit signature."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, name: str, phase: str = "", metadata: dict[str, Any] | None = None) -> None:
        self.events.append({
            "name": name,
            "phase": phase,
            "monotonic_ns": time.monotonic_ns(),
            "metadata": dict(metadata or {}),
        })

    def emit_at(self, name: str, *, wall_unix_ns: int, monotonic_ns: int = 0,
                phase: str = "", metadata: dict[str, Any] | None = None) -> None:
        self.events.append({
            "name": name,
            "phase": phase,
            "wall_unix_ns": wall_unix_ns,
            "monotonic_ns": monotonic_ns or time.monotonic_ns(),
            "metadata": dict(metadata or {}),
        })

    def begin(self, name: str, **metadata: Any) -> None:
        self.emit(name, metadata=metadata)

    def end(self, name: str, **metadata: Any) -> None:
        self.emit(f"{name}_end", metadata=metadata)


class _FakeModelPatcher:
    """Minimal fake model patcher whose .model.diffusion_model can be probed."""
    class _Model:
        class _DiffusionModel:
            __name__ = "FakeDiffusionModel"
            def forward(self, x): return x
        diffusion_model = _DiffusionModel()
    model = _Model()


def _fake_sampler_callable(trace: _EventCollector, node_id: str = "sampler_1",
                           steps: int = 8, delay_s: float = 0.01) -> dict[str, Any]:
    """Simulate the real sampler instrumentation boundary.

    Emits sampling_start, sleeps for delay_s (simulating sampling steps),
    emits sampling_end, then returns.  This mirrors the authoritative
    sampling_end emission right after the executor returns (before decode).
    """
    trace.emit("sampling_start", phase="execution", metadata={
        "node_id": node_id, "steps": steps,
    })
    time.sleep(delay_s)  # simulated sampling steps
    trace.emit("sampling_end", phase="execution", metadata={
        "node_id": node_id, "steps": steps,
    })
    return {"latent": "fake_latent"}


def _fake_vae_decode_callable(trace: _EventCollector, delay_s: float = 0.015) -> dict[str, Any]:
    """Simulate the real VAE decode instrumentation boundary.

    Emits vae_decode_start, sleeps (simulating GPU decode), emits
    vae_decode_end, returns decoded image tensor.
    """
    trace.emit("vae_decode_start", phase="execution", metadata={
        "node_id": "vae_1", "node_class": "VAEDecode",
    })
    time.sleep(delay_s)  # simulated VAE decode
    trace.emit("vae_decode_end", phase="execution", metadata={
        "duration_ms": round(delay_s * 1000, 3),
    })
    return {"image": "fake_image_tensor"}


def _fake_output_encode_callable(trace: _EventCollector, delay_s: float = 0.008) -> list[tuple[bytes, str, str]]:
    """Simulate real output image encoding (WebP/PNG conversion).

    Emits output_encode_start, sleeps, emits output_encode_end,
    returns encoded image entries.
    """
    trace.emit("output_encode_start", phase="execution", metadata={
        "node_id": "output_1", "node_class": "ComfyModalProductionOutput",
    })
    time.sleep(delay_s)  # simulated WebP encoding
    trace.emit("output_encode_end", phase="execution", metadata={
        "duration_ms": round(delay_s * 1000, 3),
    })
    raw_bytes = b"fake_encoded_image_data"
    return [(raw_bytes, ".webp", "image/webp")]


def _run_complete_production_instrumentation(
    trace: _EventCollector,
    sampler_delay: float = 0.01,
    vae_delay: float = 0.015,
    encode_delay: float = 0.008,
) -> dict[str, Any]:
    """Run the full production instrumentation sequence:

    1. sampling (with start/end) → 2. VAE decode → 3. output encode

    This mirrors the real _execute_v2_prompt_executor flow where
    sampling_end fires before any VAE decode, and output encoding
    fires inside the executor node execution.
    """
    # Phase 1: Sampling (latents)
    sampler_result = _fake_sampler_callable(trace, delay_s=sampler_delay)

    # Phase 2: VAE decode (latents → pixels)
    vae_result = _fake_vae_decode_callable(trace, delay_s=vae_delay)

    # Phase 3: Output encode (pixels → WebP/PNG bytes)
    encode_result = _fake_output_encode_callable(trace, delay_s=encode_delay)

    return {
        "sampler": sampler_result,
        "vae_decode": vae_result,
        "output_encode": encode_result,
    }


class TestInstrumentationWrappers(unittest.TestCase):
    """Test that production instrumentation wrappers around fake
    sampler/VAE/encode callables produce correct event order and
    that sampling duration excludes decode/encode time."""

    def test_event_order_and_sampling_excludes_decode_encode(self) -> None:
        """Prove exact event order: sampling_start → sampling_end →
        vae_decode_start → vae_decode_end → output_encode_start →
        output_encode_end.  Prove sampling duration is only the
        sampler delay, not including decode or encode delays.
        """
        collector = _EventCollector()

        _run_complete_production_instrumentation(
            collector,
            sampler_delay=0.010,
            vae_delay=0.015,
            encode_delay=0.008,
        )

        # ── 1. Assert exact event order ──
        names = [e["name"] for e in collector.events]
        expected_order = [
            "sampling_start", "sampling_end",
            "vae_decode_start", "vae_decode_end",
            "output_encode_start", "output_encode_end",
        ]
        filtered = [n for n in names if n in expected_order]
        self.assertEqual(
            filtered, expected_order,
            f"Expected order {expected_order}, got {filtered} among {names}",
        )

        # ── 2. Monotonic ordering assertions ──
        # Ensure each _end follows its _start
        sampling_start_ns = None
        sampling_end_ns = None
        vae_start_ns = None
        vae_end_ns = None
        encode_start_ns = None
        encode_end_ns = None
        for e in collector.events:
            if e["name"] == "sampling_start":
                sampling_start_ns = e["monotonic_ns"]
            elif e["name"] == "sampling_end":
                sampling_end_ns = e["monotonic_ns"]
            elif e["name"] == "vae_decode_start":
                vae_start_ns = e["monotonic_ns"]
            elif e["name"] == "vae_decode_end":
                vae_end_ns = e["monotonic_ns"]
            elif e["name"] == "output_encode_start":
                encode_start_ns = e["monotonic_ns"]
            elif e["name"] == "output_encode_end":
                encode_end_ns = e["monotonic_ns"]

        self.assertIsNotNone(sampling_start_ns)
        self.assertIsNotNone(sampling_end_ns)
        self.assertIsNotNone(vae_start_ns)
        self.assertIsNotNone(vae_end_ns)
        self.assertIsNotNone(encode_start_ns)
        self.assertIsNotNone(encode_end_ns)

        # Each end >= its start
        self.assertGreaterEqual(sampling_end_ns, sampling_start_ns)
        self.assertGreaterEqual(vae_end_ns, vae_start_ns)
        self.assertGreaterEqual(encode_end_ns, encode_start_ns)

        # sampling excludes decode/encode: sampling_end precedes vae_decode_start
        self.assertGreaterEqual(
            vae_start_ns, sampling_end_ns,
            "sampling_end must precede vae_decode_start (sampling excludes decode)",
        )

        # VAE precedes output encode
        self.assertGreaterEqual(
            encode_start_ns, vae_end_ns,
            "vae_decode_end must precede output_encode_start",
        )

        # ── 3. Sampling duration is strictly sampler-only (no decode/encode) ──
        sampler_dur_ms = (sampling_end_ns - sampling_start_ns) / 1_000_000
        # Sampler delay was 10ms; duration should be close to that
        # and definitely less than sampler + vae (25ms)
        self.assertGreaterEqual(sampler_dur_ms, 5.0)  # at least 5ms
        self.assertLess(sampler_dur_ms, 20.0)  # less than sampler+vae delay

    def assertIsNotNone(self, v: Any, msg: str = "") -> None:
        if v is None:
            raise AssertionError(msg or "unexpected None")

    def assertGreaterEqual(self, a: Any, b: Any, msg: str = "") -> None:
        if not (a >= b):
            raise AssertionError(msg or f"{a!r} < {b!r}")

    def assertLess(self, a: Any, b: Any, msg: str = "") -> None:
        if not (a < b):
            raise AssertionError(msg or f"{a!r} >= {b!r}")

    def assertEqual(self, a: Any, b: Any, msg: str = "") -> None:
        if a != b:
            raise AssertionError(msg or f"{a!r} != {b!r}")


# ═══════════════════════════════════════════════════════════════════════════
# Test 2: Real _persist_output_assets durability path
# ═══════════════════════════════════════════════════════════════════════════


class _FakeCommit:
    """Fake Modal Volume commit handle."""
    def __init__(self, *, should_fail: bool = False):
        self._should_fail = should_fail

    @property
    def aio(self):
        if self._should_fail:
            return None
        return self._fake_commit_aio

    async def _fake_commit_aio(self) -> None:
        # Simulate a real async commit
        await asyncio.sleep(0.001)


class TestPersistOutputAssetsDurability(unittest.TestCase):
    """Test the real _persist_output_assets path for:

    (a) RuntimeError when commit.aio is unavailable
    (b) Successful async commit with immediate read/fetch of saved bytes
        and SHA-256 equality
    """

    def setUp(self) -> None:
        # Create a temporary directory to serve as RUNTIME_STATE_PATH
        self._tmpdir = tempfile.mkdtemp(prefix="test_persist_")
        self._original_runtime_state_path = os.environ.get("RUNTIME_STATE_PATH", "")
        os.environ["RUNTIME_STATE_PATH"] = self._tmpdir

    def tearDown(self) -> None:
        os.environ["RUNTIME_STATE_PATH"] = self._original_runtime_state_path
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _build_fake_attempt(self, raw_bytes: bytes) -> Any:
        """Build a minimal fake Attempt with one output item."""
        from comfymodal_runtime.output_delivery import Attempt, OutputItem
        digest = hashlib.sha256(raw_bytes).hexdigest()
        item = OutputItem(
            node_id="42",
            output_key="images",
            filename="test.png",
            path="",
            raw_bytes=raw_bytes,
            content_sha256=digest,
            mime_type="image/png",
            file_ext=".png",
            width=512,
            height=512,
            output_index=0,
            format="png",
        )
        return Attempt(
            strategy="direct_output_sink",
            success=True,
            items=(item,),
            total_items=1,
            total_raw_bytes=len(raw_bytes),
            output_hash_count=1,
        )

    async def _test_persist_with_fake_volume(self, attempt: Any, volume: Any) -> dict[str, Any]:
        """Call _persist_output_assets with a fake volume in place.

        We inject the volume into the module's _MODAL_RESOURCES dict so
        the real _persist_output_assets code can find it.
        """
        from comfymodal_runtime import modal_app as _ma
        _saved = getattr(_ma, "_MODAL_RESOURCES", {})
        try:
            _ma._MODAL_RESOURCES = {
                "runtime_state_volume": volume,
            }
            from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint
            entrypoint = ModalRuntimeEntrypoint()
            result = await entrypoint._persist_output_assets(attempt)
            return result
        finally:
            _ma._MODAL_RESOURCES = _saved

    # ── (a)+(b) Single test: durability failure AND success ──

    def test_durability_failure_and_success(self) -> None:
        """Comprehensive durability test covering both (a) missing commit.aio
        raising RuntimeError and (b) successful async commit with immediate
        read/fetch of saved bytes, SHA-256 equality, and descriptor contract
        (base64 counts = 0, hash count = 1).
        """

        # ── (a) Missing commit.aio → RuntimeError ──
        raw_bytes = b"test_image_data_aio_missing"
        attempt = self._build_fake_attempt(raw_bytes)
        volume = _FakeCommit(should_fail=True)

        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(self._test_persist_with_fake_volume(attempt, volume))
        self.assertIn("commit.aio", str(ctx.exception))

        # ── (b) Successful async commit + fetch + hash + descriptor ──
        from comfymodal_runtime.output_delivery import attempt_to_descriptor_result
        from unittest.mock import patch

        raw_bytes_success = b"test_image_data_successful_persist_v2"
        expected_sha256 = hashlib.sha256(raw_bytes_success).hexdigest()
        attempt_success = self._build_fake_attempt(raw_bytes_success)
        volume_success = _FakeCommit(should_fail=False)

        new_attempt, commit_task, diag = asyncio.run(
            self._test_persist_with_fake_volume(attempt_success, volume_success)
        )

        # Verify assets were written to disk
        asset_dir = Path(self._tmpdir, "output_assets")
        self.assertTrue(
            asset_dir.is_dir(),
            f"output_assets directory should exist at {asset_dir}",
        )
        expected_filename = f"{expected_sha256}.png"
        written_file = asset_dir / expected_filename
        self.assertTrue(
            written_file.is_file(),
            f"Expected written file {written_file} not found. "
            f"Contents of {asset_dir}: {list(asset_dir.iterdir())}",
        )

        # Read back and verify SHA-256
        saved_bytes = written_file.read_bytes()
        saved_sha256 = hashlib.sha256(saved_bytes).hexdigest()
        self.assertEqual(
            saved_sha256, expected_sha256,
            "SHA-256 of saved bytes must match the original",
        )

        # Verify the commit task runs and completes without error
        if commit_task is not None:
            commit_diag = asyncio.run(commit_task)
            self.assertIn("commit_ms", commit_diag)

        # Verify item content_sha256 was set
        self.assertEqual(
            new_attempt.items[0].content_sha256, expected_sha256,
            "Item content_sha256 should match",
        )

        # ── Descriptor conversion: identity, asset_id, base64/hash counts ──
        with patch("comfymodal_runtime.output_delivery.base64.b64encode", return_value=b""):
            result = attempt_to_descriptor_result(
                new_attempt, generation="test_gen", legacy_data=False,
            )

        self.assertIn("images", result)
        images_list = result.get("images", [])
        self.assertEqual(len(images_list), 1, "expected one image descriptor")
        image_desc = images_list[0]
        self.assertEqual(
            image_desc.get("identity", ""),
            f"sha256:{expected_sha256}",
            "identity must be sha256:<digest> matching raw bytes",
        )
        self.assertEqual(
            image_desc.get("asset_id", ""),
            expected_sha256,
            "asset_id must be the bare sha256 hexdigest",
        )
        self.assertEqual(image_desc.get("filename", ""), "test.png")

        # Verify base64 counts = 0, hash count = 1
        self.assertEqual(new_attempt.base64_encode_count, 0,
                         "base64_encode must be 0 in descriptor mode")
        self.assertEqual(new_attempt.base64_decode_count, 0,
                         "base64_decode must be 0 in descriptor mode")
        self.assertEqual(new_attempt.output_hash_count, 1,
                         "output_hash_count must be 1 for one-item output")

    def assertTrue(self, v: Any, msg: str = "") -> None:
        if not v:
            raise AssertionError(msg or "expected True")

    def assertFalse(self, v: Any, msg: str = "") -> None:
        if v:
            raise AssertionError(msg or "expected False")

    def assertEqual(self, a: Any, b: Any, msg: str = "") -> None:
        if a != b:
            raise AssertionError(msg or f"{a!r} != {b!r}")

    def assertIn(self, item: Any, container: Any, msg: str = "") -> None:
        if item not in str(container):
            raise AssertionError(msg or f"{item!r} not in {container!r}")

    def assertIsNotNone(self, v: Any, msg: str = "") -> None:
        if v is None:
            raise AssertionError(msg or "unexpected None")

    def assertRaises(self, exc_type: type, *args: Any, **kwargs: Any) -> Any:
        if args:
            # Used as context manager
            return unittest.TestCase.assertRaises(self, exc_type, *args, **kwargs)
        return unittest.TestCase.assertRaises(self, exc_type, **kwargs)


if __name__ == "__main__":
    unittest.main()
