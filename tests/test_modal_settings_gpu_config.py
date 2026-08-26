import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = REPO_ROOT / "web" / "modal-settings.js"
OUTPUT_PREFS_PATH = REPO_ROOT / "web" / "studio-output-preferences.js"
MODAL_NODE_PATH = REPO_ROOT / "web" / "modal-node.js"


def _code(text: str) -> str:
    """Strip // line comments so documentation may name retired symbols
    while code-level absence is still asserted."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


def _slice(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


class ModalSettingsGpuConfigTests(unittest.TestCase):
    """H18 Wave G: modal-settings.js retains only the read-only GPU init
    loader; the panel dropdown/POST machinery is deleted."""

    def setUp(self) -> None:
        self.source = SETTINGS_PATH.read_text(encoding="utf-8")

    def test_frontend_fetches_config_before_setting_gpu_options(self):
        self.assertIn("available_gpus", self.source)
        self.assertIn("default_gpu", self.source)
        self.assertNotIn("const GPU_OPTIONS = [", self.source)

    def test_dropdown_population_machinery_deleted(self):
        """setGpuOptions served only the retired overlay dropdown."""
        code = _code(self.source)
        self.assertNotIn("setGpuOptions", code)

    def test_explicit_gpu_change_writer_deleted(self):
        """commitGpuSelection/getAcknowledgedGpu were the overlay's only
        GPU POST path; modern Settings owns the writer since F8."""
        code = _code(self.source)
        self.assertNotIn("commitGpuSelection", code)
        self.assertNotIn("getAcknowledgedGpu", code)
        self.assertNotIn('method: "POST"', code)


class ModalSettingsAuthorityAlignmentTests(unittest.TestCase):
    """F4B — legacy Settings authority alignment (structural pins), updated
    for Wave G (H18): only the surviving shared regions are pinned.

    Behavioral proofs live in tests/studio_legacy_settings_authority_unit.mjs.
    """

    def setUp(self) -> None:
        self.source = SETTINGS_PATH.read_text(encoding="utf-8")

    # ── 5. page load performs zero GPU POST ──────────────────────────────
    def test_gpu_initialization_is_read_only(self):
        init_slice = _slice(
            self.source, "async function loadGpuConfig()", "// Build/render lifecycle guard"
        )
        self.assertIn("fetchApi", init_slice)
        self.assertNotIn('method: "POST"', init_slice)

    def test_no_side_effect_gpu_sync_entrypoint_remains(self):
        self.assertNotIn("syncGpuConfig", self.source)
        self.assertNotIn("syncOutputOptions", self.source)

    # ── 8. dead window global removed; output global preserved ───────────
    def test_dead_comfymodalgpu_write_removed(self):
        self.assertNotIn("_comfyModalGpu", self.source)

    def test_output_options_global_owned_by_shared_helper(self):
        helper = OUTPUT_PREFS_PATH.read_text(encoding="utf-8")
        self.assertIn("window._comfyModalOutputOptions =", helper)
        # The legacy panel is gone; nothing in modal-settings writes the global.
        self.assertNotIn("window._comfyModalOutputOptions =", self.source)

    # ── 12. single sync per page load across build/render lifecycle ──────
    def test_sync_guards_setup_only(self):
        self.assertIn("function syncLegacyGpuConfigOnce()", self.source)
        self.assertIn("function syncLegacyOutputPrefsOnce()", self.source)
        # def + setup() bare call each (the buildPanel awaited call is gone).
        total_gpu_refs = self.source.count("syncLegacyGpuConfigOnce()")
        self.assertEqual(total_gpu_refs, 2)
        self.assertEqual(self.source.count("syncLegacyOutputPrefsOnce()"), 2)

    # ── 1/4/6. output settings routed through shared server-first helper ──
    def test_output_preferences_routed_through_shared_helper(self):
        self.assertIn('from "./studio-output-preferences.js"', self.source)
        self.assertIn("syncOutputConfigFromServer", self.source)
        # The panel-only preference widgets/editors are deleted.
        code = _code(self.source)
        for retired in (
            "getOutputPreferences",
            "setOutputPreferences",
            "normalizeOutputSaveFolder",
            "DEFAULT_OUTPUT_SAVEFOLDER",
            "_persistOutputSettings",
            "_renderOutputPrefs",
        ):
            self.assertNotIn(retired, code)

    # ── 10/11. canvas compatibility contracts intact ─────────────────────
    def test_canvas_window_global_reader_structurally_intact(self):
        node_src = MODAL_NODE_PATH.read_text(encoding="utf-8")
        self.assertIn("window._comfyModalOutputOptions", node_src)
        self.assertIn('localStorage.getItem(STORAGE_KEY_OUTPUT_FORMAT)', node_src)

    def test_comparison_reader_deleted_with_module(self):
        """H18 Wave G: modal-comparison.js (and its output-options reader)
        is deleted; no web module may reference it."""
        self.assertFalse((REPO_ROOT / "web" / "modal-comparison.js").exists())
        for path in (REPO_ROOT / "web").glob("*.js"):
            self.assertNotIn(
                "modal-comparison",
                _code(path.read_text(encoding="utf-8")),
                f"{path.name} references the deleted comparison module",
            )


if __name__ == "__main__":
    unittest.main()
