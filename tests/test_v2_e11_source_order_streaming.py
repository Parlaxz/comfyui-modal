"""Offline E11 tests for source-order safetensors staging."""

from __future__ import annotations

import io
import json
import os
import queue
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch

import comfymodal_runtime.source_order_safetensors as source_order
import comfymodal_runtime.staged_safetensors as staged


def _write_file(path: Path, entries: list[tuple[str, str, tuple[int, ...], bytes]]) -> None:
    offset = 0
    header: dict[str, object] = {}
    for name, dtype, shape, payload in entries:
        header[name] = {
            "dtype": dtype,
            "shape": list(shape),
            "data_offsets": [offset, offset + len(payload)],
        }
        offset += len(payload)
    raw_header = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload = b"".join(item[3] for item in entries)
    path.write_bytes(struct.pack("<Q", len(raw_header)) + raw_header + payload)


class SourceOrderLayoutTests(unittest.TestCase):
    def test_multi_file_order_blocks_and_direct_read(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.safetensors"
            second = Path(directory) / "second.safetensors"
            _write_file(first, [("a", "U8", (10,), bytes(range(10)))])
            _write_file(second, [("b", "U8", (6,), bytes(range(10, 16)))])
            first_data_start = 8 + struct.unpack("<Q", first.read_bytes()[:8])[0]
            second_data_start = 8 + struct.unpack("<Q", second.read_bytes()[:8])[0]
            specs = {
                first: {
                    "data_start": first_data_start,
                    "file_size": first.stat().st_size,
                    "tensors": {
                        "a": {"dtype": "U8", "shape": [10], "data_offsets": [0, 10]}
                    },
                    "expected_dtypes": {"a": "U8"},
                },
                second: {
                    "data_start": second_data_start,
                    "file_size": second.stat().st_size,
                    "tensors": {
                        "b": {"dtype": "U8", "shape": [6], "data_offsets": [0, 6]}
                    },
                    "expected_dtypes": {"b": "U8"},
                },
            }
            layout = source_order.build_layout(
                specs, [first, second], {"a": 1, "b": 1}
            )
            eligibility = source_order.assess_eligibility(
                specs, layout, {"a": 1, "b": 1}
            )
            self.assertTrue(eligibility.all_direct)
            self.assertEqual([item.file for item in layout.files], [first, second])
            blocks = list(source_order.iter_blocks(layout, 8))
            self.assertEqual([block.size for block in blocks], [8, 2, 6])
            self.assertLess(blocks[0].file_index, blocks[-1].file_index)
            target = bytearray(6)
            with second.open("rb") as handle:
                source_order.read_into(handle, target, 6, second_data_start)
            self.assertEqual(bytes(target), bytes(range(10, 16)))

    def test_direct_read_uses_supplied_storage_without_intermediate_bytes(self):
        target = bytearray(5)
        handle = io.BytesIO(b"0123456789")
        source_order.read_into(handle, target, 5, 3)
        self.assertEqual(bytes(target), b"34567")


class SourceOrderPlanTests(unittest.TestCase):
    def _config(self) -> staged.StagedConfig:
        return staged.StagedConfig(
            enabled=True,
            producers=4,
            pool_mb=1,
            bucket_mb=1,
            source_order_enabled=True,
        )

    def test_exact_plan_is_source_order_eligible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weights.safetensors"
            _write_file(path, [("weight", "U8", (20,), bytes(range(20)))])
            plan = staged.plan(path, config=self._config())
        self.assertTrue(plan.supported, plan.fallback_reason)
        self.assertTrue(plan.source_order_eligible)
        self.assertIsNotNone(plan.source_layout)
        self.assertEqual(plan.source_order_fallback_reason, None)
        self.assertEqual(plan.alignment_fallback_tensor_count, 0)

    def test_cast_is_reported_as_source_order_fallback_but_plan_remains_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weights.safetensors"
            _write_file(path, [("weight", "F32", (4,), bytes(range(16)))])
            plan = staged.plan(
                path, config=self._config(), target_dtype=torch.bfloat16
            )
        self.assertTrue(plan.supported, plan.fallback_reason)
        self.assertFalse(plan.source_order_eligible)
        self.assertEqual(
            plan.source_order_fallback_reason,
            "source_order_dtype_cast_required",
        )

    def test_alignment_failure_falls_back_without_padding_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "misaligned.safetensors"
            header = json.dumps(
                {
                    "byte": {
                        "dtype": "U8",
                        "shape": [1],
                        "data_offsets": [0, 1],
                    },
                    "half": {
                        "dtype": "BF16",
                        "shape": [1],
                        "data_offsets": [1, 3],
                    },
                },
                separators=(",", ":"),
            ).encode("utf-8")
            path.write_bytes(struct.pack("<Q", len(header)) + header + b"abc")
            plan = staged.plan(path, config=self._config())
        self.assertTrue(plan.supported, plan.fallback_reason)
        self.assertFalse(plan.source_order_eligible)
        self.assertEqual(plan.source_order_fallback_reason, "source_order_alignment_failure")
        self.assertEqual(plan.alignment_fallback_tensor_count, 1)

    def test_env_flag_is_default_off_and_opt_in(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(staged.config_from_env().source_order_enabled)
        with mock.patch.dict(
            os.environ, {"COMFYMODAL_V2_STAGED_SOURCE_ORDER": "1"}, clear=True
        ):
            self.assertTrue(staged.config_from_env().source_order_enabled)


class SourceOrderProducerTests(unittest.TestCase):
    def test_source_blocks_fill_slabs_directly_and_preserve_final_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "blocks.safetensors"
            raw = bytes(range(20))
            _write_file(path, [("weight", "U8", (20,), raw)])
            config = staged.StagedConfig(
                enabled=True,
                producers=4,
                pool_mb=4,
                bucket_mb=1,
                source_order_enabled=True,
            )
            plan = staged.plan(path, config=config)
            prepared = staged.PreparedStage(plan)
            prepared.pool = staged._PinnedSlabPool(
                4, 8, allocator=lambda size: bytearray(size)
            )
            jobs: queue.Queue = queue.Queue()
            blocks = list(source_order.iter_blocks(plan.source_layout, 8))
            for block in blocks:
                jobs.put(block)
            prepared._produce_source_order(jobs)
            collected = bytearray(plan.source_layout.storage_bytes)
            chunks = []
            while True:
                try:
                    chunk = prepared.queue.get_nowait()
                except queue.Empty:
                    break
                chunks.append(chunk)
                destination_offset = int(chunk.destination_offset or 0)
                collected[
                    destination_offset:destination_offset + chunk.size
                ] = chunk.slab.tensor[:chunk.size]
                prepared.queue.task_done()
            prepared.close()
        self.assertEqual([chunk.size for chunk in chunks], [8, 8, 4])
        self.assertEqual(bytes(collected[:20]), raw)
        self.assertEqual(prepared._source_read_calls, 3)
        self.assertEqual(prepared._source_sequential_bytes, 20)
        self.assertEqual(prepared._source_read_sizes, [8, 8, 4])

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA unavailable")
    def test_cuda_source_order_views_preserve_multi_file_bytes_and_owner(self):
        import safetensors.torch

        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.safetensors"
            second = Path(directory) / "second.safetensors"
            first_values = {
                "byte": torch.arange(17, dtype=torch.uint8),
                "float": torch.tensor([1.25, -2.5, 3.75], dtype=torch.float32),
            }
            second_values = {
                "half": torch.tensor([4.0, 5.5], dtype=torch.float16),
            }
            safetensors.torch.save_file(first_values, str(first))
            safetensors.torch.save_file(second_values, str(second))
            config = staged.StagedConfig(
                enabled=True,
                producers=4,
                pool_mb=1,
                bucket_mb=1,
                source_order_enabled=True,
            )
            plan = staged.plan([first, second], config=config)
            self.assertTrue(plan.source_order_eligible, plan.source_order_fallback_reason)
            committed = staged.commit(staged.prepare(plan), device="cuda")
            self.assertTrue(committed.success, committed.error)
            self.assertTrue(committed.source_order_enabled)
            self.assertTrue(committed.source_order_eligible)
            self.assertEqual(committed.source_repack_bytes, 0)
            self.assertEqual(committed.cpu_cast_bytes, 0)
            self.assertEqual(committed.exact_copy_bytes, 17 + 12 + 4)
            self.assertEqual(committed.source_to_pinned_copy_bytes, 0)
            self.assertGreater(committed.source_read_calls, 0)
            self.assertIsNotNone(committed._gpu_owner)
            torch.testing.assert_close(committed.tensors["byte"].cpu(), first_values["byte"])
            torch.testing.assert_close(committed.tensors["float"].cpu(), first_values["float"])
            torch.testing.assert_close(committed.tensors["half"].cpu(), second_values["half"])
            self.assertEqual(committed.tensors["half"].dtype, torch.float16)
            self.assertEqual(tuple(committed.tensors["float"].shape), (3,))
            committed.close()
            self.assertEqual(committed._owner, None)


if __name__ == "__main__":
    unittest.main()
