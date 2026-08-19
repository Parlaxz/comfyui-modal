"""Studio-only deterministic release gate for comfyui-modal.

Runs ONLY Studio-owned test suites (History V2, Workflows, Model Library,
Settings, Studio routes/persistence/adapters, canonical run model/controller,
frontend-JS structural tests, fake Playwright) by explicit allowlist.

Deliberately does NOT discover or import unrelated V2/runtime/Modal tests
(that is why it exists -- ``run_tests.py`` discovery sweeps in every
``tests/test_*.py`` including 80+ runtime modules).

Usage (from the repo root):

    python tests/run_studio_tests.py                 # Python + Node unit lanes
    python tests/run_studio_tests.py --fake          # + npm run test:fake (Playwright)
    python tests/run_studio_tests.py --skip-node     # Python lane only
    python tests/run_studio_tests.py --skip-python   # Node lane only

Exit code 0 only when every included lane passes.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("COMFYUI_MODAL_NODE_DIR", str(ROOT / ".experiments"))

# ---------------------------------------------------------------------------
# Explicit allowlist of Studio-owned Python test modules (unittest style).
# Order matters only for the three `tests._test_env` users, kept last-ish.
# ---------------------------------------------------------------------------
STUDIO_PY_MODULES: list[str] = [
    # History V2
    "tests.test_history_v2_api",
    "tests.test_history_v2_migration",
    "tests.test_history_v2_mixed_pagination",
    "tests.test_history_v2_repository",
    "tests.test_history_v2_production_writer",
    # Phase-E deterministic contract scaffolding
    "tests.test_phase_e_contract",
    "tests.test_phase_e_fake_parity",
    "tests.test_phase_e_wave2_contract",
    # Workflows
    "tests.test_workflow_domain",
    "tests.test_workflow_routes",
    "tests.test_workflow_metadata",
    "tests.test_workflow_run_integration",
    # Model Library / dependency resolution
    "tests.test_model_library",
    "tests.test_model_library_routes",
    "tests.test_dependency_resolver",
    # Studio backend / routes / persistence / adapters / frontend structural
    "tests.test_routes_registered",
    "tests.test_studio_backend",
    "tests.test_studio_direct_run",
    "tests.test_studio_history_v2_js",
    "tests.test_studio_progress_tracker",
    "tests.test_studio_runtime",
    "tests.test_studio_timing_integration",
    # Presets
    "tests.test_presets_images",
    "tests.test_presets_prompts",
    # Testing-suite frontend JS (structural)
    "tests.test_testing_profiles_js",
    "tests.test_testing_results_js",
    "tests.test_testing_settings_js",
    "tests.test_testing_setup_js",
    "tests.test_testing_shell_integration",
    "tests.test_testing_ui_wired",
]

# pytest-style module (module-level ``def test_*``, no TestCase classes).
# Wrapped into unittest.FunctionTestCase so the gate stays unittest-based.
PYTEST_STYLE_FILES: list[Path] = [
    ROOT / "tests" / "test_studio_error_contract.py",
]

# Studio-owned standalone Node unit tests (deterministic, no browser).
NODE_UNIT_FILES: list[Path] = [
    ROOT / "tests" / "studio_run_model_unit.mjs",
    ROOT / "tests" / "studio_playground_run_unit.mjs",
    ROOT / "tests" / "studio_workflow_run_unit.mjs",
    ROOT / "tests" / "studio_history_v2_persisted_status_unit.mjs",
    # D5 frontend experiment unit tests
    ROOT / "tests" / "studio_experiment_v2_unit.mjs",
    ROOT / "tests" / "studio_experiment_v2_frontend_unit.mjs",
    ROOT / "tests" / "studio_history_v2_experiment_unit.mjs",
    ROOT / "tests" / "studio_phase_e_contract_unit.mjs",
    ROOT / "tests" / "studio_phase_e_wave2_unit.mjs",
    ROOT / "tests" / "get_axis_eligibility_unit.mjs",
    ROOT / "tests" / "get_steps_recommendation_unit.mjs",
    ROOT / "tests" / "get_seed_insertion_unit.mjs",
    ROOT / "tests" / "browser" / "studio_completion_deterministic.mjs",
]

# Intentionally excluded (documented in STUDIO_TEST_GATE.md):
#   tests.test_studio_live_progress  - intentionally-RED TDD suite
#   tests.test_api_prompt_validator  - bridge-side preflight, not Studio-owned
#   tests/browser/test_frontend_tracker.mjs, studio_live_progress_tracker.mjs,
#   tests/browser/test_queue_prompt_timing.mjs - runtime web/ internals

# TDD classes explicitly named *RED are intentionally-failing placeholders
# ("All tests MUST fail against current production code"). They are not part
# of the release gate; they are skipped and tracked as TDD backlog.
def _is_red_class(cls) -> bool:
    return cls.__name__.endswith("RED")


def _iter_tests(suite_or_test):
    """Yield leaf TestCases from a suite (or single test)."""
    if isinstance(suite_or_test, unittest.TestSuite):
        for item in suite_or_test:
            yield from _iter_tests(item)
    else:
        yield suite_or_test


def build_python_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for name in STUDIO_PY_MODULES:
        loaded = loader.loadTestsFromName(name)
        # Filter out intentionally-RED TDD classes (e.g. the 29 in
        # test_studio_timing_integration) while keeping the rest.
        for test in _iter_tests(loaded):
            test_class = test.__class__
            if _is_red_class(test_class):
                continue
            suite.addTest(test)
    for path in PYTEST_STYLE_FILES:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None and spec.loader is not None, path
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for attr in sorted(dir(mod)):
            if attr.startswith("test_") and callable(getattr(mod, attr)):
                suite.addTest(unittest.FunctionTestCase(getattr(mod, attr)))
    return suite


def run_node_unit(path: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        ["node", str(path)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(ROOT),
    )
    ok = proc.returncode == 0
    tail = (proc.stdout + proc.stderr).strip()
    if len(tail) > 3000:
        tail = tail[-3000:] + "\n[...truncated head...]"
    return ok, tail


def run_fake_playwright() -> tuple[bool, str]:
    # npm is npm.cmd on Windows; shell=True resolves the shim.
    proc = subprocess.run(
        "npm run test:fake",
        capture_output=True,
        text=True,
        timeout=1800,
        cwd=str(ROOT),
        shell=True,
    )
    ok = proc.returncode == 0
    tail = (proc.stdout + proc.stderr).strip()
    if len(tail) > 6000:
        tail = tail[-6000:] + "\n[...truncated head...]"
    return ok, tail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fake", action="store_true", help="also run npm run test:fake")
    parser.add_argument("--skip-python", action="store_true")
    parser.add_argument("--skip-node", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    totals: list[tuple[str, int, int, int, int]] = []  # (lane, run, fail, error, skip)

    if not args.skip_python:
        print("=" * 78)
        print("STUDIO PYTHON LANE")
        print("=" * 78)
        suite = build_python_suite()
        runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1)
        result = runner.run(suite)
        totals.append(("python", result.testsRun, len(result.failures), len(result.errors), len(result.skipped)))
        if not result.wasSuccessful():
            failures.append("python")

    if not args.skip_node:
        print("=" * 78)
        print("STUDIO NODE UNIT LANE")
        print("=" * 78)
        for path in NODE_UNIT_FILES:
            ok, tail = run_node_unit(path)
            print(f"  {'PASS' if ok else 'FAIL'}  {path.name}")
            if not ok:
                failures.append(f"node:{path.name}")
                print(tail)
        totals.append(("node-unit", len(NODE_UNIT_FILES), len(failures) and sum(1 for f in failures if f.startswith("node:")), 0, 0))

    if args.fake:
        print("=" * 78)
        print("FAKE PLAYWRIGHT LANE (npm run test:fake)")
        print("=" * 78)
        ok, tail = run_fake_playwright()
        print("  " + ("PASS" if ok else "FAIL") + "  playwright fake")
        if not ok:
            failures.append("fake-playwright")
            print(tail)
        totals.append(("fake-playwright", 1, 0 if ok else 1, 0, 0))

    print("=" * 78)
    print("STUDIO GATE SUMMARY")
    for lane, run, fail, err, skip in totals:
        print(f"  {lane:<18} run={run:<5} fail={fail:<4} error={err:<4} skip={skip}")
    if failures:
        print("FAILED LANES:", ", ".join(failures))
        return 1
    print("ALL STUDIO LANES GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
