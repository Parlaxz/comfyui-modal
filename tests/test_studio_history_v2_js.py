"""History V2 headless logic module structural tests.

Verifies the public APIs and key surface area of the new headless modules:
- web/history-v2-repository.js  (adapter interface + legacy bridge + normalizer)
- web/history-v2-fixtures.js    (deterministic fixture dataset + repository)
- web/history-v2-view-state.js  (localStorage view-state persistence)
"""
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "web"


class _JsModule:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.text = path.read_text(encoding="utf-8") if path.exists() else ""

    def has_export(self, name: str) -> bool:
        return bool(re.search(rf"export\s+(?:function|const|class)\s+{re.escape(name)}\b", self.text))

    def has_function(self, name: str) -> bool:
        return bool(re.search(rf"function\s+{re.escape(name)}\s*\(", self.text))

    def contains(self, s: str) -> bool:
        return s in self.text


def _assert_no_framework_imports(test_case, module) -> None:
    for forbidden in ("from 'react'", 'from "react"', "from 'preact'",
                      "from 'vue'", "from 'svelte'"):
        with test_case.subTest(forbidden=forbidden):
            test_case.assertNotIn(forbidden, module.text)


class HistoryV2ModulesExistTests(unittest.TestCase):
    """All three web modules must exist on disk."""

    def test_all_three_web_modules_exist(self):
        for name in (
            "history-v2-repository.js",
            "history-v2-fixtures.js",
            "history-v2-view-state.js",
        ):
            with self.subTest(name=name):
                self.assertTrue((WEB / name).exists(), f"web/{name} missing")


class HistoryV2RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _JsModule(WEB / "history-v2-repository.js")
        if not self.m.text:
            self.skipTest("web/history-v2-repository.js missing")

    def test_exports(self):
        for name in ("createHistoryRepository", "normalizeFeedItem", "normalizeStatuses", "HISTORY_V2_MODES"):
            with self.subTest(export=name):
                self.assertTrue(self.m.has_export(name))

    def test_modes_include_fixture_and_bridge(self):
        self.assertIn('"fixture"', self.m.text)
        self.assertIn('"bridge"', self.m.text)

    def test_canonical_statuses_are_wire_values(self):
        self.assertIn('GENERATION_STATUSES = ["completed"', self.m.text)
        self.assertIn('"completed_with_failures"', self.m.text)

    def test_status_aliases_map_to_canonical(self):
        self.assertIn('"success": "completed"', self.m.text)
        self.assertIn('"partial": "completed_with_failures"', self.m.text)
        self.assertIn('"cancelled": "canceled"', self.m.text)
        self.assertIn('"aborted": "interrupted"', self.m.text)

    def test_uses_abort_controller(self):
        self.assertIn("AbortController", self.m.text)

    def test_auto_probe_timeout(self):
        self.assertIn("1500", self.m.text)
        self.assertIn("page=1", self.m.text)
        self.assertIn("page_size=1", self.m.text)

    def test_repository_contract_methods(self):
        for name in (
            "listFeed", "getGeneration", "getExperiment", "setFavorite", "setNote",
            "setFeaturedOutput", "retryExperiment", "generateOriginal",
            "generateOriginalForCell", "listFacets",
        ):
            with self.subTest(method=name):
                self.assertIn(name, self.m.text)

    def test_bridge_maps_legacy_sort(self):
        self.assertIn('"preset_az"', self.m.text)
        self.assertIn('"preset_za"', self.m.text)

    def test_bridge_uses_legacy_endpoints(self):
        self.assertIn('"/run-history/"', self.m.text)
        self.assertIn('"/history?"', self.m.text)
        self.assertIn("annotations", self.m.text)

    def test_bridge_cursor_derives_page(self):
        self.assertIn("offset:", self.m.text)

    def test_legacy_preview_filters_are_client_side(self):
        self.assertIn("previewOnly", self.m.text)
        self.assertIn("originalAvailable", self.m.text)

    def test_not_available_method_message(self):
        self.assertIn("History V2 repository method not available", self.m.text)

    def test_get_mode_info(self):
        self.assertIn("getModeInfo", self.m.text)

    def test_normalize_status_aliases(self):
        self.assertIn("canceled", self.m.text)
        self.assertIn("interrupted", self.m.text)

    def test_no_inner_html(self):
        self.assertNotIn("innerHTML", self.m.text)

    def test_no_framework_imports(self):
        _assert_no_framework_imports(self, self.m)


class HistoryV2FixturesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _JsModule(WEB / "history-v2-fixtures.js")
        if not self.m.text:
            self.skipTest("web/history-v2-fixtures.js missing")

    def test_exports(self):
        for name in ("buildFixtureDataset", "createFixtureRepository", "makeSvgThumbUri"):
            with self.subTest(export=name):
                self.assertTrue(self.m.has_export(name))

    def test_fixed_base_timestamp(self):
        self.assertIn("2026-08-10", self.m.text)

    def test_generation_id_prefixes(self):
        self.assertIn('"gen_00', self.m.text)

    def test_experiment_id_prefixes(self):
        self.assertIn('"exp_00', self.m.text)

    def test_original_failed_marker(self):
        self.assertIn("originalFailed", self.m.text)

    def test_cover_padded_to_4(self):
        self.assertIn("cover.length < 4", self.m.text)

    def test_cover_slice_first_four(self):
        self.assertIn("slice(0, 4)", self.m.text)

    def test_status_distribution_present(self):
        text = self.m.text
        for status in ("success", "interrupted", "failed", "canceled", "running"):
            with self.subTest(status=status):
                self.assertIn('"' + status + '"', text)

    def test_dataset_counts_markers(self):
        # Multi-output gens, preview-only gens, no-image gen
        text = self.m.text
        self.assertIn('"gen_003"', text)
        self.assertIn('"gen_007"', text)
        self.assertIn('"gen_012"', text)
        self.assertIn('"gen_005"', text)
        self.assertIn('"gen_014"', text)
        self.assertIn('"gen_018"', text)
        self.assertIn('"gen_022"', text)

    def test_experiment_counts_markers(self):
        text = self.m.text
        for exp_id in ("exp_001", "exp_002", "exp_003", "exp_004", "exp_005", "exp_006", "exp_007"):
            with self.subTest(exp_id=exp_id):
                self.assertIn('"' + exp_id + '"', text)

    def test_axis_labels_marker(self):
        self.assertIn("axis_labels", self.m.text)

    def test_no_random_or_date_now(self):
        self.assertNotIn("Math.random", self.m.text)
        self.assertNotIn("Date.now", self.m.text)

    def test_svg_data_uri(self):
        self.assertIn("data:image/svg+xml;utf8,", self.m.text)

    def test_no_inner_html(self):
        self.assertNotIn("innerHTML", self.m.text)

    def test_no_framework_imports(self):
        _assert_no_framework_imports(self, self.m)


class HistoryV2ViewStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _JsModule(WEB / "history-v2-view-state.js")
        if not self.m.text:
            self.skipTest("web/history-v2-view-state.js missing")

    def test_exports(self):
        for name in (
            "loadHistoryViewState", "saveHistoryViewState", "normalizeViewState",
            "STORAGE_KEY", "DEFAULT_HIDDEN_STATUSES", "VIEW_STATE_SCHEMA",
        ):
            with self.subTest(export=name):
                self.assertTrue(self.m.has_export(name))

    def test_uses_local_storage(self):
        self.assertIn("localStorage", self.m.text)

    def test_storage_key_constant(self):
        self.assertIn("comfymodal.history.v2.viewstate", self.m.text)

    def test_schema_version_marker(self):
        self.assertIn("VIEW_STATE_SCHEMA = 2", self.m.text)

    def test_statuses_normalized_at_load_boundary(self):
        self.assertIn("normalizeStatuses(filters.statuses)", self.m.text)

    def test_imports_canonical_normalizer(self):
        self.assertIn('import { normalizeStatuses } from "./history-v2-repository.js"', self.m.text)

    def test_default_hidden_statuses(self):
        self.assertIn('"failed"', self.m.text)
        self.assertIn('"canceled"', self.m.text)

    def test_default_sort_newest(self):
        self.assertIn('"newest"', self.m.text)

    def test_default_filters_shape(self):
        text = self.m.text
        for key in ("favoriteOnly", "previewOnly", "originalAvailable", "hasImage", "dateFrom", "dateTo"):
            with self.subTest(key=key):
                self.assertIn(key, text)

    def test_resilient_to_json_errors(self):
        self.assertIn("JSON.parse", self.m.text)
        self.assertIn("catch", self.m.text)

    def test_no_inner_html(self):
        self.assertNotIn("innerHTML", self.m.text)

    def test_no_framework_imports(self):
        _assert_no_framework_imports(self, self.m)


class HistoryV2StudioModuleTests(unittest.TestCase):
    """web/studio-history-v2.js uses canonical statuses only."""

    def setUp(self) -> None:
        self.m = _JsModule(WEB / "studio-history-v2.js")
        if not self.m.text:
            self.skipTest("web/studio-history-v2.js missing")

    def test_always_visible_statuses_are_canonical(self):
        self.assertIn('["completed", "running", "completed_with_failures"]', self.m.text)
        self.assertNotIn('["success", "running", "partial"]', self.m.text)

    def test_status_labels_cover_canonical_statuses(self):
        self.assertIn('completed: "Completed"', self.m.text)
        self.assertIn('completed_with_failures: "Completed with failures"', self.m.text)

    def test_explicit_persisted_statuses_used_verbatim(self):
        self.assertIn("storedStatuses.length > 0", self.m.text)
        self.assertIn("new Set(storedStatuses)", self.m.text)

    def test_no_inner_html_assignment(self):
        self.assertIsNone(re.search(r"\.innerHTML\s*=", self.m.text))

    def test_no_framework_imports(self):
        _assert_no_framework_imports(self, self.m)


if __name__ == "__main__":
    unittest.main()
