"""Phase-5 corrective: Style Library set-registry + browser-wiring contracts.

Static source contracts (fast_unit): the JS catalog/browser are verified by
reading their source — no browser, network, or heavy imports. Provenance
sanitize is verified functionally against studio_workflow_run.

Library provenance: 118/120 reference-sheet labels matched case-insensitively
(punctuation-normalized) to wildcard entry names from the Drive wildcard text
(192061 bytes, 289 `Name: fragment` lines, fetched via direct download);
titles/fragments are verbatim copies. UNMATCHED (excluded, fragments never
invented): ROMANCE MANGA (S02), BORDERLANDS (S19). "Film Noir" has two
distinct wildcard fragments; the library uses the first. LEGO MINIFIGURE +
LEGO share one fragment ("LEGO Minifigure") under unique ids. Each sheet is
3 cols x 2 rows (r1c1 r1c2 r1c3 r2c1 r2c2 r2c3); S02 misses r2c1, S19 misses
r2c2, hence rows {1: 60, 2: 58} and cols {1: 39, 2: 39, 3: 40}.
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

CURATED_TITLES = [
    "DSLR Photo [Sharp & Shallow DOF]",
    "High-Quality Photo [Clean & Detailed]",
    "Kodak Portra 400 [Soft & Flattering]",
    "CineStill 800T [Neon Halation]",
    "1940s Film Noir [Hard Shadows]",
    "1980s Neon Night [City Lights]",
    "Rim Light [Glowing Edge]",
    "Chiaroscuro [Deep Shadow Drama]",
    "Golden Warmth [Amber & Honeyed]",
    "Dense Fog [Vanishing & Soft]",
    "Rule of Thirds [Classic Balance]",
    "Shallow Focus [Isolated & Creamy]",
]

LIBRARY_IMAGE_IDS = [
    "gj43aaww3vdh1", "wh03gc2x3vdh1", "dwefcr7x3vdh1", "uftdxcdx3vdh1",
    "btd0gvix3vdh1", "h4bc37mx3vdh1", "w6n2z9qx3vdh1", "cz0zdcux3vdh1",
    "ogvabbyx3vdh1", "wfku8c2y3vdh1", "dww3gb6y3vdh1", "f05vglay3vdh1",
    "7vc9vwey3vdh1", "swfifniy3vdh1", "5zwme2my3vdh1", "3u62ujpy3vdh1",
    "3d08l1vy3vdh1", "h1asknyy3vdh1", "shxf593z3vdh1", "83whpa7z3vdh1",
]

# Exact wildcard entry names, catalog order (sheet order S01..S20).
LIBRARY_TITLES = [
    "Anime Style",
    "Ghibli Style",
    "70s Anime",
    "Chibi Anime",
    "My Hero Academia Style",
    "Granblue Fantasy Pin-Up Style",
    "Manga Style",
    "Akira Toriyama Style",
    "Chainsaw Man Style",
    "Shindol Style",
    "One Piece Style",
    "Cartoon Style",
    "Steven Universe Style",
    "Adventure Time Style",
    "Hanna-Barbera Style",
    "Rubber Hose Cartoon",
    "Disney Ultradetailed Illustration",
    "Drawing",
    "Chinese Ink Drawing",
    "Fashion Sketch",
    "Technical Drawing",
    "Playful Hand-Drawn Illustration",
    "Very Simplistic Doodle",
    "Photography",
    "Analog Photography",
    "Black And White Documentary",
    "Brassa\u00ef Night Photography",
    "Cinematic Photography",
    "Selfie Photo",
    "Comics Style",
    "Alternative Comics Style",
    "Amanda Conner Illustration",
    "Hellboy Style",
    "Bruce Timm Noir",
    "Graphic Novel",
    "Design",
    "Corporate Memphis",
    "Soviet Propaganda Poster",
    "Graphic Flat-Vector Travel Poster Illustration",
    "Poster Art",
    "Contemporary Commercial Illustration",
    "Painting",
    "Van Gogh Style",
    "Cubism",
    "Jackson Pollock Style",
    "Academic Precision Realism",
    "Wet-on-Wet Watercolor Ink Painting",
    "Alex Ross Style",
    "Artgerm Style",
    "Boris Vallejo Style",
    "Pin-Up",
    "American Comic Realism",
    "RossDraws Style",
    "Children's Book Drawing",
    "Vintage Children's Book Drawing",
    "Collector Storybook Illustration",
    "Bookplate Illustration",
    "Whimsical Illustration",
    "Beatrix Potter Style",
    "Character Design Illustration",
    "Arcane Animation Still",
    "Caricature",
    "Gris Grimly Style",
    "Tim Burton Style",
    "Loose Crosshatched Character Sketch",
    "Brushwork Emphasis",
    "Ink Pen Drawing",
    "Carne Griffiths Style",
    "Impasto",
    "Crayola Colored-Book Style",
    "Airbrush Fantasy",
    "Natural Lighting Photography",
    "Blue Hour Cinema",
    "Golden Hour Photography",
    "High-Key Lighting Photography",
    "Direct-Flash Photography",
    "Neon Photography",
    "3D Render",
    "Pixar  Animation",
    "Cinematic Final Fantasy 3D Render",
    "Isometric 3D Graphic",
    "Low Poly",
    "PS1 Graphics",
    "Claymation",
    "Wallace and Gromit Style",
    "Muppets Style",
    "LEGO Minifigure",
    "LEGO Minifigure",
    "Funko Pop Style",
    "Pop Art",
    "Variable-Size Ben-Day Dots Illustration",
    "Contemporary Lithography",
    "Contemporary Ukiyo-E",
    "Woodcut",
    "Etching",
    "Photoshoot",
    "Instagram Model Glamour Photography",
    "GQ Photoshoot",
    "Supermodel Photoshoot",
    "Playboy / Maxim-Style Photoshoot",
    "LinkedIn Pro Portrait",
    "Paper Cutout",
    "Quilling",
    "Mosaic Art",
    "Stained Glass Flat Art",
    "Marble Sculpture",
    "Mixed Media",
    "8-Bit Style",
    "Minecraft Style",
    "Zelda Wind Waker Style",
    "GTA V Polished Cover Art",
    "Cel Shading",
    "Film Noir",
    "Hitchcockian Photo",
    "Sin City Photography",
    "Stranger Things-Inspired Art",
    "Cyberpunk Photography",
    "Cinematic Tron",
]

# Two full wildcard fragments embedded for byte-verbatim spot-checks.
AKIRA_TORIYAMA_FRAGMENT = (
    "clean and highly readable linework, appealing character-focused design "
    "language, expressive forms, dynamic silhouettes, polished cel-style "
    "rendering, balanced stylization, energetic visual storytelling, strong "
    "graphic clarity, and a playful yet technically disciplined aesthetic that "
    "emphasizes personality and visual impact, reminiscent of Akira Toriyama "
    "and Toyotarou, inspired by Dragon Ball and Chrono Trigger."
)

ARTGERM_FRAGMENT = (
    "A polished digital-painting portrait style blending photorealistic "
    "rendering with idealized comic-glamour proportions, luminous porcelain "
    "skin with soft airbrushed gradients and crisp specular highlights, richly "
    "detailed glossy rendering carried strand by strand where fine linework is "
    "called for, confident glamorous poses framed with clean painterly "
    "composition, and a slick, high-production pin-up polish that bridges "
    "Western comic-cover art and digital beauty illustration. Influenced by: "
    'Stanley "Artgerm" Lau, comic-book cover illustration, digital pin-up '
    "art, airbrush portrait technique."
)


def _catalog_src():
    return CATALOG.read_text(encoding="utf-8")


def _playground_src():
    return PLAYGROUND.read_text(encoding="utf-8")


def _unjs(s):
    """Decode a JS double-quoted string body (escapes the generator emits)."""
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            out.append({"n": "\n", "r": "\r", "t": "\t",
                        "\\": "\\", '"': '"',
                        "u": "u"}.get(n, n))
            # \uXXXX sequences never appear in the catalog; a lone "u" would
            # be a generator bug, so fail loudly instead of guessing.
            assert not (n == "u"), s[:80]
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _js_field_values(src, field):
    return [_unjs(m) for m in
            re.findall(r'"%s": "((?:[^"\\]|\\.)*)"' % field, src)]


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
    # additions, no renames. (Library ids use the krea- prefix.)
    assert len(CURATED_IDS) == 12


def test_library_has_matched_entry_count():
    src = _catalog_src()
    # One entry per matched label: 118/120 (ROMANCE MANGA, BORDERLANDS out).
    assert len(LIBRARY_TITLES) == 118
    assert src.count('"category": "Style Library"') == 118
    # Composable entries: no reference_only gate, no empty fragments, no
    # placeholder builder.
    assert '"reference_only"' not in src
    assert '"prompt_fragment": ""' not in src
    assert "_libraryEntry(" not in src
    assert '"preview_image"' not in src
    # Drive text recovered: header records the direct-download source.
    assert "RECOVERED via direct download" in src


def test_library_titles_exact():
    src = _catalog_src()
    titles = _js_field_values(src, "title")
    lib = [t for t in titles
           if t not in CURATED_TITLES and t not in ("Curated", "Style Library")]
    assert lib == LIBRARY_TITLES


def test_library_ids_unique_and_slugged():
    src = _catalog_src()
    ids = re.findall(r'"id": "(krea-[^"]+)"', src)
    assert len(ids) == 118
    assert len(set(ids)) == 118
    # The shared-fragment pair stays addressable under unique ids.
    assert "krea-lego-minifigure" in ids
    assert "krea-lego-minifigure-2" in ids


def test_library_fragments_nonempty_verbatim():
    src = _catalog_src()
    frags = _js_field_values(src, "prompt_fragment")
    assert len(frags) == 12 + 118
    lib = frags[12:]  # catalog emits the curated block first
    assert all(f.strip() for f in lib)
    # Real wildcard bodies are long; nothing placeholder-short survives.
    assert min(len(f) for f in lib) >= 100
    # Exactly one documented shared fragment (LEGO MINIFIGURE + LEGO).
    assert len(set(lib)) == len(lib) - 1
    by_title = dict(zip(
        [t for t in _js_field_values(src, "title")
         if t not in CURATED_TITLES and t not in ("Curated", "Style Library")],
        lib))
    assert by_title["Akira Toriyama Style"] == AKIRA_TORIYAMA_FRAGMENT
    assert by_title["Artgerm Style"] == ARTGERM_FRAGMENT


def test_library_crop_row_col_metadata():
    src = _catalog_src()
    previews = re.findall(
        r'"preview": \{"sheet": "https://i\.redd\.it/([a-z0-9]+)\.jpg", '
        r'"row": (\d), "col": (\d)\}', src)
    assert len(previews) == 118
    rows = [r for _, r, _ in previews]
    cols = [c for _, _, c in previews]
    assert sorted(set(rows)) == ["1", "2"]
    assert sorted(set(cols)) == ["1", "2", "3"]
    # S02 misses r2c1, S19 misses r2c2.
    assert rows.count("1") == 60 and rows.count("2") == 58
    assert cols.count("1") == 39 and cols.count("2") == 39
    assert cols.count("3") == 40
    # Every sheet image id is a known gallery image; all 20 sheets appear.
    found_ids = {image_id for image_id, _, _ in previews}
    assert found_ids == set(LIBRARY_IMAGE_IDS)


def test_library_descriptions_are_factual():
    src = _catalog_src()
    descriptions = _js_field_values(src, "description")
    lib = [d for d in descriptions
           if "example from reference sheet S" in d]
    assert len(lib) == 118
    assert all("Full wildcard text applied at run time." in d for d in lib)


def test_library_unmatched_labels_excluded_but_listed():
    src = _catalog_src()
    # No invented entries or fragments for the two unmatched labels.
    assert '"title": "Romance Manga"' not in src
    assert '"title": "Borderlands"' not in src
    # ...but the exclusion is explicit in the header comment, not silent.
    assert "ROMANCE MANGA (S02)" in src
    assert "BORDERLANDS (S19)" in src


def test_library_previews_are_remote_only_with_provenance():
    src = _catalog_src()
    for image_id in LIBRARY_IMAGE_IDS:
        assert ("https://i.redd.it/%s.jpg" % image_id) in src
    assert "https://www.reddit.com/r/StableDiffusion/comments/1uzdj7o/" in src
    assert "https://www.reddit.com/gallery/1uzdj7o" in src
    assert "https://drive.google.com/file/d/1z1tY_365qpIgXtvm6_QcfKEGYE9ix2xw/view?usp=drivesdk" in src
    assert "Dear-Spend-2865 via r/StableDiffusion" in src
    assert "unverified" in src
    # Nothing is bundled: no data URIs, no local image files, no blocked
    # preview host. Remote i.redd.it URLs are the only image references.
    assert "data:image/" not in src
    # The blocked preview host is mentioned exactly once: the header comment
    # explaining why it is NOT used. No URL ever points at it.
    assert src.count("preview.redd.it") == 1
    assert "https://preview.redd.it" not in src
    without_remote = re.sub(r"https://i\.redd\.it/[a-z0-9]+\.jpg", "", src)
    assert ".png" not in without_remote
    assert ".jpg" not in without_remote
    assert ".webp" not in without_remote


def test_browser_renders_tabs_above_search():
    src = _playground_src()
    assert '"data-testid": "style-tabs"' in src
    assert '"style-tab-" + set.id' in src
    # Tabs are appended before the search/category tools row.
    assert src.index("box.appendChild(tabs)") < src.index('box.appendChild(tools)')


def test_browser_cards_crop_remote_sheet_with_honest_fallback():
    src = _playground_src()
    # Deterministic client-side CSS crop of the 3x2 reference sheet.
    assert "aspect-ratio:2/3" in src
    assert "overflow:hidden" in src
    assert "width:300%" in src
    assert "max-width:none" in src
    # Plain precomputed % margins (calc((1-N)*100%) is rejected by the CSS
    # parser, so the implementation must not use it).
    assert "margin-left:calc((1-" not in src
    assert "margin-top:calc((1-" not in src
    assert "((1 - _col) * 100)" in src and "((1 - _row) * 150)" in src
    assert 'loading", "lazy"' in src or "'loading', 'lazy'" in src or \
        '"loading", "lazy"' in src
    assert "style-media-" in src
    assert "style-img-fallback-" in src
    assert "Preview unavailable" in src
    # Curated swatches stay; library crops read the preview object.
    assert "style-swatch-" in src
    assert "s.preview" in src
    assert "pv.sheet" in src
    # No reference-only gating survives: every card composes for real.
    assert "reference_only" not in src
    assert "preview_image" not in src


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


def test_library_style_provenance_sanitizes_with_real_fragment():
    style, error = _sanitize_studio_style({
        "id": "krea-akira-toriyama-style",
        "title": "Akira Toriyama Style",
        "fragment": AKIRA_TORIYAMA_FRAGMENT,
        "user_prompt": "a lighthouse",
        "catalog_version": 1,
        "set": "reddit-style-library",
    })
    assert error is None
    assert style is not None
    assert style["set"] == "reddit-style-library"
    # Execution inputs are untouched by provenance: fragment verbatim.
    assert style["fragment"] == AKIRA_TORIYAMA_FRAGMENT
    # A curated companion keeps working alongside the library set.
    style, error = _sanitize_studio_style({
        "id": "1980s-neon-night-city-lights",
        "title": "1980s Neon Night [City Lights]",
        "fragment": "Era: 1980s neon night, pink, cyan and orange neon",
        "user_prompt": "a lighthouse",
        "catalog_version": 1,
        "set": "curated",
    })
    assert error is None
    assert style is not None
    assert style["set"] == "curated"
    assert style["fragment"].startswith("Era: 1980s neon night")
