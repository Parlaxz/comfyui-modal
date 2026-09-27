"""Focused offline tests for the generic staged safetensors core."""

from __future__ import annotations

import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

import torch

import comfymodal_runtime.staged_safetensors as staged


def _write_header(
    path: Path, *, dtype: str = "F32", shape=(4,), name: str = "weight"
) -> None:
    raw = bytes(range(max(1, len(shape) and int(torch.tensor(shape).prod().item()) * {
        "F32": 4,
        "BF16": 2,
        "F16": 2,
    }.get(dtype, 1))))
    header = json.dumps({
        name: {
            "dtype": dtype,
            "shape": list(shape),
            "data_offsets": [0, len(raw)],
        }
    }, separators=(",", ":")).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(header)) + header + raw)


class _Event:
    def __init__(self, done: bool = False):
        self.done = done
        self.synchronize_calls = 0

    def query(self):
        return self.done

    def synchronize(self):
        self.synchronize_calls += 1
        self.done = True


class PlanTests(unittest.TestCase):
    def test_exact_same_dtype_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weights.safetensors"
            _write_header(path, dtype="F32", shape=(4,))
            config = staged.StagedConfig(
                enabled=True, producers=1, pool_mb=1, bucket_mb=1
            )
            stage_plan = staged.plan(path, config=config, target_dtype=torch.float32)
            self.assertTrue(stage_plan.supported, stage_plan.fallback_reason)
            source = torch.tensor([1.0, -2.0, 3.5, 8.0], dtype=torch.float32)
            result = staged._cpu_convert(source, stage_plan.specs[0].output_dtype, True)
            self.assertEqual(result.dtype, source.dtype)
            self.assertEqual(
                result.view(torch.uint8).reshape(-1).tolist(),
                source.view(torch.uint8).reshape(-1).tolist(),
            )
            self.assertFalse(stage_plan.specs[0].converted)

    def test_plan_tracks_source_and_output_bytes_for_cpu_cast(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weights.safetensors"
            _write_header(path, dtype="F32", shape=(4,))
            config = staged.StagedConfig(
                enabled=True, producers=1, pool_mb=1, bucket_mb=1
            )
            stage_plan = staged.plan(path, config=config, target_dtype=torch.bfloat16)
            self.assertTrue(stage_plan.supported, stage_plan.fallback_reason)
            self.assertTrue(stage_plan.specs[0].converted)
            self.assertEqual(stage_plan.specs[0].source_nbytes, 16)
            self.assertEqual(stage_plan.specs[0].nbytes, 8)

    def test_plan_accepts_multiple_checkpoint_files(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.safetensors"
            second = Path(directory) / "second.safetensors"
            _write_header(first, name="first")
            _write_header(second, name="second")
            config = staged.StagedConfig(
                enabled=True, producers=1, pool_mb=1, bucket_mb=1
            )
            stage_plan = staged.plan([first, second], config=config)
        self.assertTrue(stage_plan.supported, stage_plan.fallback_reason)
        self.assertEqual(stage_plan.checkpoints, (first, second))
        self.assertEqual(
            {spec.name for spec in stage_plan.specs}, {"first", "second"}
        )
        self.assertTrue(all(spec.source_checkpoint in (first, second)
                            for spec in stage_plan.specs))

    def test_fp32_to_bfloat16_and_float16_parity(self):
        source = torch.tensor(
            [-1000.25, -1.5, 0.0, 1.25, 1000.5], dtype=torch.float32
        )
        for output_dtype in (torch.bfloat16, torch.float16):
            actual = staged._cpu_convert(source, output_dtype, True)
            expected = source.to(dtype=output_dtype)
            self.assertEqual(actual.dtype, output_dtype)
            torch.testing.assert_close(actual, expected)

    def test_integer_conversion_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integer.safetensors"
            _write_header(path, dtype="I8", shape=(4,))
            config = staged.StagedConfig(
                enabled=True, producers=1, pool_mb=1, bucket_mb=1
            )
            stage_plan = staged.plan(path, config=config, target_dtype=torch.float16)
            self.assertEqual(stage_plan.fallback_reason, "dtype_conversion_unsupported")

    def test_unknown_dtype_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.safetensors"
            _write_header(path, dtype="CUSTOM", shape=(4,))
            config = staged.StagedConfig(
                enabled=True, producers=1, pool_mb=1, bucket_mb=1
            )
            stage_plan = staged.plan(path, config=config)
            self.assertEqual(stage_plan.fallback_reason, "unsupported_dtype:CUSTOM")

    def test_fp8_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fp8.safetensors"
            _write_header(path, dtype="F8_E4M3", shape=(4,))
            config = staged.StagedConfig(
                enabled=True, producers=1, pool_mb=1, bucket_mb=1
            )
            stage_plan = staged.plan(path, config=config)
            self.assertEqual(stage_plan.fallback_reason, "unsupported_dtype:F8_E4M3")


class PackedBucketPlanTests(unittest.TestCase):
    def _spec(self, name: str, nbytes: int, dtype: Any = torch.uint8):
        return staged.TensorSpec(
            name=name,
            source_dtype_name="U8" if dtype is torch.uint8 else "BF16",
            source_dtype=dtype,
            output_dtype=dtype,
            shape=(nbytes // torch.empty((), dtype=dtype).element_size(),),
            nbytes=nbytes,
            offset=0,
        )

    def test_tiny_tensors_pack_into_one_bucket(self):
        specs = (self._spec("a", 2), self._spec("b", 3), self._spec("c", 1))
        layout, packed_bytes = staged._packed_layout(specs)
        buckets = staged._packed_bucket_plan(specs, layout, packed_bytes, 8)
        self.assertEqual(len(buckets), 1)
        self.assertEqual(buckets[0][1], 6)
        self.assertEqual(len(buckets[0][2]), 3)

    def test_tensor_crossing_boundary_is_split_at_exact_offsets(self):
        specs = (self._spec("a", 6), self._spec("b", 6))
        layout, packed_bytes = staged._packed_layout(specs)
        buckets = staged._packed_bucket_plan(specs, layout, packed_bytes, 8)
        self.assertEqual(len(buckets), 2)
        self.assertEqual(buckets[0][2][-1], ("b", 0, 6, 2))
        self.assertEqual(buckets[1][2][0], ("b", 2, 0, 4))

    def test_multiple_crossings_scale_with_bucket_count(self):
        specs = (self._spec("a", 10), self._spec("b", 10))
        layout, packed_bytes = staged._packed_layout(specs)
        buckets = staged._packed_bucket_plan(specs, layout, packed_bytes, 8)
        self.assertEqual(len(buckets), 3)
        self.assertNotEqual(len(buckets), len(specs))
        self.assertEqual([bucket[1] for bucket in buckets], [8, 8, 4])

    def test_alignment_gap_is_not_exposed_as_a_tensor_range(self):
        specs = (self._spec("bf16", 2, torch.bfloat16), self._spec("f32", 4, torch.float32))
        layout, packed_bytes = staged._packed_layout(specs)
        self.assertEqual(layout, {"bf16": 0, "f32": 4})
        self.assertEqual(packed_bytes, 8)
        buckets = staged._packed_bucket_plan(specs, layout, packed_bytes, 8)
        self.assertEqual(buckets[0][2], (("bf16", 0, 0, 2), ("f32", 0, 4, 4)))

    def test_final_partial_bucket_and_exact_reconstruction(self):
        specs = (self._spec("a", 6), self._spec("b", 6), self._spec("c", 2))
        layout, packed_bytes = staged._packed_layout(specs)
        buckets = staged._packed_bucket_plan(specs, layout, packed_bytes, 8)
        source = {"a": bytes(range(6)), "b": bytes(range(10, 16)), "c": bytes((20, 21))}
        packed = bytearray(packed_bytes)
        for bucket_start, _, ranges in buckets:
            host = bytearray(8)
            for name, source_offset, bucket_offset, size in ranges:
                host[bucket_offset:bucket_offset + size] = source[name][source_offset:source_offset + size]
            for name, source_offset, bucket_offset, size in ranges:
                tensor_start = layout[name] + source_offset
                packed[tensor_start:tensor_start + size] = host[bucket_offset:bucket_offset + size]
        expected = source["a"] + source["b"] + source["c"]
        self.assertEqual(bytes(packed), expected)
        self.assertEqual(buckets[-1][1], 6)

    def test_packed_buckets_partition_across_producers(self):
        buckets = tuple((index, 1, ()) for index in range(5))
        partitions = staged._partition_packed_buckets(buckets, 2)
        self.assertEqual([len(partition) for partition in partitions], [3, 2])
        self.assertEqual(
            tuple(bucket for partition in partitions for bucket in partition),
            buckets,
        )


class PoolTests(unittest.TestCase):
    def test_pool_records_pinned_state_when_allocator_exposes_it(self):
        class PinnedBuffer:
            def is_pinned(self):
                return True

        pool = staged._PinnedSlabPool(2, 8, allocator=lambda size: PinnedBuffer())
        self.assertTrue(pool.host_slab_is_pinned)
        pool.close()

    def test_slab_cannot_recycle_before_event_completion(self):
        pool = staged._PinnedSlabPool(1, 8, allocator=lambda size: bytearray(size))
        slab = pool._try_reclaim()
        self.assertIsNotNone(slab)
        event = _Event(done=False)
        pool.release(slab, event)
        self.assertIsNone(pool._try_reclaim())
        event.done = True
        self.assertIs(pool._try_reclaim(), slab)
        pool.close()

    def test_pool_is_bounded(self):
        allocations = []

        def allocate(size):
            allocations.append(size)
            return bytearray(size)

        config = staged.StagedConfig(
            enabled=True, producers=4, pool_mb=4, bucket_mb=1
        )
        pool = staged._PinnedSlabPool(
            config.slab_count, config.bucket_mb * staged._MIB, allocator=allocate
        )
        self.assertEqual(len(allocations), 4)
        self.assertEqual(pool.allocated_bytes, 4 * staged._MIB)
        self.assertEqual(pool.allocated_bytes, config.pool_bytes)
        pool.close()

    def test_unconfirmed_pin_state_is_not_promoted_to_fast_path(self):
        class UnpinnedBuffer:
            def is_pinned(self):
                return False

        config = staged.StagedConfig(enabled=True, producers=1, pool_mb=1, bucket_mb=1)
        spec = staged.TensorSpec(
            name="weight",
            source_dtype_name="U8",
            source_dtype=torch.uint8,
            output_dtype=torch.uint8,
            shape=(1,),
            nbytes=1,
            offset=0,
        )
        plan = staged.StagePlan(Path("weight.safetensors"), config, specs=(spec,))
        with mock.patch.object(staged, "_allocate_pinned", return_value=UnpinnedBuffer()):
            prepared = staged.prepare(plan)
        self.assertEqual(prepared.fallback_reason, "pinned_memory_unconfirmed")
        self.assertFalse(prepared.ready)
        self.assertFalse(prepared.host_slab_is_pinned)
        self.assertEqual(prepared.pool.allocated_bytes, 0)
        prepared.close()

    def test_native_pin_budget_reservation_is_released(self):
        calls = []
        native = SimpleNamespace(
            TOTAL_PINNED_MEMORY=0,
            MAX_PINNED_MEMORY=1024 * 1024,
            ensure_pin_budget=lambda size: calls.append(("budget", size)) or True,
            ensure_pin_registerable=lambda size: calls.append(("register", size)) or True,
        )
        with mock.patch.object(
            staged, "_native_model_management", return_value=native
        ):
            reservation = staged._native_pin_reservation(64)
            self.assertTrue(callable(reservation))
            self.assertEqual(native.TOTAL_PINNED_MEMORY, 64)
            reservation()
        self.assertEqual(native.TOTAL_PINNED_MEMORY, 0)
        self.assertEqual(calls, [("budget", 64), ("register", 64)])

    def test_native_pin_budget_unavailable_is_distinct_from_rejection(self):
        unavailable = SimpleNamespace(
            MAX_PINNED_MEMORY=0,
            ensure_pin_budget=lambda size: False,
            ensure_pin_registerable=lambda size: False,
        )
        rejected = SimpleNamespace(
            MAX_PINNED_MEMORY=1024 * 1024,
            ensure_pin_budget=lambda size: False,
            ensure_pin_registerable=lambda size: True,
        )
        with mock.patch.object(
            staged, "_native_model_management", return_value=unavailable
        ):
            reservation, available, was_rejected, reason = staged._native_pin_budget_status(64)
        self.assertIsNone(reservation)
        self.assertFalse(available)
        self.assertFalse(was_rejected)
        self.assertEqual(reason, "native_pin_budget_uninitialized")
        with mock.patch.object(
            staged, "_native_model_management", return_value=rejected
        ):
            reservation, available, was_rejected, reason = staged._native_pin_budget_status(64)
        self.assertIs(reservation, False)
        self.assertTrue(available)
        self.assertTrue(was_rejected)
        self.assertEqual(reason, "native_pin_budget_rejected")


class LifecycleTests(unittest.TestCase):
    def test_env_config_reads_all_staged_flags(self):
        values = {
            "COMFYMODAL_V2_STAGED_SAFETENSORS": "1",
            "COMFYMODAL_V2_STAGED_PRODUCERS": "3",
            "COMFYMODAL_V2_STAGED_POOL_MB": "12",
            "COMFYMODAL_V2_STAGED_BUCKET_MB": "2",
            "COMFYMODAL_V2_STAGED_CPU_CAST": "0",
            "COMFYMODAL_V2_STAGED_ASYNC_H2D": "false",
            "COMFYMODAL_V2_STAGED_CONTIGUOUS_GPU_BUCKETS": "yes",
        }
        with mock.patch.dict(os.environ, values, clear=False):
            config = staged.config_from_env()
        self.assertTrue(config.enabled)
        self.assertEqual(config.producers, 3)
        self.assertEqual(config.pool_mb, 12)
        self.assertEqual(config.bucket_mb, 2)
        self.assertFalse(config.cpu_cast)
        self.assertFalse(config.async_h2d)
        self.assertTrue(config.contiguous_gpu_buckets)

    def test_flag_off_returns_fallback_without_opening_file(self):
        config = staged.StagedConfig(enabled=False)
        stage_plan = staged.plan("does-not-exist.safetensors", config=config)
        self.assertEqual(stage_plan.fallback_reason, "flag_off")
        with mock.patch.object(staged, "_open_reader") as open_reader:
            prepared = staged.prepare(stage_plan)
            result = staged.commit(prepared)
        open_reader.assert_not_called()
        self.assertFalse(result.success)
        self.assertEqual(result.fallback_reason, "flag_off")

    def test_exception_cleanup_closes_pool_and_reports_reason(self):
        config = staged.StagedConfig(
            enabled=True, producers=1, pool_mb=1, bucket_mb=1
        )
        spec = staged.TensorSpec(
            name="weight",
            source_dtype_name="F32",
            source_dtype=torch.float32,
            output_dtype=torch.float32,
            shape=(1,),
            nbytes=4,
            offset=0,
        )
        stage_plan = staged.StagePlan(
            Path("weights.safetensors"), config, specs=(spec,), checkpoint_bytes=100
        )
        prepared = staged.PreparedStage(stage_plan)
        prepared.pool = staged._PinnedSlabPool(
            1, staged._MIB, allocator=lambda size: bytearray(size)
        )
        prepared._peak_pinned_bytes = prepared.pool.allocated_bytes
        with mock.patch.object(staged, "_cuda_available", return_value=True), \
                mock.patch.object(staged, "_new_copy_stream", side_effect=RuntimeError("boom")):
            result = staged.commit(prepared, device="cuda")
        self.assertFalse(result.success)
        self.assertEqual(result.fallback_reason, "commit_exception:RuntimeError")
        self.assertEqual(result.peak_pinned_bytes, staged._MIB)
        self.assertTrue(prepared._closed)
        self.assertEqual(prepared.pool.allocated_bytes, 0)

    def test_contiguous_gpu_buckets_have_a_safe_dense_plan(self):
        config = staged.StagedConfig(
            enabled=True,
            producers=1,
            pool_mb=1,
            bucket_mb=1,
            contiguous_gpu_buckets=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packed.safetensors"
            _write_header(path, dtype="F32", shape=(4,))
            stage_plan = staged.plan(path, config=config)
        self.assertTrue(stage_plan.supported, stage_plan.fallback_reason)
        self.assertTrue(stage_plan.config.contiguous_gpu_buckets)

    def test_contiguous_prepare_uses_configured_producer_workers(self):
        class PinnedBuffer:
            def is_pinned(self):
                return True

        class Future:
            def done(self):
                return True

            def result(self):
                return None

        submitted = []

        class Executor:
            def __init__(self, max_workers, thread_name_prefix):
                self.max_workers = max_workers

            def submit(self, function, *args):
                submitted.append((function, args))
                return Future()

            def shutdown(self, wait, cancel_futures=False):
                return None

        config = staged.StagedConfig(
            enabled=True,
            producers=3,
            pool_mb=4,
            bucket_mb=1,
            contiguous_gpu_buckets=True,
        )
        spec = staged.TensorSpec(
            name="weight",
            source_dtype_name="U8",
            source_dtype=torch.uint8,
            output_dtype=torch.uint8,
            shape=(4,),
            nbytes=4,
            offset=0,
        )
        stage_plan = staged.StagePlan(
            Path("weights.safetensors"), config, specs=(spec,)
        )
        buckets = tuple((index, 1, ()) for index in range(5))
        with mock.patch.object(staged, "_ThreadPoolExecutor", Executor), \
                mock.patch.object(
                    staged, "_allocate_pinned", return_value=PinnedBuffer()
                ), \
                mock.patch.object(
                    staged, "_packed_bucket_plan", return_value=buckets
                ):
            prepared = staged.prepare(stage_plan)
        self.assertTrue(prepared.ready)
        self.assertEqual(len(submitted), 3)
        self.assertEqual(
            len({id(args[0]) for _, args in submitted}), 1
        )
        self.assertEqual(submitted[0][1][0].qsize(), 5)
        prepared.close()

    def test_bucket_first_source_fill_reads_ranges_and_preserves_bytes(self):
        import safetensors.torch

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            staged, "_MIB", 8
        ):
            path = Path(directory) / "bucket-first.safetensors"
            source = {
                "a": torch.arange(10, dtype=torch.uint8),
                "b": torch.arange(10, 20, dtype=torch.uint8),
            }
            safetensors.torch.save_file(source, str(path))
            config = staged.StagedConfig(
                enabled=True, producers=2, pool_mb=4, bucket_mb=1,
                contiguous_gpu_buckets=True,
            )
            stage_plan = staged.plan(path, config=config)
            prepared = staged.PreparedStage(stage_plan)
            prepared.pool = staged._PinnedSlabPool(
                4, 8, allocator=lambda size: torch.empty(size, dtype=torch.uint8)
            )
            layout, packed_bytes = staged._packed_layout(stage_plan.specs)
            bucket_plan = staged._packed_bucket_plan(
                stage_plan.specs, layout, packed_bytes, 8
            )
            with mock.patch.object(
                prepared, "_read_source_bytes",
                side_effect=AssertionError("tensor materialization used"),
            ):
                prepared._produce_packed(bucket_plan)
            packed = bytearray(packed_bytes)
            while True:
                try:
                    chunk = prepared.queue.get_nowait()
                except staged._queue.Empty:
                    break
                packed[chunk.destination_offset:chunk.destination_offset + chunk.size] = (
                    bytes(chunk.slab.tensor[:chunk.size].tolist())
                )
                prepared.queue.task_done()
            self.assertEqual(bytes(packed), bytes(range(20)))
            self.assertEqual(prepared.exact_copy_bytes, 20)
            self.assertEqual(prepared.cpu_cast_bytes, 0)
            self.assertGreaterEqual(prepared.source_read_ms, 0.0)
            self.assertGreater(prepared.bucket_pack_cpu_ms, 0.0)
            prepared.close()

    def test_bucket_publishes_before_later_tensor_range_is_read(self):
        import safetensors.torch

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            staged, "_MIB", 8
        ):
            path = Path(directory) / "publish-early.safetensors"
            safetensors.torch.save_file(
                {"a": torch.arange(8, dtype=torch.uint8),
                 "b": torch.arange(8, 16, dtype=torch.uint8)},
                str(path),
            )
            config = staged.StagedConfig(
                enabled=True, producers=1, pool_mb=4, bucket_mb=1,
                contiguous_gpu_buckets=True,
            )
            stage_plan = staged.plan(path, config=config)
            prepared = staged.PreparedStage(stage_plan)
            prepared.pool = staged._PinnedSlabPool(
                4, 8, allocator=lambda size: torch.empty(size, dtype=torch.uint8)
            )
            layout, packed_bytes = staged._packed_layout(stage_plan.specs)
            bucket_plan = staged._packed_bucket_plan(
                stage_plan.specs, layout, packed_bytes, 8
            )
            published = __import__("threading").Event()
            continue_fill = __import__("threading").Event()
            reads = []
            original_put = prepared._put
            original_read = prepared._read_source_range

            def read_range(spec, source_offset, size, handle):
                reads.append((spec.name, source_offset, size))
                return original_read(spec, source_offset, size, handle)

            def put(chunk):
                original_put(chunk)
                if chunk.destination_offset == 0:
                    published.set()
                    continue_fill.wait(1.0)

            with mock.patch.object(prepared, "_put", side_effect=put), \
                    mock.patch.object(
                        prepared, "_read_source_range", side_effect=read_range
                    ):
                worker = __import__("threading").Thread(
                    target=prepared._produce_packed, args=(bucket_plan,)
                )
                worker.start()
                self.assertTrue(published.wait(1.0))
                self.assertEqual([name for name, _, _ in reads], ["a"])
                continue_fill.set()
                worker.join(1.0)
            self.assertFalse(worker.is_alive())
            self.assertEqual([name for name, _, _ in reads], ["a", "b"])
            self.assertEqual(prepared.exact_copy_bytes, 16)
            prepared.close()

    def test_result_phase_is_identity_for_adapter_compatibility(self):
        committed = staged.fallback("test")
        self.assertIs(staged.result(committed), committed)

    def test_result_reports_cast_and_exact_byte_partitions(self):
        config = staged.StagedConfig(enabled=True, producers=4, pool_mb=1, bucket_mb=1)
        prepared = staged.PreparedStage(staged.StagePlan(Path("x"), config))
        prepared.add_transfer_bytes(cast=8, exact=16)
        committed = staged._result_from(
            prepared,
            success=True,
            tensors={},
            disk_ms=1.0,
            enqueue_ms=2.0,
            device_ms=None,
            consumer_wait_ms=0.0,
        )
        self.assertEqual(committed.cpu_cast_bytes, 8)
        self.assertEqual(committed.exact_copy_bytes, 16)
        self.assertEqual(committed.metrics["cpu_cast_bytes"], 8)
        self.assertEqual(committed.metrics["exact_copy_bytes"], 16)
        committed.close()

    def test_parallel_boundary_reads_count_transfer_bytes_once(self):
        config = staged.StagedConfig(enabled=True, producers=4, pool_mb=4, bucket_mb=1)
        prepared = staged.PreparedStage(staged.StagePlan(Path("x"), config))
        spec = staged.TensorSpec(
            name="weight",
            source_dtype_name="U8",
            source_dtype=torch.uint8,
            output_dtype=torch.uint8,
            shape=(8,),
            nbytes=8,
            offset=0,
        )
        prepared._record_transfer_bytes_once(spec)
        prepared._record_transfer_bytes_once(spec)
        self.assertEqual(prepared.exact_copy_bytes, 8)
        self.assertEqual(prepared.cpu_cast_bytes, 0)
        prepared.close()

    def test_result_reports_packed_bucket_and_dma_fields(self):
        config = staged.StagedConfig(
            enabled=True, producers=4, pool_mb=4, bucket_mb=1,
            contiguous_gpu_buckets=True,
        )
        prepared = staged.PreparedStage(staged.StagePlan(Path("x"), config))
        prepared.host_slab_is_pinned = True
        prepared.host_slab_is_pinned_per_slot = (True, True, True, True)
        prepared._host_slab_count = 4
        prepared._packed_model_bytes = 10
        prepared._gpu_bucket_count = 1
        prepared._copy_sizes = [4, 4, 2]
        prepared._h2d_stream_span_ms = 5.0
        prepared._h2d_dma_busy_ms = 3.0
        prepared._h2d_stream_idle_estimate_ms = 2.0
        committed = staged._result_from(
            prepared, success=True, tensors={}, disk_ms=1.0,
            enqueue_ms=2.0, device_ms=5.0, consumer_wait_ms=0.0,
        )
        self.assertEqual(committed.metrics["h2d_bucket_count"], 3)
        self.assertEqual(committed.metrics["median_h2d_copy_bytes"], 4)
        self.assertEqual(committed.metrics["h2d_final_bucket_bytes"], 2)
        self.assertTrue(committed.metrics["host_slab_is_pinned_all"])
        self.assertEqual(committed.metrics["h2d_stream_idle_estimate_ms"], 2.0)
        committed.close()

    def test_stage_result_close_releases_pool_accounting(self):
        released = []
        class PinnedBuffer:
            def is_pinned(self):
                return True

        config = staged.StagedConfig(enabled=True, producers=1, pool_mb=1, bucket_mb=1)
        prepared = staged.PreparedStage(staged.StagePlan(Path("x"), config))
        prepared.pool = staged._PinnedSlabPool(
            1, staged._MIB, allocator=lambda size: PinnedBuffer(),
            on_close=lambda: released.append(True),
        )
        prepared._peak_pinned_bytes = staged._MIB
        prepared.host_slab_is_pinned = True
        prepared.host_slab_is_pinned_per_slot = (True,)
        result = staged._result_from(
            prepared, success=True, tensors={}, disk_ms=0.0,
            enqueue_ms=0.0, device_ms=0.0, consumer_wait_ms=0.0,
        )
        result.close()
        self.assertEqual(prepared.pool.allocated_bytes, 0)
        self.assertEqual(released, [True])

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA unavailable")
    def test_cuda_transfer_reports_exact_cast_and_packed_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transfer.safetensors"
            _write_header(path, dtype="F32", shape=(4,))
            for target_dtype, expected_cast, expected_exact in (
                (None, 0, 16),
                (torch.bfloat16, 8, 0),
            ):
                config = staged.StagedConfig(
                    enabled=True,
                    producers=1,
                    pool_mb=1,
                    bucket_mb=1,
                    contiguous_gpu_buckets=True,
                )
                stage_plan = staged.plan(
                    path, config=config, target_dtype=target_dtype
                )
                prepared = staged.prepare(stage_plan)
                committed = staged.commit(prepared, device="cuda")
                self.assertTrue(committed.success, committed.error)
                self.assertEqual(committed.cpu_cast_bytes, expected_cast)
                self.assertEqual(committed.exact_copy_bytes, expected_exact)
                self.assertIsNotNone(committed._gpu_owner)
                self.assertEqual(
                    committed.tensors["weight"].data_ptr(),
                    committed._gpu_owner.data_ptr(),
                )
                committed.close()

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA unavailable")
    def test_cuda_packed_buckets_preserve_crossing_tensor_views(self):
        import safetensors.torch

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(staged, "_MIB", 8):
            path = Path(directory) / "bucketed.safetensors"
            source = {
                "a": torch.arange(10, dtype=torch.uint8),
                "b": torch.arange(10, 20, dtype=torch.uint8),
            }
            safetensors.torch.save_file(source, str(path))
            config = staged.StagedConfig(
                enabled=True,
                producers=4,
                pool_mb=4,
                bucket_mb=1,
                contiguous_gpu_buckets=True,
            )
            stage_plan = staged.plan(path, config=config)
            prepared = staged.prepare(stage_plan)
            committed = staged.commit(prepared, device="cuda")
            self.assertTrue(committed.success, committed.error)
            self.assertTrue(committed.host_slab_is_pinned_all)
            self.assertEqual(committed.packed_model_bytes, 20)
            self.assertEqual(committed.copy_count, 3)
            self.assertEqual(committed.h2d_final_bucket_bytes, 4)
            self.assertEqual(committed.min_h2d_copy_bytes, 4)
            self.assertEqual(committed.max_h2d_copy_bytes, 8)
            torch.testing.assert_close(committed.tensors["a"].cpu(), source["a"])
            torch.testing.assert_close(committed.tensors["b"].cpu(), source["b"])
            self.assertIsNotNone(committed._gpu_owner)
            committed.close()


class GenericSurfaceTests(unittest.TestCase):
    def test_no_family_specific_branches_or_global_sync(self):
        source = Path(staged.__file__).read_text(encoding="utf-8")
        self.assertNotIn("CLIP", source)
        self.assertNotIn("UNET", source)
        self.assertNotIn("torch.cuda.synchronize", source)
        self.assertNotIn("pin_memory()", source)


if __name__ == "__main__":
    unittest.main()
