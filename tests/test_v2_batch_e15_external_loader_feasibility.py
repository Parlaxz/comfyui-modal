"""Offline E15 external-loader feasibility tests.

Scope is strictly the *installed* external loader surface as seen by the
existing production staged loader (``comfymodal_runtime.staged_safetensors``):

1. The installed ``safetensors`` public ``safe_open`` surface has no
   pread/mmap backend switch (the ``backend`` parameter only exists in
   safetensors >= 0.8.0; the installed version predates it).  When the
   package is absent the tests skip; when present they assert the surface.
2. The installed ``fastsafetensors`` copier surface exposes
   ``CopierInterface``, ``NoGdsFileCopier`` and ``create_copier_constructor``
   when the package is available, otherwise the tests skip.
3. Importing the existing production staged loader does NOT require any
   optional external package (fastsafetensors / runai-model-streamer /
   instanttensor / modal) — verified with import + module inspection, never
   by executing Modal.
4. A tiny fastsafetensors CPU copy round-trip may run (only when the package
   and torch are available) via a ``TemporaryDirectory`` +
   ``safetensors.torch.save_file``, and proves the loader is closed and the
   buffers cleaned up afterwards.
5. No assumption is made that InstantTensor or RunAI are installed.

Everything here is offline/local: nothing imports ``modal``, deploys, or runs
a container.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import safetensors as _safetensors
    import safetensors.torch as _st_torch

    _HAS_SAFETENSORS = True
    _SAFETENSORS_VERSION = str(getattr(_safetensors, "__version__", "unknown"))
except Exception:  # pragma: no cover - package absent or broken
    _HAS_SAFETENSORS = False
    _SAFETENSORS_VERSION = "unavailable"

try:
    import fastsafetensors as _fs
    from fastsafetensors import copier as _fs_copier

    _HAS_FASTSAFE = True
    _FASTSAFE_VERSION = str(getattr(_fs, "__version__", "unknown"))
except Exception:  # pragma: no cover - package absent or broken
    _HAS_FASTSAFE = False
    _FASTSAFE_VERSION = "unavailable"

try:
    import torch as _torch

    _HAS_TORCH = True
except Exception:  # pragma: no cover - torch absent
    _HAS_TORCH = False

_REQUIRES_SAFETENSORS = unittest.skipUnless(
    _HAS_SAFETENSORS, "safetensors unavailable"
)
_REQUIRES_FASTSAFE = unittest.skipUnless(
    _HAS_FASTSAFE, "fastsafetensors unavailable"
)
_REQUIRES_SMOKE = unittest.skipUnless(
    _HAS_FASTSAFE and _HAS_SAFETENSORS and _HAS_TORCH,
    "fastsafetensors + safetensors + torch required for the CPU smoke test",
)

_EXTERNAL_TOP_LEVELS = (
    "fastsafetensors",
    "runai_model_streamer",
    "instanttensor",
    "modal",
)
_ROOT = Path(__file__).resolve().parents[1]


def _spec_available(name: str) -> bool:
    """Pure find_spec inspection; never imports the package."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


@_REQUIRES_SAFETENSORS
class SafetensorsSurfaceTests(unittest.TestCase):
    """The installed safetensors exposes no pread/mmap (``backend``) switch.

    The ``backend="mmap"|"pread"`` switch only appears in safetensors >= 0.8.0;
    this environment's installed surface predates it, which is exactly the E15
    feasibility finding under test.  If the signature ever grows a ``backend``
    parameter the assertion fails loudly instead of silently assuming it.
    """

    def test_torch_safe_open_signature_has_no_backend_switch(self):
        params = list(inspect.signature(_st_torch.safe_open).parameters)
        self.assertNotIn(
            "backend",
            params,
            f"safetensors {_SAFETENSORS_VERSION} torch.safe_open grew a "
            f"backend (pread/mmap) switch: {params}",
        )

    def test_top_level_safe_open_signature_has_no_backend_switch(self):
        params = list(inspect.signature(_safetensors.safe_open).parameters)
        self.assertNotIn(
            "backend",
            params,
            f"safetensors {_SAFETENSORS_VERSION} safe_open grew a "
            f"backend (pread/mmap) switch: {params}",
        )


@_REQUIRES_FASTSAFE
class FastsafetensorsCopierSurfaceTests(unittest.TestCase):
    """The installed fastsafetensors copier surface (C10 / E15 feasibility)."""

    def test_copier_submodule_exposes_required_symbols(self):
        for name in ("CopierInterface", "NoGdsFileCopier",
                     "create_copier_constructor"):
            symbol = getattr(_fs_copier, name, None)
            self.assertIsNotNone(
                symbol, f"fastsafetensors {_FASTSAFE_VERSION} copier.{name} missing"
            )
            self.assertTrue(
                callable(symbol), f"copier.{name} is not callable"
            )

    def test_nogds_copier_is_a_copier_interface(self):
        self.assertTrue(
            issubclass(_fs_copier.NoGdsFileCopier, _fs_copier.CopierInterface)
        )

    def test_create_copier_constructor_accepts_type_and_device(self):
        params = list(
            inspect.signature(_fs_copier.create_copier_constructor).parameters
        )
        self.assertIn("copier_type", params)
        self.assertIn("device", params)

    def test_top_level_loader_surface_used_by_production(self):
        # Production paths (unet_fastsafetensors / clip_fast_hydration) use
        # SafeTensorsFileLoader + fastsafe_open from the top-level package.
        self.assertTrue(
            callable(getattr(_fs, "SafeTensorsFileLoader", None)),
            "fastsafetensors.SafeTensorsFileLoader missing",
        )
        self.assertTrue(
            callable(getattr(_fs, "fastsafe_open", None)),
            "fastsafetensors.fastsafe_open missing",
        )


class StagedLoaderImportIndependenceTests(unittest.TestCase):
    """Importing the production staged loader must not require externals."""

    @classmethod
    def setUpClass(cls):
        import comfymodal_runtime.staged_safetensors as _staged

        cls.staged = _staged

    def test_module_source_has_no_top_level_external_imports(self):
        source = Path(self.staged.__file__).read_text(encoding="utf-8")
        top_level_imports = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for name in _EXTERNAL_TOP_LEVELS:
            self.assertFalse(
                any(name in line for line in top_level_imports),
                f"staged_safetensors has a top-level import of {name}",
            )

    def test_module_source_mentions_no_external_loader(self):
        source = Path(self.staged.__file__).read_text(encoding="utf-8")
        for name in _EXTERNAL_TOP_LEVELS:
            self.assertNotIn(
                name, source, f"staged_safetensors references {name}"
            )

    def test_module_dict_has_no_external_attributes(self):
        for name in _EXTERNAL_TOP_LEVELS:
            self.assertNotIn(name, self.staged.__dict__)

    def test_exposes_staged_loader_public_surface(self):
        for name in (
            "StagedConfig",
            "StagePlan",
            "StageResult",
            "PreparedStage",
            "plan",
            "prepare",
            "commit",
            "result",
            "fallback",
            "config_from_env",
        ):
            symbol = getattr(self.staged, name, None)
            self.assertIsNotNone(
                symbol, f"staged loader missing {name}"
            )
            self.assertTrue(
                callable(symbol) or isinstance(symbol, type),
                f"staged loader {name} is inert",
            )

    def test_flag_off_plan_needs_no_file_or_external_package(self):
        # Pure env + stdlib path: no file opened, no external import needed.
        config = self.staged.StagedConfig(enabled=False)
        stage_plan = self.staged.plan(
            "does-not-exist.safetensors", config=config
        )
        self.assertEqual(stage_plan.fallback_reason, "flag_off")

    def test_find_spec_of_externals_never_imports_them(self):
        before = {
            name for name in sys.modules
            if name.split(".", 1)[0]
            in ("runai_model_streamer", "instanttensor")
        }
        for name in ("runai_model_streamer", "instanttensor"):
            _spec_available(name)  # record availability only
        after = {
            name for name in sys.modules
            if name.split(".", 1)[0]
            in ("runai_model_streamer", "instanttensor")
        }
        # find_spec is pure inspection: nothing new may appear in sys.modules.
        self.assertEqual(after, before)

    @unittest.skipIf(not sys.executable, "no python executable for subprocess")
    def test_isolated_interpreter_import_requires_no_externals(self):
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(_ROOT)!r})\n"
            "import comfymodal_runtime.staged_safetensors\n"
            "bad = [m for m in sys.modules\n"
            "       if m.split('.', 1)[0] in "
            "('fastsafetensors', 'runai_model_streamer', "
            "'instanttensor', 'modal')]\n"
            "if bad:\n"
            "    print('loaded:', bad)\n"
            "    sys.exit(1)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode,
            0,
            "importing comfymodal_runtime.staged_safetensors pulled external "
            f"packages\nstdout={result.stdout}\nstderr={result.stderr}",
        )


@_REQUIRES_SMOKE
class FastsafetensorsCpuSmokeTests(unittest.TestCase):
    """Tiny fastsafetensors CPU copy round-trip + close cleanup."""

    def test_cpu_copy_round_trip_and_loader_close(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "tiny.safetensors")
            source = {
                "a": _torch.tensor(
                    [1.0, -2.0, 3.5, 8.0], dtype=_torch.float32
                ),
                "b": _torch.arange(6, dtype=_torch.int64),
            }
            _st_torch.save_file(source, path)
            handle = None
            with _fs.fastsafe_open(
                filenames=[path],
                framework="pt",
                device="cpu",
                nogds=True,
                max_copy_block_size=1024,
            ) as handle:
                self.assertEqual(sorted(handle.keys()), sorted(source))
                a = handle.get_tensor("a")
                b = handle.get_tensor("b")
                self.assertEqual(a.device.type, "cpu")
                self.assertEqual(b.device.type, "cpu")
                self.assertEqual(a.dtype, source["a"].dtype)
                self.assertEqual(b.dtype, source["b"].dtype)
                _torch.testing.assert_close(a, source["a"])
                _torch.testing.assert_close(b, source["b"])
            # Correct close cleanup: __exit__ closed both the device buffer
            # and the loader (frames/meta reset, copier constructor dropped).
            self.assertEqual(handle.fb.rank_loaders, {})
            self.assertEqual(handle.loader.frames, {})
            self.assertEqual(handle.loader.meta, {})
            self.assertFalse(hasattr(handle.loader, "copier_constructor"))


if __name__ == "__main__":
    unittest.main()
