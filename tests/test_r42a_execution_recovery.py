"""R42A execution-recovery invariants.

Covers the two new correctness contracts introduced by the R42A continuation:

1. Manifest identity is stat/header-derived (NO full-file SHA on the request
   hot path) and the manifest cache invalidates when source size or mtime
   changes — a same-path byte change must never silently reuse old identity.
2. Real native fallbacks are STICKY: once ``record_real_fallback`` fires for a
   role, a later Golden success may not erase the canonical
   ``golden_qd_fallback:{role}`` degradation.  Provisional strings are still
   removable.
"""

from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comfymodal_runtime import golden_runtime_bridge as grb  # noqa: E402
from comfymodal_runtime.golden.contracts import ModelRole  # noqa: E402


def _write_safetensors(path: Path, tensors: list[tuple[str, str, tuple[int, ...]]]) -> None:
    header: dict = {}
    offset = 0
    for name, dtype, shape in tensors:
        nbytes = 4
        for dim in shape:
            nbytes *= int(dim)
        header[name] = {
            "dtype": dtype,
            "shape": list(shape),
            "data_offsets": [offset, offset + nbytes],
        }
        offset += nbytes
    header_bytes = json.dumps(header).encode("utf-8")
    pad = (8 - (len(header_bytes) % 8)) % 8
    header_bytes += b" " * pad
    with open(path, "wb") as fh:
        fh.write(struct.pack("<Q", len(header_bytes)))
        fh.write(header_bytes)
        fh.write(b"\x00" * offset)


class TestManifestIdentityAndCache(unittest.TestCase):
    def _ctx(self) -> "grb.GoldenRunContext":
        return grb.GoldenRunContext(join_timeout_s=5.0)

    def test_no_full_sha_and_cache_hit(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "m.safetensors"
            _write_safetensors(path, [("w", "F32", (8, 8))])
            ctx = self._ctx()
            m1 = ctx.build_manifest(str(path), ModelRole.VAE)
            # Identity must be stat/header derived: identical rebuild returns
            # the SAME cached object without re-reading model bytes.
            m2 = ctx.build_manifest(str(path), ModelRole.VAE)
            self.assertIs(m1, m2)
            self.assertEqual(m1.extra.get("identity_kind"), "stat_header_snapshot")
            self.assertNotEqual(m1.file_sha256, "")

    def test_cache_invalidates_on_mtime_change(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "m.safetensors"
            _write_safetensors(path, [("w", "F32", (8, 8))])
            ctx = self._ctx()
            m1 = ctx.build_manifest(str(path), ModelRole.CLIP)
            st = os.stat(path)
            future = int(getattr(st, "st_mtime_ns")) + 10_000_000
            os.utime(path, ns=(st.st_atime_ns, future))
            m2 = ctx.build_manifest(str(path), ModelRole.CLIP)
            self.assertIsNot(m1, m2)
            self.assertNotEqual(m1.identity_hash, m2.identity_hash)

    def test_realpath_key_lookup(self):
        with tempfile.TemporaryDirectory() as td:
            real = str(Path(td).resolve() / "vae.safetensors")
            _write_safetensors(Path(real), [("dec.w", "F32", (4, 4))])
            tricky = str(Path(td) / "sub" / ".." / "vae.safetensors")
            self.assertNotEqual(tricky, os.path.realpath(tricky))
            ctx = self._ctx()
            built = ctx.build_manifest(tricky, ModelRole.VAE)
            ctx.note_role_source("vae", tricky)
            self.assertIs(ctx._manifest_for("vae"), built)


class TestStickyRealFallback(unittest.TestCase):
    def test_real_fallback_survives_clear(self):
        ctx = grb.GoldenRunContext(join_timeout_s=5.0)
        ctx.record_real_fallback("vae", "schedule_denied")
        self.assertIn("golden_qd_fallback:vae", ctx.degradations)
        slot = ctx._role_lifecycle["vae"]
        self.assertTrue(slot["fallback"])
        self.assertEqual(slot["fallback_reason"], "schedule_denied")
        # A later Golden success clears provisional strings but must keep the
        # canonical real-fallback degradation visible.
        ctx.add_degradation("golden_owner_join_timeout:vae")
        ctx.clear_role_fallback_degradations("vae")
        self.assertIn("golden_qd_fallback:vae", ctx.degradations)
        self.assertNotIn("golden_owner_join_timeout:vae", ctx.degradations)

    def test_provisional_only_is_fully_clearable(self):
        ctx = grb.GoldenRunContext(join_timeout_s=5.0)
        ctx.add_degradation("golden_owner_join_timeout:vae")
        ctx.clear_role_fallback_degradations("vae")
        self.assertNotIn("golden_owner_join_timeout:vae", ctx.degradations)
        self.assertFalse(ctx._role_lifecycle["vae"]["fallback"])


if __name__ == "__main__":
    unittest.main()
