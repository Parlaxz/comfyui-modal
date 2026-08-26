"""Phase H14 — Wave E: Legacy Settings & Comparison product retirement proofs.

Frozen authority:
  - PHASE_H5C_WAVES_CD_CONVERGENCE_WAVE_E_FREEZE_2026-08-24.md (§9/§13–§20)
  - PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md

What this suite proves, per the H14 batch contract:
  1. Settings ▸ Advanced ▸ Legacy group is gone; modern sections remain.
  2. The standalone legacy overlay cannot open; its globals are retired;
     the canvas comfymodal_enabled compatibility shim is present with the
     frozen precedence (H5C §15-B).
   3. No legacy tab is mountable from the Studio shell; Wave G (H18)
      deleted the retired loader and testing-* module files.
   4. Comparison UI/overlays/canvas menu are retired; the inert
      modal-comparison.js residue module was deleted in Wave G.
  5. POST /comfymodal/comparison/run cannot execute: bounded truthful
     retired response, zero executor invocation, zero manifest write,
     stored data byte-identical. READ_COMPAT routes still answer.
  6. Transitional modern Single seams (GET /experiments/{id},
     POST .../stop-now) survive untouched.
  7. Warmup is untouched (Wave F/G destination) and is the sole remaining
     direct run_prompt_stream caller in __init__.py.

Read-only against production data; no network, no Modal, no GPU.
"""
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"
NODE_DIR = REPO_ROOT

sys.path.insert(0, str(REPO_ROOT))

from tests.test_routes_registered import (  # noqa: E402
    _MockRequest,
    _StubServer,
    _build_init_with_stub,
    _handler_for,
    _run,
)


def _code(text: str) -> str:
    """Strip // line comments so documentation may name retired symbols
    while code-level absence is still asserted."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


def _read_web(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1+2. Settings Legacy group + standalone overlay absence
# ---------------------------------------------------------------------------


class SettingsLegacyGroupAbsenceTests(unittest.TestCase):
    def test_no_legacy_group_or_entries(self):
        text = _read_web("studio-settings.js")
        code = _code(text)
        for retired in [
            "Legacy Setup",
            "Legacy Profiles",
            "Legacy Results",
            "Legacy Settings",
            "Open Legacy Settings",
            "settings-legacy-open",
            "settings-legacy-setup",
            "settings-legacy-profiles",
            "settings-legacy-results",
            "settings-legacy-settings",
        ]:
            self.assertNotIn(retired, code)

    def test_modern_preference_sections_remain(self):
        text = _read_web("studio-settings.js")
        for section in ["general", "generation", "outputs", "history", "interface", "advanced"]:
            self.assertIn(section, text)
        self.assertIn("settings-reset-all", text)
        self.assertIn("settings-open-backend", text)

    def test_settings_has_no_legacy_mount_path(self):
        code = _code(_read_web("studio-settings.js"))
        for retired in ["mountLegacyTab", "renderLegacyView", "activeLegacyTab"]:
            self.assertNotIn(retired, code)


class LegacyOverlayAbsenceTests(unittest.TestCase):
    def test_overlay_globals_retired(self):
        code = _code(_read_web("modal-settings.js"))
        for retired in [
            "open_comfymodal_settings",
            "mountSettingsPanel",
            "comfymodal-settings-overlay",
        ]:
            self.assertNotIn(retired, code)

    def test_canvas_compatibility_shim_present_with_frozen_precedence(self):
        """H5C §15-B: startup reads persisted comfymodal_enabled into
        window._comfyModalEnabled; absent key → enabled (cloud)."""
        text = _read_web("modal-settings.js")
        self.assertIn('const STORAGE_KEY_ENABLED = "comfymodal_enabled"', text)
        self.assertIn(
            'window._comfyModalEnabled = savedEnabled === null ? true : savedEnabled === "true";',
            text,
        )
        # Shared init regions preserved (H5C §15-C/D)
        self.assertIn("syncLegacyGpuConfigOnce();", text)
        self.assertIn("syncLegacyOutputPrefsOnce();", text)
        self.assertIn('from "./studio-output-preferences.js"', text)

    def test_canvas_readers_unchanged(self):
        node_src = _read_web("modal-node.js")
        self.assertEqual(node_src.count("window._comfyModalEnabled !== false"), 2)
        # /prompt interception remains
        self.assertIn('route === "/prompt" || route === "prompt"', node_src)
        # Production mode remains
        self.assertIn("production_mode_enabled", node_src)
        # Output options reader remains
        self.assertIn("window._comfyModalOutputOptions", node_src)


# ---------------------------------------------------------------------------
# 3. Studio legacy mount surface retirement
# ---------------------------------------------------------------------------


class LegacyMountSurfaceRetirementTests(unittest.TestCase):
    def test_shell_registers_five_modern_pages_only(self):
        text = _read_web("studio-shell.js")
        for page in ["playground", "history", "workflows", "backend", "settings"]:
            self.assertIn(page, text)
        code = _code(text)
        for retired in ["mountLegacyTab", "setSettingsLegacyTab", "activeLegacyTab", "stopLegacyController"]:
            self.assertNotIn(retired, code)

    def test_modal_testing_has_no_lazy_tab_machinery(self):
        code = _code(_read_web("modal-testing.js"))
        for retired in [
            "TAB_MODULES",
            "mountLazyTab",
            "./testing-setup.js",
            "./testing-profiles.js",
            "./testing-results.js",
            "./testing-settings.js",
            "mountLegacyTab",
            "stopLegacyController",
        ]:
            self.assertNotIn(retired, code)

    def test_no_production_importer_of_studio_legacy(self):
        """studio-legacy.js is deleted (Wave G); nothing in production may
        import or reference it."""
        importers = []
        for path in WEB.glob("*.js"):
            if 'from "./studio-legacy.js"' in path.read_text(encoding="utf-8"):
                importers.append(path.name)
        self.assertEqual(importers, [], f"Unexpected studio-legacy.js importers: {importers}")
        self.assertFalse((WEB / "studio-legacy.js").exists())

    def test_alias_map_and_sidebar_preserved(self):
        text = _read_web("modal-testing.js")
        for alias in [
            'playground: "playground"',
            'dashboard: "backend"',
            'setup: "playground"',
            'profiles: "playground"',
            'results: "history"',
            'history: "history"',
            'settings: "settings"',
        ]:
            self.assertIn(alias, text)
        self.assertIn("registerSidebarTab", text)
        self.assertIn("comfymodal-testing-suite", text)
        self.assertIn("window.open_testing_modal = open_testing_modal", text)

    def test_testing_modules_unreachable_from_production_entrypoints(self):
        entrypoints = [
            "modal-testing.js",
            "studio-shell.js",
            "studio-settings.js",
            "studio-playground.js",
            "studio-backend.js",
            "studio-workflows.js",
            "studio-history-v2.js",
        ]
        targets = ["testing-setup.js", "testing-profiles.js", "testing-results.js", "testing-settings.js"]
        for ep in entrypoints:
            text = _read_web(ep)
            for t in targets:
                self.assertNotIn(t, text, f"{ep} must not reference {t}")


# ---------------------------------------------------------------------------
# 4. Comparison UI / overlays / canvas menu retirement
# ---------------------------------------------------------------------------


class ComparisonUiRetirementTests(unittest.TestCase):
    def test_comparison_module_is_deleted(self):
        """Wave G deleted the inert auto-loaded module outright: it had no
        extension registration, no globals, and no required side effects."""
        self.assertFalse(
            (WEB / "modal-comparison.js").exists(),
            "web/modal-comparison.js must stay deleted (Wave G)",
        )

    def test_comparison_globals_unreferenced_across_web(self):
        for glob in [
            "openComparisonProfilesOverlay",
            "openComparisonRunnerOverlay",
            "mountComparisonProfiles",
            "mountComparisonRunner",
        ]:
            hits = [
                p.name for p in WEB.glob("*.js")
                if glob in _code(p.read_text(encoding="utf-8"))
            ]
            self.assertEqual(hits, [], f"{glob} must have zero web references")

    def test_ab_slider_not_mounted_by_production(self):
        """The legacy A/B slider retires with Comparison UI (Phase I owns any
        future compare experience); the module file is deleted."""
        self.assertFalse((WEB / "testing-ab-slider.js").exists())
        for ep in ["modal-testing.js", "studio-shell.js", "studio-playground.js", "studio-history-v2.js"]:
            self.assertNotIn("testing-ab-slider", _read_web(ep))

    def test_no_reachable_frontend_caller_of_comparison_run(self):
        """No production-reachable frontend caller of /comparison/run may
        remain anywhere in web/ (the old Runner POST lived only in the
        deleted modal-comparison.js residue)."""
        hits = []
        for path in WEB.glob("*.js"):
            if "/comparison/run" in _code(path.read_text(encoding="utf-8")):
                hits.append(path.name)
        self.assertEqual(hits, [], f"Reachable frontend callers of /comparison/run remain: {hits}")


# ---------------------------------------------------------------------------
# 5. POST /comparison/run execution retirement (route-level)
# ---------------------------------------------------------------------------


class _InitHarnessMixin:
    @classmethod
    def build_init(cls):
        cls.stub = _StubServer()
        cls.init_mod = _build_init_with_stub(cls.stub)


class ComparisonRunRetirementTests(_InitHarnessMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_init()

    def _call_run(self, body=None):
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/comparison/run")
        self.assertIsNotNone(fn, "retired route must stay registered")
        req = _MockRequest(json_body=body if body is not None else {
            "profile_ids": ["p1"], "prompt": "x", "seed": 0,
        })
        return _run(fn(req))

    def test_returns_bounded_retired_response(self):
        resp = self._call_run()
        self.assertEqual(resp.status, 410)
        body = json.loads(resp.body)
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error_code"], "COMPARISON_RETIRED")
        self.assertIn("retired", body["message"].lower())

    def test_zero_executor_invocation_and_zero_manifest_write(self):
        """H19 update: __init__.py no longer even imports the retired
        executor/manifest symbols, so the tripwires patch the SOURCE
        modules (modal_client / comparison) instead."""
        calls = {"stream": 0, "manifest_build": 0, "manifest_save": 0}

        def _no_stream(*a, **k):
            calls["stream"] += 1
            raise AssertionError("run_prompt_stream must not be invoked by the retired endpoint")
            yield  # pragma: no cover

        def _no_run_comparison(*a, **k):
            calls["manifest_build"] += 1
            raise AssertionError("run_comparison must not be invoked by the retired endpoint")

        def _no_save_manifest(*a, **k):
            calls["manifest_save"] += 1
            raise AssertionError("save_comparison_manifest must not be invoked by the retired endpoint")

        src = (NODE_DIR / "__init__.py").read_text(encoding="utf-8")
        # H19 Wave G: the retired imports are gone from __init__.py entirely.
        # (Only import bindings count; docstring prose is exempt.)
        self.assertNotIn(" run_comparison,\n", src)
        self.assertNotIn(" save_comparison_manifest,\n", src)
        self.assertNotIn(" save_comparison_result,\n", src)
        mc_import = re.search(r"from modal_client import ([^\n]*)", src)
        self.assertIsNotNone(mc_import)
        self.assertNotIn("run_prompt_stream", mc_import.group(1))

        with patch("modal_client.run_prompt_stream", _no_stream), \
             patch("comparison.run_comparison", _no_run_comparison), \
             patch("comparison.save_comparison_manifest", _no_save_manifest):
            resp = self._call_run({
                "profile_ids": ["p1", "p2"], "prompt": "exec should not happen",
                "execution_mode": "parallel", "max_parallel_jobs": 4,
            })
        self.assertEqual(resp.status, 410)
        self.assertEqual(calls, {"stream": 0, "manifest_build": 0, "manifest_save": 0})

    def test_retired_endpoint_writes_nothing_to_stored_profiles(self):
        """Byte-integrity: profiles stored before the call are byte-identical
        after it (H14 §19)."""
        import comparison

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow_api = {
                "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "u1"}},
                "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "c1"}},
                "3": {"class_type": "VAELoader", "inputs": {"vae_name": "v1"}},
                "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}},
            }
            comparison.create_profile(comfyui_root=str(root), name="KeepMe", workflow_api=workflow_api)

            def snapshot():
                out = {}
                for p in sorted(root.rglob("*")):
                    if p.is_file():
                        out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
                return out

            before = snapshot()
            original_root = self.init_mod._COMFYUI_ROOT
            self.init_mod._COMFYUI_ROOT = str(root)
            try:
                resp = self._call_run({"profile_ids": ["keepme"], "prompt": "nope"})
            finally:
                self.init_mod._COMFYUI_ROOT = original_root
            self.assertEqual(resp.status, 410)
            self.assertEqual(snapshot(), before, "stored Comparison data must be byte-identical")

    def test_read_compat_profile_list_still_answers(self):
        """READ_COMPAT survives: stored profiles remain readable (H5C §9/§10)."""
        import comparison

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow_api = {
                "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "u1"}},
                "2": {"class_type": "DualCLIPLoader", "inputs": {"clip_name1": "c1"}},
                "3": {"class_type": "VAELoader", "inputs": {"vae_name": "v1"}},
                "10": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}},
            }
            created = comparison.create_profile(comfyui_root=str(root), name="Reader", workflow_api=workflow_api)
            original_root = self.init_mod._COMFYUI_ROOT
            self.init_mod._COMFYUI_ROOT = str(root)
            try:
                fn = _handler_for(self.init_mod, "GET", "/comfymodal/comparison/profiles")
                resp = _run(fn(_MockRequest()))
            finally:
                self.init_mod._COMFYUI_ROOT = original_root
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.body)
            self.assertEqual(body["status"], "ok")
            ids = [p["id"] for p in body.get("profiles", [])]
            self.assertIn(created["id"], ids)

    def test_all_seventeen_comparison_routes_still_registered(self):
        """Wave E removes no route; Wave F owns mutation freezing."""
        expected = {
            ("GET", "/comfymodal/comparison/profiles"),
            ("POST", "/comfymodal/comparison/profiles"),
            ("GET", "/comfymodal/comparison/profiles/{profile_id}"),
            ("PUT", "/comfymodal/comparison/profiles/{profile_id}"),
            ("DELETE", "/comfymodal/comparison/profiles/{profile_id}"),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/duplicate"),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/validate"),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/detect-slots"),
            ("POST", "/comfymodal/comparison/profiles/{profile_id}/slots"),
            ("POST", "/comfymodal/comparison/run"),
            ("GET", "/comfymodal/comparison/results"),
            ("GET", "/comfymodal/comparison/results/{comparison_id}"),
            ("GET", "/comfymodal/comparison/profiles/{profile_id}/workflow/nodes"),
            ("GET", "/comfymodal/comparison/profiles/{profile_id}/workflow"),
            ("GET", "/comfymodal/comparison/config"),
            ("POST", "/comfymodal/comparison/config"),
            ("GET", "/comfymodal/comparison/gallery/{comparison_id}"),
        }
        registered = {(m, p) for m, p, _ in self.stub.routes._handlers if "/comparison" in p}
        self.assertTrue(expected.issubset(registered),
                        f"missing comparison routes: {sorted(expected - registered)}")


# ---------------------------------------------------------------------------
# 6. Transitional modern Single seams protected (H5C §5)
# ---------------------------------------------------------------------------


class TransitionalSingleSeamTests(_InitHarnessMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_init()

    def test_detail_get_route_protected(self):
        fn = _handler_for(self.init_mod, "GET", "/comfymodal/experiments/{experiment_id}")
        self.assertIsNotNone(fn, "GET /experiments/{id} must remain registered")
        resp = _run(fn(_MockRequest(match_info={"experiment_id": "no_such_exp_h14"})))
        self.assertEqual(resp.status, 404)

    def test_stop_now_route_protected(self):
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/experiments/{experiment_id}/stop-now")
        self.assertIsNotNone(fn, "POST .../stop-now must remain registered")
        resp = _run(fn(_MockRequest(match_info={"experiment_id": "no_such_exp_h14"})))
        self.assertEqual(resp.status, 404)

    def test_single_poll_cancel_frontends_still_wired(self):
        api_src = _read_web("studio-backend-api.js")
        self.assertIn("export async function getStudioRunStatus", api_src)
        self.assertIn("`/experiments/${encodeURIComponent(id)}`", api_src)
        self.assertIn("/stop-now", api_src)
        pg_src = _read_web("studio-playground.js")
        self.assertIn("getStudioRunStatus(apiBase, experimentId)", pg_src)
        self.assertIn("await stopExperiment(apiBase, _eid)", pg_src)


# ---------------------------------------------------------------------------
# 7. Warmup untouched + run_prompt_stream caller census
# ---------------------------------------------------------------------------


class WarmupUntouchedTests(_InitHarnessMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_init()

    def test_warmup_route_still_registered(self):
        fn = _handler_for(self.init_mod, "POST", "/comfymodal/deploy-warmup/run")
        self.assertIsNotNone(fn, "warmup route must be untouched by Wave E")

    def test_warmup_is_sole_reachable_direct_stream_caller_in_init(self):
        """Census updated by Phase H19 (Wave G): the warmup route's direct
        stream call was retired by Wave F and the dead Comparison residue
        body was deleted, so ZERO textual direct calls remain in
        __init__.py. The shared transport lives in modal_client/ModalTransport."""
        src = (NODE_DIR / "__init__.py").read_text(encoding="utf-8")
        direct_calls = re.findall(r"async for (\w+) in run_prompt_stream\(", src)
        self.assertEqual(
            sorted(direct_calls), [],
            "expected zero direct stream calls in __init__.py after H19 "
            "deleted the Comparison residue — anything else is unaccounted drift",
        )
        # The retired route handler itself must not reach the executor.
        handler_start = src.index('async def comparison_run(')
        handler_end = src.index("@_server.routes.get", handler_start)
        self.assertNotIn("run_prompt_stream", src[handler_start:handler_end])
        # H19: the residue helper is fully deleted from __init__.py.
        self.assertNotIn("_execute_comparison_profile", src)

    def test_shared_transport_not_deleted(self):
        mc_src = (NODE_DIR / "modal_client.py").read_text(encoding="utf-8")
        self.assertIn("async def run_prompt_stream(", mc_src)
        # V2 transport still streams through the same remote method
        mt_src = (NODE_DIR / "comfymodal_runtime" / "modal_transport.py").read_text(encoding="utf-8")
        self.assertIn("run_prompt_stream", mt_src)


# ---------------------------------------------------------------------------
# 8. Wave G (H18) — dead frontend files genuinely absent/unreachable
# ---------------------------------------------------------------------------


class WaveGDeadFrontendFileContractTests(unittest.TestCase):
    """H18 Wave G: every retired frontend module is deleted, no production
    code references its filename, and no product registry/loader can reach
    it. Deliberately avoids large source snapshots — absence is the contract."""

    RETIRED_FILES = [
        "testing-setup.js",
        "testing-profiles.js",
        "testing-results.js",
        "testing-settings.js",
        "testing-ab-slider.js",
        "testing-setup-adapter.js",
        "testing-api.js",
        "studio-legacy.js",
        "modal-comparison.js",
    ]

    def test_retired_files_do_not_exist(self):
        for name in self.RETIRED_FILES:
            with self.subTest(name=name):
                self.assertFalse((WEB / name).exists(), f"web/{name} must stay deleted")

    def test_no_importer_references_retired_filenames(self):
        """No web/*.js code (comments excluded) may reference any retired
        filename — no static import, dynamic import, or loader map entry."""
        for path in WEB.glob("*.js"):
            code = _code(path.read_text(encoding="utf-8"))
            for name in self.RETIRED_FILES:
                with self.subTest(file=path.name, retired=name):
                    self.assertNotIn(name, code)

    def test_no_legacy_ui_reachability(self):
        """No route back to legacy Setup/Profiles/Results/Settings/Comparison:
        aliases land on modern owners; no legacy mount machinery remains."""
        text = _read_web("modal-testing.js")
        code = _code(text)
        for alias in [
            'setup: "playground"',
            'profiles: "playground"',
            'results: "history"',
            'history: "history"',
            'settings: "settings"',
            'dashboard: "backend"',
        ]:
            self.assertIn(alias, text)
        for retired in [
            "mountLegacyTab", "activeLegacyTab", "LEGACY_MODULES", "TAB_MODULES",
            "mountLazyTab", "_draftState", "_previewState",
            "comfymodal_setup_draft", "comfymodal_last_experiment_id",
        ]:
            self.assertNotIn(retired, code)

    def test_modal_settings_is_minimal_canvas_compat_module(self):
        """The overlay body is gone; only the canvas/shared compatibility
        surface survives (shim + syncs + redeploy banner)."""
        text = _read_web("modal-settings.js")
        code = _code(text)
        for retired in [
            "buildPanel", "buildAuthPanel", "loadModels", "renderModelList",
            "startDeployPoll", "pollDeployStatus", "checkHealth",
            "createCollapsibleSection", "showConfirmDialog",
            "STORAGE_KEY_PRODUCTION", "DOWNLOAD_FOLDERS",
        ]:
            self.assertNotIn(retired, code)
        # Surviving regions (H5C §15-B/C/D)
        self.assertIn('const STORAGE_KEY_ENABLED = "comfymodal_enabled"', text)
        self.assertIn("syncLegacyGpuConfigOnce();", text)
        self.assertIn("syncLegacyOutputPrefsOnce();", text)
        self.assertIn('from "./studio-output-preferences.js"', text)


if __name__ == "__main__":
    unittest.main()
