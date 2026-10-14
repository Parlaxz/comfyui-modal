// Style catalog (Phase 5). Source: https://github.com/aoleg/photographic-styles-and-wildcards-for-Krea-2
// (via r/StableDiffusion post "Krea 2: styles (wildcards txt)").
// License: MIT, Copyright (c) 2026 ghleg — names, categories and prompt text
// bundled verbatim under that license; the MIT notice is preserved here.
// Preview images are NOT bundled (their license is unknown); thumbnails
// render as CSS hue swatches. Negative prompts from the CSV are not
// consumed (composition is append-only); recorded in handoff.
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
