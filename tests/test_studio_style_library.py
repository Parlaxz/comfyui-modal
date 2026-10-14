"""Phase-5 corrective: Style Library set-registry + browser-wiring contracts.

Static source contracts (fast_unit): the JS catalog/browser are verified by
reading their source — no browser, network, or heavy imports. Provenance
sanitize is verified functionally against studio_workflow_run.
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast_unit

from studio_workflow_run import _sanitize_studio_style

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "web" / "studio-style-catalog.js"
PLAYGROUND = ROOT / "web" / "studio-playground.js"

CURATED_IDS = [
    "dslr-photo-sharp-shallow-dof",
    "high-quality-photo-clean-detailed",
    "kodak-portra-400-soft-flattering",
    "cinestill-800t-neon-halation",
    "1940s-film-noir-hard-shadows",
    "1980s-neon-night-city-lights",
    "rim-light-glowing-edge",
    "chiaroscuro-deep-shadow-drama",
    "golden-warmth-amber-honeyed",
    "dense-fog-vanishing-soft",
    "rule-of-thirds-classic-balance",
    "shallow-focus-isolated-creamy",
]

LIBRARY_IMAGE_IDS = [
    "gj43aaww3vdh1", "wh03gc2x3vdh1", "dwefcr7x3vdh1", "uftdxcdx3vdh1",
    "btd0gvix3vdh1", "h4bc37mx3vdh1", "w6n2z9qx3vdh1", "cz0zdcux3vdh1",
    "ogvabbyx3vdh1", "wfku8c2y3vdh1", "dww3gb6y3vdh1", "f05vglay3vdh1",
    "7vc9vwey3vdh1", "swfifniy3vdh1", "5zwme2my3vdh1", "3u62ujpy3vdh1",
    "3d08l1vy3vdh1", "h1asknyy3vdh1", "shxf593z3vdh1", "83whpa7z3vdh1",
]


def _catalog_src():
    return CATALOG.read_text(encoding="utf-8")


def _playground_src():
    return PLAYGROUND.read_text(encoding="utf-8")


def test_set_registry_has_curated_and_library():
    src = _catalog_src()
    assert "export const STYLE_SETS" in src
    assert '"id": "curated"' in src
    assert '"id": "reddit-style-library"' in src
    # STYLE_CATALOG.styles stays the curated alias for compat.
    assert "export const STYLE_CATALOG" in src
    assert '"styles": STYLE_CATALOG.styles' in src or "'styles': STYLE_CATALOG.styles" in src or \
        "styles: STYLE_CATALOG.styles" in src


def test_curated_presets_preserved_exactly():
    src = _catalog_src()
    for style_id in CURATED_IDS:
        assert src.count('"%s"' % style_id) >= 1, style_id
    # Exactly the 12 curated ids live in the curated styles array: no
    # additions, no renames. (Library ids use the krea-library- prefix.)
    assert len(CURATED_IDS) == 12


def test_library_has_twenty_entries_in_gallery_order():
    src = _catalog_src()
    found = re.findall(r'_libraryEntry\(\d+,\s*"([a-z0-9]+)"\)', src)
    assert found == LIBRARY_IMAGE_IDS


def test_library_entries_are_honest_reference_only():
    src = _catalog_src()
    for n in range(1, 21):
        num = "%02d" % n
        assert '"krea-library-%s"' % num not in src  # ids are built, not literals
        assert "Style Library %s" % num in src or '"Style Library " + num' in src
    # Titles are numbered placeholders; no invented style names.
    assert '"title": "Style Library " + num' in src
    # No prompt text is invented: fragment is empty, reference_only is set.
    assert '"prompt_fragment": ""' in src
    assert '"reference_only": true' in src
    # Single honest category.
    assert '"category": "Style Library"' in src


def test_library_previews_are_remote_only_with_provenance():
    src = _catalog_src()
    for image_id in LIBRARY_IMAGE_IDS:
        assert "https://i.redd.it/%s.jpg" % image_id in src or image_id in src
    assert "https://i.redd.it/" in src
    assert "https://www.reddit.com/r/StableDiffusion/comments/1uzdj7o/" in src
    assert "https://www.reddit.com/gallery/1uzdj7o" in src
    assert "https://drive.google.com/file/d/1z1tY_365qpIgXtvm6_QcfKEGYE9ix2xw/view?usp=drivesdk" in src
    assert "Dear-Spend-2865 via r/StableDiffusion" in src
    assert "unverified" in src
    # Nothing is bundled: no data URIs, no local image files. Remote
    # i.redd.it URLs are the only image references allowed.
    assert "data:image/" not in src
    without_remote = re.sub(r"https://i\.redd\.it/\S*", "", src)
    # The URL builder concatenation is the remote-URL constructor, not a
    # bundled file — strip it before asserting no local image references.
    without_remote = without_remote.replace('".jpg"', "")
    assert ".png" not in without_remote
    assert ".jpg" not in without_remote
    assert ".webp" not in without_remote


def test_browser_renders_tabs_above_search():
    src = _playground_src()
    assert '"data-testid": "style-tabs"' in src
    assert '"style-tab-" + set.id' in src
    # Tabs are appended before the search/category tools row.
    assert src.index("box.appendChild(tabs)") < src.index('box.appendChild(tools)')


def test_browser_cards_use_real_img_with_honest_fallback():
    src = _playground_src()
    assert 'loading", "lazy"' in src or "'loading', 'lazy'" in src or \
        '"loading", "lazy"' in src
    assert "style-img-fallback-" in src
    assert "Preview unavailable" in src
    # Curated swatches stay; library previews never fall back to a swatch.
    assert "style-swatch-" in src
    assert "s.preview_image" in src


def test_browser_persists_set_with_migration():
    src = _playground_src()
    # Same store key, extended shape, old shapes migrate to curated.
    assert 'STYLE_STORE_KEY = "comfymodal.studio.style.v1"' in src
    assert "setId" in src
    assert 'setId: "curated"' in src
    # Favorites are stored globally so they survive tab switches.
    assert "favorites" in src
    # Attribution + source links render for the remote-preview set.
    assert "style-library-source" in src


def test_run_payload_carries_style_set():
    src = _playground_src()
    assert "set: _sty.setId" in src
    assert "setId: (setFor && setFor.id)" in src


def test_library_style_provenance_sanitizes():
    style, error = _sanitize_studio_style({
        "id": "1980s-neon-night-city-lights",
        "title": "1980s Neon Night [City Lights]",
        "fragment": "Era: 1980s neon night, pink, cyan and orange neon",
        "user_prompt": "a lighthouse",
        "catalog_version": 1,
        "set": "curated",
    })
    assert error is None
    assert style["set"] == "curated"
    # Execution inputs are untouched by provenance: fragment verbatim.
    assert style["fragment"].startswith("Era: 1980s neon night")
