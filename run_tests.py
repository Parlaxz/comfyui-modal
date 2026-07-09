"""Run the comfyui-modal test suite with the right sys.path.

The embedded Python distribution on Windows ignores PYTHONPATH. This wrapper
inserts its own directory (the custom-node root) into sys.path so that
``import experiment_service``, ``import worker_control``, etc. resolve.

Usage:
    python run_tests.py                          # run all tests
    python run_tests.py tests.test_workstream_e  # run one module
    python run_tests.py tests.test_x tests.test_y
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Some tests (and the modules under test) read these env vars. Default them
# to a tmp dir so they don't pollute the workspace.
os.environ.setdefault("COMFYUI_MODAL_NODE_DIR", str(ROOT / ".experiments"))


def main() -> int:
    args = sys.argv[1:]
    if not args:
        loader = unittest.TestLoader()
        suite = loader.discover(start_dir=str(ROOT / "tests"), pattern="test_*.py")
        runner = unittest.TextTestRunner(verbosity=1)
        result = runner.run(suite)
        return 0 if result.wasSuccessful() else 1
    # Explicit module list — replicate `python -m unittest` semantics
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in args:
        suite.addTests(loader.loadTestsFromName(name))
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
