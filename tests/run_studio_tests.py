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
    # F7 Export core + F9 production route/projection integration
    "tests.test_history_v2_export",
    "tests.test_history_v2_export_integration",
    # E3B2 Generate Original replay core + service/routes (production backend)
    "tests.test_history_v2_replay_core",
    "tests.test_history_v2_generate_original",
    "tests.test_history_v2_modern_experiment",
    "tests.test_f1_followup_a_durable_resume",
    # Phase-E deterministic contract scaffolding
    "tests.test_phase_e_contract",
    "tests.test_phase_e_fake_parity",
    "tests.test_phase_e_wave2_contract",
    # E1C logical-output grouping production proof (closes the E5C blocker)
    "tests.test_phase_e_logical_output_integration",
    # E2D Preview encoder method-selection contract (lightweight; no torch)
    "tests.test_e2d_preview_method_contract",
    # Workflows
    "tests.test_workflow_domain",
    "tests.test_workflow_routes",
    "tests.test_workflow_metadata",
    "tests.test_workflow_run_integration",
    # Model Library / dependency resolution
    "tests.test_model_library",
    "tests.test_model_library_routes",
    "tests.test_dependency_resolver",
    # Phase-G portability: G6 risk engine + G9 backend/roundtrip +
    # G11 cache integration (unittest suites).  G7 target rules, G8
    # fixtures and the G10 cache suite are pytest-style modules and are
    # registered in PYTEST_STYLE_FILES below — never list a file twice.
    "tests.test_portability_risk_engine",
    "tests.test_portability_backend",
    "tests.test_portability_roundtrip",
    "tests.test_portability_cache_integration",
    # Studio backend / routes / persistence / adapters / frontend structural
    "tests.test_routes_registered",
    "tests.test_studio_backend",
    "tests.test_studio_direct_run",
    # H20 Wave G registration: V2-only execution contracts (resolver
    # vocabulary collapse, retired-mode rejection, single-V2 dispatch).
    # Patches __init__ lazily like test_studio_direct_run; no stub-server
    # harness, so it tolerates this position.
    "tests.test_phase8_execution_mode",
    "tests.test_studio_history_v2_js",
    "tests.test_studio_progress_tracker",
    # H20 Wave G registration: progress/annotation contracts (renamed from
    # test_task3_progress_annotations; stale scoped-tracker wiring assertions
    # re-pointed at the run-controller owner). Pure structural reads; no
    # ordering constraints.
    "tests.test_studio_progress_annotations",
    "tests.test_studio_runtime",
    "tests.test_studio_timing_integration",
    # F8 GPU authority consolidation (persistence, immutable threading,
    # transport, reset).  Kept AFTER the Workflows block: like
    # test_routes_registered, it loads __init__.py in-process, which the
    # workflow integration suite tolerates only when it ran first.
    "tests.test_f8_gpu_authority",
    # H14 Wave E retirement proofs (loads __init__.py in-process via the
    # test_routes_registered stub-server harness — same ordering constraint).
    "tests.test_h14_wave_e_retirement",
    # H17 Wave F closure: H15 server compatibility/write-freeze proofs (same
    # stub-server harness as H14; builds its own cached __init__ instance).
    # Must stay AFTER the Workflows block and next to H14 for the identical
    # in-process __init__.py loading constraint.
    "tests.test_h15_wave_f_server_freeze",
    # H20 Wave G registration: H12 V2-only consolidation contracts (persisted
    # execution_mode migration matrix, /config retired-engine rejection,
    # comparison-survival audits). ConfigContractTests uses the same
    # stub-server harness as H14/H15 → identical ordering constraint.
    "tests.test_h12_v2_only_consolidation",
    # H20 Wave G registration: `.run_history` store/annotation/save unit
    # authority (H5 §27 registration debt). test_run_history_save builds its
    # own cached stubbed __init__ instance → same after-Workflows placement.
    "tests.test_run_history",
    "tests.test_task2_run_history_extensions",
    "tests.test_run_history_save",
    # H20 Wave G registration: canvas/Studio UI architecture AST contracts
    # (five-page shell reachability, canvas Production mode, protected Single
    # poll seam, versioned persistence). The two historically-stale pins
    # turned GREEN truthfully when H18 deleted the retired UI.
    "tests.test_modal_workspace_ui_ast",
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
    # G5 portability contract freeze (pure; no I/O, no risk computation)
    ROOT / "tests" / "test_portability_contract.py",
    # G7 target readiness rules (pure adapters; module-level test functions)
    ROOT / "tests" / "test_portability_target_rules.py",
    # G8 fixture corpus self-consistency (module-level test functions)
    ROOT / "tests" / "test_portability_fixtures.py",
    # G10 derived report cache (module-level test functions)
    ROOT / "tests" / "test_portability_cache.py",
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
    # E4C Generate Original frontend contract + E4 presentation/settings units
    ROOT / "tests" / "studio_phase_e4c_generate_original_unit.mjs",
    # H20 Wave G registration: E4D Retry Original contract (sibling of e4c;
    # slice-bounded transport pin fixed this lane).
    ROOT / "tests" / "studio_phase_e4d_original_retry_unit.mjs",
    ROOT / "tests" / "studio_phase_e_preview_settings_unit.mjs",
    ROOT / "tests" / "studio_phase_e_history_presentation_unit.mjs",
    # F4A modern Settings authority guard + truthful restart/GPU/reset semantics
    ROOT / "tests" / "studio_phase_f4_settings_authority_unit.mjs",
    # F8 GPU Authority Consolidation — Reset All/Generation server-GPU reset semantics
    ROOT / "tests" / "studio_phase_f8_gpu_reset_unit.mjs",
    # F4C History V2 Grid Columns consumer (normalization + consumption + responsive)
    ROOT / "tests" / "studio_history_v2_grid_columns_unit.mjs",
    # F6 History frontend actions: Single Resume eligibility, truthful Retry
    # naming, replay-capability tolerance, frozen bodyless resume route
    ROOT / "tests" / "studio_phase_f6_history_actions_unit.mjs",
    # F3 History V2 Browser Download helper (MIME/filename contract + invariants)
    ROOT / "tests" / "studio_history_v2_download_unit.mjs",
    ROOT / "tests" / "get_axis_eligibility_unit.mjs",
    ROOT / "tests" / "get_steps_recommendation_unit.mjs",
    ROOT / "tests" / "get_seed_insertion_unit.mjs",
    # H20 Wave G registrations: H6 Backend operations, H7 Model Library
    # parity, and the Settings-compat authority unit (renamed from
    # studio_legacy_settings_authority_unit.mjs after the H18 overlay
    # deletion; MIGRATE-THEN-REGISTER debt resolved).
    ROOT / "tests" / "studio_backend_operations_unit.mjs",
    ROOT / "tests" / "studio_model_library_parity_unit.mjs",
    ROOT / "tests" / "studio_settings_compat_authority_unit.mjs",
    # Setup-wizard bounded draft persistence + explicit-reboot reconnect
    # (queued/download in-flight status survives re-renders).
    ROOT / "tests" / "studio_wizard_draft_reboot_unit.mjs",
    # I2 shell/nav accessibility: semantic nav, aria-current page state,
    # h1 shell heading, _trapTab retirement, responsive overflow valve
    ROOT / "tests" / "studio_phase_i2_shell_nav_accessibility_unit.mjs",
    # I3 shared UI primitives foundation: loading primitive + normalization,
    # chip base/tones/family guards, statusBadge migration, focus-visible
    # fallback, generic copy-free empty state, scope guards
    ROOT / "tests" / "studio_phase_i3_shared_primitives_unit.mjs",
    ROOT / "tests" / "browser" / "studio_completion_deterministic.mjs",
    # I5 lightweight A/B image compare: pure session model (exactly-two-slots,
    # replace-B, single divider authority), descriptor normalization caps,
    # onChange contract, persistence/backend/retirement bans, detail+experiment
    # entry wiring, viewer byte-markers (registered by convergence lane I9A)
    ROOT / "tests" / "studio_phase_i5_image_compare_unit.mjs",
    # I9 hash routing: frozen format parse/serialize fail-soft rules,
    # serialize↔parse round-trip corpus, route-history decision matrix,
    # single shell-owned hashchange listener, alias precedence, page modules
    # routing-free, zero router libraries (registered by convergence lane I9A)
    ROOT / "tests" / "studio_phase_i9_routing_unit.mjs",
    # I10 cross-tab invalidation: one singleton BroadcastChannel, strict
    # four-kind schema, fail-soft delivery, and unsubscribe behavior.
    ROOT / "tests" / "studio_phase_i10_cross_tab_sync_unit.mjs",
]

# Intentionally excluded (documented in STUDIO_TEST_GATE.md):
#   tests.test_api_prompt_validator  - bridge-side preflight, not Studio-owned
#   tests/browser/test_frontend_tracker.mjs, studio_live_progress_tracker.mjs,
#   tests/browser/test_queue_prompt_timing.mjs - runtime web/ internals
#   (tests.test_studio_live_progress was deleted outright by H19 Wave G —
#   its LocalRemoteInvoker stream-sink subject no longer exists)

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
        encoding="utf-8",
        errors="replace",
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
    # UTF-8 + replace: Playwright/spec output may contain non-cp1252 bytes
    # and strict locale decoding would crash the lane with stdout=None.
    proc = subprocess.run(
        "npm run test:fake",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
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
    # Console-safe output: lane tails may contain non-cp1252 characters.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
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
