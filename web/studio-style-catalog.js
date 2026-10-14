// Style catalog (Phase 5) + Style Library (Phase 5 corrective).
//
// Set "curated": 12 prompt presets bundled verbatim under their MIT license
// (Copyright (c) 2026 ghleg; source below). The MIT notice is preserved here.
// Preview images are NOT bundled (their license is unknown); curated cards
// render as CSS hue swatches. Negative prompts from the CSV are not
// consumed (composition is append-only); recorded in handoff.
//
// Set "reddit-style-library": 20 reference-only entries, one per image in
// the r/StableDiffusion gallery "Krea 2 : styles (wildcards txt)" by
// Dear-Spend-2865 (2026-07-17):
//   post:    https://www.reddit.com/r/StableDiffusion/comments/1uzdj7o/krea_2_styles_wildcards_txt/
//   gallery: https://www.reddit.com/gallery/1uzdj7o
//   drive:   https://drive.google.com/file/d/1z1tY_365qpIgXtvm6_QcfKEGYE9ix2xw/view?usp=drivesdk
// Shortlink https://www.reddit.com/r/StableDiffusion/s/O6wS76rpNt resolves
// to the post above.
//
// Drive fetch outcome (2026-10-14, recorded – do not silently retry as if
// verified): the Drive file sits behind a Google sign-in wall and exposes
// no fetchable wildcard text, so NO prompt fragments are bundled for this
// set. prompt_fragment is "" and reference_only is true for every library
// entry; selecting one never alters the prompt (plain-prompt run).
//
// Licensing: the post carries NO explicit reuse license for its text or
// images (Reddit UA: poster retains ownership, no downstream redistribution
// grant; Krea Terms prohibit copying/significant-portion storage without
// consent). Images are therefore NOT bundled in-repo: previews render as
// remote <img> against i.redd.it with attribution + source links.
// (preview.redd.it 307-redirects to an HTML media page that browsers
// ORB-block inside <img>; i.redd.it serves the same image bytes directly.)
// Gallery captions are empty in metadata and the overlaid style labels
// require pixel inspection, so titles stay honest ("Style Library 01..20"
// + note) — no style names are invented, and no Krea prompt text is faked.
//
// No image prefetch storms: cards use loading="lazy" and no preloading.
export const STYLE_CATALOG = {
  "version": 1,
  "license": "MIT, Copyright (c) 2026 ghleg",
  "source": "https://github.com/aoleg/photographic-styles-and-wildcards-for-Krea-2",
  "styles": [
    {
      "id": "dslr-photo-sharp-shallow-dof",
      "title": "DSLR Photo [Sharp & Shallow DOF]",
      "category": "Quality",
      "tags": ["photo", "sharp", "dof"],
      "description": "Sharp large-aperture photo with shallow depth of field.",
      "prompt_fragment": "Quality: sharp DSLR photo shot at a large aperture, shallow depth of field, out of focus background, accurate color, high dynamic range, and clean fine detail.",
      "hue": 210
    },
    {
      "id": "high-quality-photo-clean-detailed",
      "title": "High-Quality Photo [Clean & Detailed]",
      "category": "Quality",
      "tags": ["photo", "clean", "detailed"],
      "description": "Crisp high-quality photo with full tonal range.",
      "prompt_fragment": "Quality: high-quality photo, crisp fine detail, accurate color, a full range of tones from shadows to highlights, and clean rendering.",
      "hue": 200
    },
    {
      "id": "kodak-portra-400-soft-flattering",
      "title": "Kodak Portra 400 [Soft & Flattering]",
      "category": "Film Stocks",
      "tags": ["film", "portra", "warm"],
      "description": "Warm flattering Portra tones with gentle contrast.",
      "prompt_fragment": "Style and tones: Kodak Portra 400, with warm natural skin tones, gentle contrast, retained shadow and highlight detail, and fine grain.",
      "hue": 30
    },
    {
      "id": "cinestill-800t-neon-halation",
      "title": "CineStill 800T [Neon Halation]",
      "category": "Film Stocks",
      "tags": ["film", "neon", "night"],
      "description": "Cool-shadow neon film look with red halation.",
      "prompt_fragment": "Style and tones: CineStill 800T, with cool-leaning shadows, warmer whites and highlights, a faint red halation around bright light sources, and visible grain.",
      "hue": 320
    },
    {
      "id": "1940s-film-noir-hard-shadows",
      "title": "1940s Film Noir [Hard Shadows]",
      "category": "Decades",
      "tags": ["noir", "black-and-white", "shadows"],
      "description": "Low-key black-and-white with long hard shadows.",
      "prompt_fragment": "Era: 1940s film noir, low-key black-and-white, long hard shadows, light through blinds, and deep blacks.",
      "hue": 0
    },
    {
      "id": "1980s-neon-night-city-lights",
      "title": "1980s Neon Night [City Lights]",
      "category": "Decades",
      "tags": ["neon", "night", "city"],
      "description": "Neon night streets with wet reflections and grain.",
      "prompt_fragment": "Era: 1980s neon night, pink, cyan and orange neon, wet reflective streets, dark blue skies, and film grain.",
      "hue": 300
    },
    {
      "id": "rim-light-glowing-edge",
      "title": "Rim Light [Glowing Edge]",
      "category": "Lighting",
      "tags": ["light", "rim", "contour"],
      "description": "Glowing rim contour separating subject from dark ground.",
      "prompt_fragment": "Lighting: rim light behind the subject tracing a glowing contour, the front in soft shadow, and clean separation from a darker surrounding.",
      "hue": 45
    },
    {
      "id": "chiaroscuro-deep-shadow-drama",
      "title": "Chiaroscuro [Deep Shadow Drama]",
      "category": "Lighting",
      "tags": ["light", "shadow", "drama"],
      "description": "Single directional light carving form from darkness.",
      "prompt_fragment": "Lighting: chiaroscuro, one directional light carving the subject from deep darkness, a slow tonal turn, and rich dark tones filling most of the frame.",
      "hue": 20
    },
    {
      "id": "golden-warmth-amber-honeyed",
      "title": "Golden Warmth [Amber & Honeyed]",
      "category": "Color & tonality",
      "tags": ["color", "warm", "amber"],
      "description": "Amber honey tones with cream whites and warm shadows.",
      "prompt_fragment": "Color: golden warmth, amber and honey tones over the frame, cream whites, warm brown shadows, and gently boosted yellows.",
      "hue": 38
    },
    {
      "id": "dense-fog-vanishing-soft",
      "title": "Dense Fog [Vanishing & Soft]",
      "category": "Atmosphere",
      "tags": ["fog", "soft", "murk"],
      "description": "Subject half-dissolved in pale collapsing fog.",
      "prompt_fragment": "Atmosphere: dense fog, the subject half-dissolved in pale gray-white murk, contrast collapsing with distance, and cool desaturated color.",
      "hue": 180
    },
    {
      "id": "rule-of-thirds-classic-balance",
      "title": "Rule of Thirds [Classic Balance]",
      "category": "Composition",
      "tags": ["composition", "balance", "thirds"],
      "description": "Off-center subject on a third-line with breathing room.",
      "prompt_fragment": "Composition: rule of thirds, the subject off-center on a third-line, the horizon on a third, and breathing room ahead of the subject.",
      "hue": 120
    },
    {
      "id": "shallow-focus-isolated-creamy",
      "title": "Shallow Focus [Isolated & Creamy]",
      "category": "Focus & depth",
      "tags": ["focus", "shallow", "bokeh"],
      "description": "Thin sharp plane with creamy melted background.",
      "prompt_fragment": "Focus: shallow depth of field, a thin plane of the subject sharp, out of focus background melting into creamy blur, and the subject lifted from its surroundings.",
      "hue": 150
    }
  ]
};

// Shared provenance for every Style Library entry (remote-only previews).
export const STYLE_LIBRARY_PROVENANCE = {
  "post": "https://www.reddit.com/r/StableDiffusion/comments/1uzdj7o/krea_2_styles_wildcards_txt/",
  "gallery": "https://www.reddit.com/gallery/1uzdj7o",
  "drive_url": "https://drive.google.com/file/d/1z1tY_365qpIgXtvm6_QcfKEGYE9ix2xw/view?usp=drivesdk",
  "attribution": "Dear-Spend-2865 via r/StableDiffusion",
  "license": "unverified — remote preview only, not bundled",
};

function _libraryEntry(n, imageId) {
  var num = String(n).padStart(2, "0");
  var imageUrl = "https://i.redd.it/" + imageId + ".jpg";
  return {
    "id": "krea-library-" + num,
    "title": "Style Library " + num,
    "category": "Style Library",
    "tags": ["reference-only"],
    "description": "Reference-only gallery preview " + num + " of 20. The overlaid style label is unverified, so no style name is claimed; no prompt fragment is bundled (Drive text unfetchable). Selecting this card leaves the prompt unchanged.",
    "prompt_fragment": "",
    "preview_image": imageUrl,
    "reference_only": true,
    "provenance": {
      "post": STYLE_LIBRARY_PROVENANCE.post,
      "gallery": STYLE_LIBRARY_PROVENANCE.gallery,
      "image_url": imageUrl,
      "drive_url": STYLE_LIBRARY_PROVENANCE.drive_url,
      "attribution": STYLE_LIBRARY_PROVENANCE.attribution,
      "license": STYLE_LIBRARY_PROVENANCE.license,
    },
  };
}

// Set registry. STYLE_CATALOG.styles stays the curated alias for compat.
export const STYLE_SETS = [
  {
    "id": "curated",
    "title": "Curated",
    "styles": STYLE_CATALOG.styles,
  },
  {
    "id": "reddit-style-library",
    "title": "Style Library",
    "source": STYLE_LIBRARY_PROVENANCE.post,
    "styles": [
      _libraryEntry(1, "gj43aaww3vdh1"),
      _libraryEntry(2, "wh03gc2x3vdh1"),
      _libraryEntry(3, "dwefcr7x3vdh1"),
      _libraryEntry(4, "uftdxcdx3vdh1"),
      _libraryEntry(5, "btd0gvix3vdh1"),
      _libraryEntry(6, "h4bc37mx3vdh1"),
      _libraryEntry(7, "w6n2z9qx3vdh1"),
      _libraryEntry(8, "cz0zdcux3vdh1"),
      _libraryEntry(9, "ogvabbyx3vdh1"),
      _libraryEntry(10, "wfku8c2y3vdh1"),
      _libraryEntry(11, "dww3gb6y3vdh1"),
      _libraryEntry(12, "f05vglay3vdh1"),
      _libraryEntry(13, "7vc9vwey3vdh1"),
      _libraryEntry(14, "swfifniy3vdh1"),
      _libraryEntry(15, "5zwme2my3vdh1"),
      _libraryEntry(16, "3u62ujpy3vdh1"),
      _libraryEntry(17, "3d08l1vy3vdh1"),
      _libraryEntry(18, "h1asknyy3vdh1"),
      _libraryEntry(19, "shxf593z3vdh1"),
      _libraryEntry(20, "83whpa7z3vdh1"),
    ],
  },
];
