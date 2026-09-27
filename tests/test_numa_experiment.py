"""Unit tests for the NUMA experiment module (no Modal / no Linux needed).

Covers: numa_maps parsing (with /proc/self/maps cross-reference), per-range
NUMA counts, storage range merging, page address expansion, the raw
syscall(2) move_pages wrapper via a FAKE syscall (verifying status counting
and verification math), and JSON-safe flattening.  The syscall-heavy paths
(mmap/mbind/migrate on real pages) only run on the Modal Linux container
and are covered by the shadow experiment itself.
"""
from __future__ import annotations

import ctypes
import unittest
from unittest import mock

from comfymodal_runtime import numa_experiment as ne

NUMA_MAPS_FIXTURE = [
    "00400000 default file=/usr/bin/python3.11 mapped=15 N0=15 kernelpagesize_kB=4",
    "55a1c0000000 default anon=512 dirty=512 N0=300 N1=212 kernelpagesize_kB=4",
    "7f0000000000 default anon=4096 dirty=4096 N1=4096 kernelpagesize_kB=4",
    "7f0040000000 default anon=2048 dirty=2048 N0=2048 kernelpagesize_kB=4",
    "7fff00000000 default stack anon=8 dirty=8 N0=8 kernelpagesize_kB=4",
]

MAPS_FIXTURE = [
    "00400000-00402000 r-xp 00000000 00:00 0",
    "55a1c0000000-55a1c0800000 rw-p 00000000 00:00 0",
    "7f0000000000-7f0040000000 rw-p 00000000 00:00 0",
    "7f0040000000-7f0080000000 rw-p 00000000 00:00 0",
    "7fff00000000-7fff00020000 rw-p 00000000 00:00 0",
]


def _patched_read():
    """Patch Path.read_text so the two /proc reads return the fixtures."""
    return mock.patch.object(
        ne.Path, "read_text", side_effect=[
            "\n".join(NUMA_MAPS_FIXTURE), "\n".join(MAPS_FIXTURE),
        ],
    )


class NumaMapsParseTest(unittest.TestCase):
    def test_parse_numa_lines(self):
        vmas = ne.parse_numa_maps_lines(NUMA_MAPS_FIXTURE)
        self.assertEqual(len(vmas), 5)
        self.assertEqual(vmas[0]["node_counts"], {"N0": 15})
        self.assertEqual(vmas[1]["node_counts"], {"N0": 300, "N1": 212})
        self.assertEqual(vmas[2]["node_counts"], {"N1": 4096})
        self.assertEqual(vmas[1]["addr"], 0x55a1c0000000)

    def test_parse_rejects_garbage(self):
        vmas = ne.parse_numa_maps_lines([
            "00400000 default file=/x N0=x kernelpagesize_kB=4",
            "garbage line",
            "00400000 default",
            "00400000 default anon=1 dirty=1 kernelpagesize_kB=4",
        ])
        self.assertEqual(vmas, [])

    def test_read_cross_references_maps(self):
        with _patched_read():
            vmas = ne.read_proc_numa_maps()
        self.assertEqual(len(vmas), 5)
        # zipped by index: numa line i -> maps range i
        self.assertEqual(vmas[0]["start"], 0x00400000)
        self.assertEqual(vmas[0]["end"], 0x00402000)
        self.assertEqual(vmas[0]["node_counts"], {"N0": 15})
        self.assertEqual(vmas[2]["start"], 0x7f0000000000)
        self.assertEqual(vmas[2]["end"], 0x7f0040000000)
        self.assertEqual(vmas[2]["node_counts"], {"N1": 4096})

    def test_read_fallback_by_address(self):
        # Kernel omitted one VMA from numa_maps -> lengths differ -> fallback
        numa = NUMA_MAPS_FIXTURE[:3]
        maps = MAPS_FIXTURE
        with mock.patch.object(
            ne.Path, "read_text", side_effect=["\n".join(numa), "\n".join(maps)],
        ):
            vmas = ne.read_proc_numa_maps()
        self.assertEqual(len(vmas), 3)
        self.assertEqual(vmas[2]["start"], 0x7f0000000000)
        self.assertEqual(vmas[2]["end"], 0x7f0040000000)

    def test_counts_for_range(self):
        with _patched_read():
            vmas = ne.read_proc_numa_maps()
        info = ne.numa_counts_for_range(
            vmas, 0x7f0000001000, 0x7f0000100000,
        )
        self.assertEqual(info["coverage_fraction"], 1.0)
        self.assertEqual(info["node_counts"], {"N1": 4096})
        self.assertGreater(info["pages"], 0)

    def test_counts_for_range_partial_overlap(self):
        with _patched_read():
            vmas = ne.read_proc_numa_maps()
        info = ne.numa_counts_for_range(
            vmas, 0x7f0000000000 - 4096, 0x7f0000000000 + 4096,
        )
        self.assertLess(info["coverage_fraction"], 1.0)
        self.assertGreater(info["coverage_fraction"], 0.0)

    def test_counts_for_range_uncovered(self):
        with _patched_read():
            vmas = ne.read_proc_numa_maps()
        info = ne.numa_counts_for_range(vmas, 0x123400000000, 0x123400010000)
        self.assertEqual(info["coverage_fraction"], 0.0)
        self.assertEqual(info["node_counts"], {})


class FakeStorage:
    def __init__(self, addr, nbytes, sid):
        self._addr = addr
        self._nbytes = nbytes
        self._sid = sid
        self.id = sid

    def data_ptr(self):
        return self._addr

    def nbytes(self):
        return self._nbytes


class FakeTensor:
    def __init__(self, addr, nbytes, sid):
        self._st = FakeStorage(addr, nbytes, sid)

    def untyped_storage(self):
        return self._st


class FakeModule:
    def __init__(self, items):
        self._items = items

    def named_parameters(self, recurse=True, remove_duplicate=False):
        return list(self._items)

    def named_buffers(self, recurse=True, remove_duplicate=False):
        return []


class RangeTest(unittest.TestCase):
    def test_merge_ranges(self):
        unet = FakeModule([
            ("w1", FakeTensor(0x1000, 4096, 1)),
            ("w2", FakeTensor(0x1000, 8192, 2)),   # same pages as w1
            ("w3", FakeTensor(0x20000000, 4096, 3)),
            ("w4", FakeTensor(0x20001000, 4096, 4)),  # adjacent -> merged
        ])
        ranges = ne.collect_unet_page_ranges(unet)
        self.assertEqual(ranges, [
            (0x1000, 0x3000),
            (0x20000000, 0x20002000),
        ])

    def test_page_addresses_expansion(self):
        addrs = ne._page_addresses([(0x1000, 0x3000)])
        self.assertEqual(addrs, [0x1000, 0x2000])
        addrs = ne._page_addresses([(0x1000, 0x1000)])
        self.assertEqual(addrs, [])


class FakeRawSyscall:
    """Fake syscall(2): writes statuses into the status array; records calls."""

    def __init__(self, statuses_by_call=None, move_rc=0):
        self.calls = []
        self.statuses_by_call = statuses_by_call or []
        self.move_rc = move_rc

    def __call__(self, name, *args):
        self.calls.append((name, args))
        if name == "move_pages":
            # wrapper passes: (pid, nr_pages, pages, nodes, status, flags)
            status_ptr = args[4]
            arr = ctypes.cast(status_ptr, ctypes.POINTER(ctypes.c_int))
            statuses = [0] * int(args[1].value)
            if self.statuses_by_call:
                statuses = self.statuses_by_call.pop(0)
            for i, s in enumerate(statuses):
                arr[i] = s
            if self.move_rc != 0:
                ctypes.set_errno(-self.move_rc)
            return self.move_rc
        return 0


class MovePagesWrapperTest(unittest.TestCase):
    def test_query_counts_statuses(self):
        fake = FakeRawSyscall(statuses_by_call=[
            [0] * 2 + [-1, -12] + [1] * 3,  # N0,N0,-EPERM,-ENOMEM,N1,N1,N1
        ])
        with mock.patch.object(ne, "_raw_syscall", fake), \
             mock.patch.object(ne.os, "getpid", return_value=42):
            res = ne._move_pages_chunked(
                [0x1000, 0x2000, 0x3000, 0x4000, 0x5000, 0x6000, 0x7000],
                target_node=None,
            )
        self.assertEqual(res["mode"], "query")
        self.assertEqual(res["pages"], 7)
        self.assertEqual(res["calls"], 1)
        self.assertEqual(res["status_counts"], {
            "N0": 2, "errno1": 1, "errno12": 1, "N1": 3,
        })
        self.assertEqual(fake.calls[0][0], "move_pages")
        self.assertEqual(fake.calls[0][1][0].value, 42)  # pid
        self.assertEqual(fake.calls[0][1][5].value, 0)  # flags
        self.assertIsNone(fake.calls[0][1][3])  # nodes ptr

    def test_move_targets_node(self):
        fake = FakeRawSyscall(statuses_by_call=[[0] * 3])
        with mock.patch.object(ne, "_raw_syscall", fake):
            res = ne._move_pages_chunked(
                [0x1000, 0x2000, 0x3000], target_node=1,
            )
        self.assertEqual(res["mode"], "move")
        self.assertEqual(res["target_node"], 1)
        self.assertEqual(fake.calls[0][1][5].value, ne.MPOL_MF_MOVE)
        nodes_ptr = fake.calls[0][1][3]
        nodes_arr = ctypes.cast(nodes_ptr, ctypes.POINTER(ctypes.c_int))
        self.assertEqual([nodes_arr[i] for i in range(3)], [1, 1, 1])
        self.assertEqual(res["status_counts"], {"N0": 3})

    def test_chunking(self):
        fake = FakeRawSyscall(statuses_by_call=[[0] * 100000, [0] * 50000])
        with mock.patch.object(ne, "_raw_syscall", fake):
            res = ne._move_pages_chunked(
                [0x1000 + i * 4096 for i in range(150000)],
                target_node=0,
            )
        self.assertEqual(res["calls"], 2)
        self.assertEqual(res["pages"], 150000)
        self.assertEqual(res["status_counts"], {"N0": 150000})

    def test_syscall_errno_recorded(self):
        fake = FakeRawSyscall(move_rc=-13)
        with mock.patch.object(ne, "_raw_syscall", fake):
            res = ne._move_pages_chunked([0x1000, 0x2000], target_node=0)
        # Indeterminate statuses must NOT be counted on syscall failure.
        self.assertEqual(res["syscall_errno"], [13])
        self.assertEqual(res["status_counts"], {})


class JsonSafeTest(unittest.TestCase):
    def test_flattens_non_json(self):
        rec = {"a": {"b": object()}, "c": [1, 2]}
        out = ne._json_safe(rec)
        self.assertTrue(str(out["a"]["b"]).startswith("<object object at"))
        self.assertEqual(out["c"], [1, 2])


if __name__ == "__main__":
    unittest.main()
