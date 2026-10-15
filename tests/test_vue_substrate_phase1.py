"""Phase 1 Vue substrate — fast structural guards (FAST_UNIT).

Deterministic, dependency-free checks that the Vue substrate exists in its
intended shape. Behavioral coverage lives in the frontend vitest suites
(frontend/src/**/*.test.ts) and tests/studio_vue_substrate_unit.mjs; this
module only pins the cheap structural facts so the standard FAST_UNIT path
notices if the substrate goes missing or regresses its loader contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"
ASSETS = ROOT / "web" / "assets" / "studio"

EXPECTED_STORES = {
    "infrastructure.ts": "studio-infrastructure",
    "workflows.ts": "studio-workflows",
    "history.ts": "studio-history",
    "playground.ts": "studio-playground",
    "settings.ts": "studio-settings",
    "operations.ts": "studio-operations",
}


@pytest.mark.fast_unit
def test_vue_build_artifacts_are_loader_safe() -> None:
    assert (ASSETS / "studio.mjs").is_file(), "stable Vue entry must be built"
    assert (ASSETS / "studio.css").is_file(), "Vue stylesheet must be built"
    js_files = [p for p in ASSETS.rglob("*") if p.is_file() and p.suffix == ".js"]
    assert js_files == [], (
        "no .js under web/assets/studio: ComfyUI auto-executes **/*.js "
        f"as extensions: {js_files}"
    )


@pytest.mark.fast_unit
def test_vue_stores_exist_with_stable_ids() -> None:
    for filename, store_id in EXPECTED_STORES.items():
        text = (SRC / "stores" / filename).read_text(encoding="utf-8")
        assert f'"{store_id}"' in text, f"{filename} must declare {store_id}"


@pytest.mark.fast_unit
def test_vue_ui_imports_zero_old_studio_css() -> None:
    checked = 0
    for path in SRC.rglob("*"):
        if path.suffix not in (".ts", ".vue"):
            continue
        text = path.read_text(encoding="utf-8")
        assert "studio-styles" not in text, f"{path.name}: old styles import"
        assert "testing-styles" not in text, f"{path.name}: old styles import"
        assert ".comfymodal-" not in text, f"{path.name}: copied old selector"
        checked += 1
    assert checked > 10, "frontend sources must exist"


@pytest.mark.fast_unit
def test_vue_router_has_five_pages_no_docs() -> None:
    codec = (SRC / "app" / "router" / "studioRoute.ts").read_text(encoding="utf-8")
    for page in ("playground", "history", "workflows", "backend", "settings"):
        assert f'"{page}"' in codec, f"route key {page} missing"
    assert '"docs"' not in codec, "no sixth Docs route"
    history = (SRC / "app" / "router" / "studioHistory.ts").read_text(encoding="utf-8")
    assert "serializeStudioHash(routerLocationToRoute(to))" in history, (
        "router link hrefs must render the canonical Studio hash"
    )


@pytest.mark.fast_unit
def test_vue_host_bridge_and_old_studio_intact() -> None:
    host = (ROOT / "web" / "studio-vue-host.js").read_text(encoding="utf-8")
    assert "data-studio-portals" in host, "Studio-contained portal target"
    assert "setGraphInteractionEnabled" in host, "wizard graph seam"
    entry = (ROOT / "web" / "modal-testing.js").read_text(encoding="utf-8")
    assert "window.open_testing_modal" in entry
    assert "window.close_testing_modal" in entry
    assert "window.__comfymodalOpenVueStudio" in entry


@pytest.mark.fast_unit
def test_vue_fixed_stack_only() -> None:
    pkg = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    for required in (
        "vue",
        "typescript",
        "pinia",
        "vue-router",
        "tailwindcss",
        "reka-ui",
        "@lucide/vue",
        "zod",
        "@vueuse/core",
        "vite",
    ):
        assert required in deps, f"fixed stack dep missing: {required}"
    for name in deps:
        assert "@tanstack/" not in name, f"forbidden dep: {name}"
        assert "xstate" not in name, f"forbidden dep: {name}"
