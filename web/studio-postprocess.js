// Modal Studio — Post Processing workspace (TinyLuma-based).
//
// Integrated finishing editor mounted inside the Post Processing tool canvas.
// Full TinyLuma control parity: Light / Color / Curves / Mixer / Grading /
// Detail / Effects / LUT library / Crop+Straighten / Spot heal / WB picker /
// presets / filmstrip / batch apply / undo-redo / before-after / export.
//
// Processing order mirrors TinyLuma's render_full_image:
// heal -> color/curves/LUT -> dehaze -> spatial -> orient/straighten/crop.
// Preview renders at <=1200px on the long side; export renders full-res.
// Client-side engine: single-threaded Canvas 2D pixel pipeline (no WASM yet).
// Approximations vs native Rust are marked APPROX below.

import { el } from "./studio-ui.js";

var PREVIEW_MAX = 1200;
var LS_RECIPE = "comfymodal.studio.postprocess.recipe.v1";
var LS_PRESETS = "comfymodal.studio.postprocess.presets.v1";
var LS_LUTFAV = "comfymodal.studio.postprocess.lutfav.v1";
var _styleInjected = false;

// ── Recipe ──────────────────────────────────────────────────────────────

export function defaultRecipe() {
  return {
    exposure: 0, contrast: 0, whites: 0, blacks: 0, shadows: 0, highlights: 0, brightness: 0,
    temp: 0, tint: 0, vibrance: 0, saturation: 0, hue: 0,
    texture: 0, clarity: 0, dehaze: 0, sharpen: 0, detailMasking: 0, structure: 0,
    noiseChroma: 0, noiseLuma: 0, noiseDetail: 50,
    lutIntensity: 0, lutId: "",
    grain: 0, grainSize: 25, grainRoughness: 0,
    glow: 0, halation: 0, flare: 0,
    vignetteAmount: 0, vignetteMidpoint: 50, vignetteRoundness: 0, vignetteFeather: 50,
    curves: { master: [[0, 0], [1, 1]], r: [[0, 0], [1, 1]], g: [[0, 0], [1, 1]], b: [[0, 0], [1, 1]] },
    mixer: [0, 1, 2, 3, 4, 5, 6, 7].map(function () { return { h: 0, s: 0, l: 0 }; }),
    grading: {
      shadow: { h: 0, s: 0, l: 0 }, mid: { h: 0, s: 0, l: 0 },
      high: { h: 0, s: 0, l: 0 }, global: { h: 0, s: 0, l: 0 },
      blend: 50, balance: 0,
    },
    crop: { x: 0, y: 0, w: 1, h: 1, angle: 0 },
    spots: [], // [{x,y,r}] normalized
    embedMetadata: true, format: "png", quality: 90,
  };
}

var BUILTIN_PRESETS = [
  { name: "Neutral", recipe: defaultRecipe() },
  { name: "Clean Portrait", recipe: Object.assign(defaultRecipe(), { texture: -18, clarity: 12, sharpen: 22, grain: 8, grainSize: 25, vibrance: 8, whites: 6 }) },
  { name: "Cinematic Teal", recipe: Object.assign(defaultRecipe(), { contrast: 22, saturation: -8, temp: -14, tint: 6, vignetteAmount: -28, grain: 22, grainSize: 30 }) },
  { name: "Warm Film", recipe: Object.assign(defaultRecipe(), { temp: 16, tint: -4, saturation: 10, grain: 30, grainSize: 38, grainRoughness: 30, halation: 18, vignetteAmount: -18 }) },
  { name: "Punchy", recipe: Object.assign(defaultRecipe(), { contrast: 30, clarity: 25, structure: 18, sharpen: 35, saturation: 18, vibrance: 12, blacks: -10 }) },
  { name: "Soft Matte", recipe: Object.assign(defaultRecipe(), { contrast: -18, blacks: 22, clarity: -12, saturation: -14, grain: 26, glow: 14 }) },
];

var MIXER_BANDS = ["Red", "Orange", "Yellow", "Green", "Aqua", "Blue", "Purple", "Magenta"];
var BAND_HUES = [0, 30, 60, 120, 180, 240, 270, 320]; // degrees

// ── Small helpers ───────────────────────────────────────────────────────

function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
function clone(o) { return JSON.parse(JSON.stringify(o)); }
function uid() { return "pp" + Math.random().toString(36).slice(2, 9); }

function storeGet(key, fallback) {
  try {
    var raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (_e) { return fallback; }
}
function storeSet(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (_e) {}
}

// sRGB <-> linear
function srgbToLin(c) { return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }
function linToSrgb(c) { return c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055; }

function rgbToHsl(r, g, b) {
  var max = Math.max(r, g, b), min = Math.min(r, g, b), h = 0, s = 0;
  var l = (max + min) / 2, d = max - min;
  if (d !== 0) {
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
  }
  return [h * 360, s, l];
}
function hslToRgb(h, s, l) {
  h = ((h % 360) + 360) % 360 / 360;
  var r, g, b;
  if (s === 0) { r = g = b = l; }
  else {
    var q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    var p = 2 * l - q;
    r = hue2(p, q, h + 1 / 3); g = hue2(p, q, h); b = hue2(p, q, h - 1 / 3);
  }
  return [r, g, b];
  function hue2(p, q, t) {
    if (t < 0) t += 1; if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  }
}
function smoothstep(a, b, x) {
  var t = clamp((x - a) / (b - a), 0, 1);
  return t * t * (3 - 2 * t);
}
// Separable box blur on Float32Array rgb (stride 3). APPROX of gaussian/bilateral.
function boxBlur(data, w, h, radius) {
  if (radius < 1) return data;
  var tmp = new Float32Array(data.length);
  var out = new Float32Array(data.length);
  var r = Math.round(radius), i, x, y, c;
  for (y = 0; y < h; y++) {
    for (x = 0; x < w; x++) {
      var acc0 = 0, acc1 = 0, acc2 = 0, n = 0;
      for (var k = -r; k <= r; k++) {
        var sx = clamp(x + k, 0, w - 1), idx = (y * w + sx) * 3;
        acc0 += data[idx]; acc1 += data[idx + 1]; acc2 += data[idx + 2]; n++;
      }
      i = (y * w + x) * 3;
      tmp[i] = acc0 / n; tmp[i + 1] = acc1 / n; tmp[i + 2] = acc2 / n;
    }
  }
  for (y = 0; y < h; y++) {
    for (x = 0; x < w; x++) {
      var b0 = 0, b1 = 0, b2 = 0, m = 0;
      for (var k2 = -r; k2 <= r; k2++) {
        var sy = clamp(y + k2, 0, h - 1), j = (sy * w + x) * 3;
        b0 += tmp[j]; b1 += tmp[j + 1]; b2 += tmp[j + 2]; m++;
      }
      i = (y * w + x) * 3;
      out[i] = b0 / m; out[i + 1] = b1 / m; out[i + 2] = b2 / m;
    }
  }
  return out;
}
// Fritsch-Carlson monotone cubic through points [[x,y]...] -> 256-entry table.
function bakeCurveTable(points) {
  var pts = points.slice().sort(function (a, b) { return a[0] - b[0]; });
  var n = pts.length, out = new Float32Array(256);
  if (n < 2) { for (var i = 0; i < 256; i++) out[i] = i / 255; return out; }
  var dx = [], m = [], i;
  for (i = 0; i < n - 1; i++) {
    dx[i] = pts[i + 1][0] - pts[i][0];
    m[i] = dx[i] > 1e-9 ? (pts[i + 1][1] - pts[i][1]) / dx[i] : 0;
  }
  var t = new Array(n);
  t[0] = m[0]; t[n - 1] = m[n - 2];
  for (i = 1; i < n - 1; i++) {
    if (m[i - 1] === 0 || m[i] === 0 || (m[i - 1] < 0) !== (m[i] < 0)) t[i] = 0;
    else t[i] = 3 * dx[i - 1] * dx[i] / ((2 * dx[i] + dx[i - 1]) / m[i - 1] + (dx[i] + 2 * dx[i - 1]) / m[i]);
  }
  for (i = 0; i < 256; i++) {
    var x = i / 255, v;
    if (x <= pts[0][0]) v = pts[0][1];
    else if (x >= pts[n - 1][0]) v = pts[n - 1][1];
    else {
      var s = 0;
      while (s < n - 2 && x > pts[s + 1][0]) s++;
      var h = dx[s], x0 = pts[s][0], y0 = pts[s][1], y1 = pts[s + 1][1];
      var tt = (x - x0) / h;
      v = (2 * tt * tt * tt - 3 * tt * tt + 1) * y0 + (tt * tt * tt - 2 * tt * tt + tt) * h * t[s] +
        (-2 * tt * tt * tt + 3 * tt * tt) * y1 + (tt * tt * tt - tt * tt) * h * t[s + 1];
    }
    out[i] = clamp(v, 0, 1);
  }
  return out;
}

// ── .cube LUT ───────────────────────────────────────────────────────────

function parseCube(text) {
  var lines = String(text).split(/\r?\n/);
  var size = 0, data = [], domainMin = [0, 0, 0], domainMax = [1, 1, 1], title = "";
  for (var li = 0; li < lines.length; li++) {
    var line = lines[li].trim();
    if (!line || line[0] === "#") continue;
    var parts = line.split(/\s+/);
    var key = parts[0].toUpperCase();
    if (key === "TITLE") title = line.slice(5).trim().replace(/^"|"$/g, "");
    else if (key === "LUT_3D_SIZE") size = parseInt(parts[1], 10);
    else if (key === "DOMAIN_MIN") domainMin = [parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3])];
    else if (key === "DOMAIN_MAX") domainMax = [parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3])];
    else if (key === "LUT_1D_SIZE" || key === "LUT_1D_INPUT_RANGE") return null; // 1D unsupported
    else if (!isNaN(parseFloat(parts[0]))) {
      if (parts.length >= 3) data.push([clamp(parseFloat(parts[0]), 0, 2), clamp(parseFloat(parts[1]), 0, 2), clamp(parseFloat(parts[2]), 0, 2)]);
    }
  }
  if (!size || data.length < size * size * size) return null;
  return { size: size, data: data.slice(0, size * size * size), domainMin: domainMin, domainMax: domainMax, title: title };
}
function sampleLut(lut, r, g, b) {
  var n = lut.size;
  function toGrid(v, c) {
    var lo = lut.domainMin[c], hi = lut.domainMax[c];
    return clamp((v - lo) / Math.max(1e-6, hi - lo), 0, 1) * (n - 1);
  }
  var x = toGrid(r, 0), y = toGrid(g, 1), z = toGrid(b, 2);
  var x0 = Math.floor(x), y0 = Math.floor(y), z0 = Math.floor(z);
  var x1 = Math.min(n - 1, x0 + 1), y1 = Math.min(n - 1, y0 + 1), z1 = Math.min(n - 1, z0 + 1);
  var fx = x - x0, fy = y - y0, fz = z - z0;
  function node(ix, iy, iz) { return lut.data[(iz * n * n + iy * n + ix)]; }
  var out = [0, 0, 0], c;
  for (c = 0; c < 3; c++) {
    var c000 = node(x0, y0, z0)[c], c100 = node(x1, y0, z0)[c];
    var c010 = node(x0, y1, z0)[c], c110 = node(x1, y1, z0)[c];
    var c001 = node(x0, y0, z1)[c], c101 = node(x1, y0, z1)[c];
    var c011 = node(x0, y1, z1)[c], c111 = node(x1, y1, z1)[c];
    var c00 = c000 + (c100 - c000) * fx, c10 = c010 + (c110 - c010) * fx;
    var c01 = c001 + (c101 - c001) * fx, c11 = c011 + (c111 - c011) * fx;
    var c0 = c00 + (c10 - c00) * fy, c1 = c01 + (c11 - c01) * fy;
    out[c] = clamp(c0 + (c1 - c0) * fz, 0, 1);
  }
  return out;
}

// ── Core pixel pipeline (float RGB 0..1, in place) ──────────────────────

function processPixels(data, w, h, recipe, lut, seed) {
  var n = w * h, i, r, g, b;
  var expGain = Math.pow(2, recipe.exposure);
  var brightAdd = recipe.brightness / 100 * 0.25;
  var conAmt = recipe.contrast / 100;
  var conK = 1 + conAmt * 0.9;
  var hiAmt = recipe.highlights / 100, shAmt = recipe.shadows / 100;
  var whAmt = recipe.whites / 100, blAmt = recipe.blacks / 100;
  var tempG = recipe.temp / 100, tintG = recipe.tint / 100;
  var satM = 1 + recipe.saturation / 100;
  var vibM = recipe.vibrance / 100;
  var hueRot = recipe.hue;
  var curveM = bakeCurveTable(recipe.curves.master);
  var curveR = bakeCurveTable(recipe.curves.r);
  var curveG = bakeCurveTable(recipe.curves.g);
  var curveB = bakeCurveTable(recipe.curves.b);
  var lutMix = clamp(recipe.lutIntensity / 100, 0, 1);
  var hasLut = !!(lut && lutMix > 0);
  var mixer = recipe.mixer, grading = recipe.grading;

  for (i = 0; i < n; i++) {
    var o = i * 3;
    r = data[o]; g = data[o + 1]; b = data[o + 2];
    // WB (Bradford approx as channel gains)
    r *= 1 + tempG * 0.22; b *= 1 - tempG * 0.20; g *= 1 - tintG * 0.10;
    r *= 1 + tintG * 0.04; b *= 1 + tintG * 0.04;
    // Light
    r *= expGain; g *= expGain; b *= expGain;
    r += brightAdd; g += brightAdd; b += brightAdd;
    var luma = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    var hiW = smoothstep(0.45, 1.0, luma), shW = 1 - smoothstep(0.0, 0.55, luma);
    var whW = smoothstep(0.7, 1.0, luma), blW = 1 - smoothstep(0.0, 0.3, luma);
    var gain = 1 + hiAmt * 0.55 * hiW + shAmt * 0.55 * shW + whAmt * 0.45 * whW + blAmt * 0.45 * blW;
    r *= gain; g *= gain; b *= gain;
    r = clamp((r - 0.5) * conK + 0.5, 0, 1.5);
    g = clamp((g - 0.5) * conK + 0.5, 0, 1.5);
    b = clamp((b - 0.5) * conK + 0.5, 0, 1.5);
    // Mixer + hue + sat/vibrance in HSL
    var hsl = rgbToHsl(clamp(r, 0, 1), clamp(g, 0, 1), clamp(b, 0, 1));
    var hh = hsl[0], ss = hsl[1], ll = hsl[2];
    var dh = 0, ds = 1, dl = 0;
    for (var bi = 0; bi < 8; bi++) {
      var band = mixer[bi];
      if (!band || (band.h === 0 && band.s === 0 && band.l === 0)) continue;
      var ddeg = Math.abs(hh - BAND_HUES[bi]);
      if (ddeg > 180) ddeg = 360 - ddeg;
      var bw = Math.max(0, Math.cos(ddeg / 180 * Math.PI * 1.5));
      bw = bw * bw * (3 - 2 * bw); // raised-cosine-ish partition
      if (bw <= 0.001) continue;
      dh += band.h / 100 * 28.6 * bw; // ±100 -> ±28.6deg
      ds *= 1 + (band.s / 100) * bw;
      if (ss > 0.02) dl += (band.l / 100) * 0.18 * bw * Math.min(1, ss * 3);
    }
    hh += dh + hueRot;
    ss = clamp(ss * ds * satM * (1 + vibM * (1 - ss)), 0, 1);
    ll = clamp(ll + dl, 0, 1);
    var rgb = hslToRgb(hh, ss, ll);
    r = rgb[0]; g = rgb[1]; b = rgb[2];
    // Grading: zone weights from pre-grade luma
    var lz = clamp(luma, 0, 1);
    var bal = grading.balance / 100;
    var wS = 1 - smoothstep(0.15 + bal * 0.2, 0.55 + bal * 0.2, lz);
    var wH = smoothstep(0.45 + bal * 0.2, 0.85 + bal * 0.2, lz);
    var wM = clamp(1 - wS - wH, 0, 1);
    var zones = [[grading.shadow, wS], [grading.mid, wM], [grading.high, wH], [grading.global, 1]];
    for (var zi = 0; zi < 4; zi++) {
      var zw = zones[zi][1], zc = zones[zi][0];
      if (zw < 0.003 || (zc.s === 0 && zc.l === 0)) continue;
      var tint = hslToRgb(zc.h, clamp(zc.s / 100, 0, 1), 0.5);
      var amt = (zc.s / 100) * 0.09 * zw;
      r += (tint[0] - 0.5) * amt * 2; g += (tint[1] - 0.5) * amt * 2; b += (tint[2] - 0.5) * amt * 2;
      var ladd = (zc.l / 100) * 0.12 * zw;
      r += ladd; g += ladd; b += ladd;
    }
    r = clamp(r, 0, 1); g = clamp(g, 0, 1); b = clamp(b, 0, 1);
    // Curves on display-referred values
    r = curveR[Math.round(curveM[Math.round(r * 255)] * 255)];
    g = curveG[Math.round(curveM[Math.round(g * 255)] * 255)];
    b = curveB[Math.round(curveM[Math.round(b * 255)] * 255)];
    // External LUT
    if (hasLut) {
      var m = sampleLut(lut, r, g, b);
      r = r * (1 - lutMix) + m[0] * lutMix;
      g = g * (1 - lutMix) + m[1] * lutMix;
      b = b * (1 - lutMix) + m[2] * lutMix;
    }
    data[o] = r; data[o + 1] = g; data[o + 2] = b;
  }

  // Dehaze (APPROX dark-channel-prior look: local contrast + saturation)
  if (recipe.dehaze !== 0) {
    var dhAmt = recipe.dehaze / 100;
    var blurD = boxBlur(data, w, h, Math.max(2, Math.round(Math.max(w, h) / 90)));
    for (i = 0; i < n; i++) {
      var p = i * 3;
      for (var c = 0; c < 3; c++) {
        var v = data[p + c], bv = blurD[p + c];
        var diff = (v - bv) / (1 + Math.abs(v - bv) * 8);
        v = v + diff * dhAmt * 0.9;
        var mean = (data[p] + data[p + 1] + data[p + 2]) / 3;
        v = mean + (v - mean) * (1 + dhAmt * 0.25);
        data[p + c] = clamp(v, 0, 1);
      }
    }
  }

  // Spatial detail group (APPROX bilateral/log-clarity/unsharp radii)
  var needDetail = recipe.texture !== 0 || recipe.clarity !== 0 || recipe.structure !== 0 ||
    recipe.sharpen > 0 || recipe.noiseChroma > 0 || recipe.noiseLuma > 0 ||
    recipe.glow > 0 || recipe.halation > 0;
  var smallR = Math.max(1, Math.round(Math.max(w, h) / 500));
  var base = needDetail ? boxBlur(data, w, h, smallR * 2) : null;
  var wide = (recipe.structure !== 0 || recipe.glow > 0) ? boxBlur(data, w, h, Math.max(3, Math.round(Math.min(w, h) / 28))) : null;
  var maskKnee = 0.002, maskAmt = clamp(recipe.detailMasking / 100, 0, 1);
  for (i = 0; i < n; i++) {
    var q = i * 3;
    var cr = data[q], cg = data[q + 1], cb = data[q + 2];
    var lum = 0.2126 * cr + 0.7152 * cg + 0.0722 * cb;
    var gate = 1;
    if (maskAmt > 0 && base) {
      var bl2 = 0.2126 * base[q] + 0.7152 * base[q + 1] + 0.0722 * base[q + 2];
      var hp = lum - bl2, en = hp * hp;
      gate = 1 + maskAmt * ((en / (en + maskKnee)) - 1);
    }
    // Noise reduction first (mix toward blurred base in flat areas)
    if ((recipe.noiseChroma > 0 || recipe.noiseLuma > 0) && base) {
      var nz = (recipe.noiseChroma + recipe.noiseLuma) / 200;
      var flat = 1 - gate * maskAmt; // reuse energy: flat areas smooth more
      var mix = clamp(nz * (0.35 + 0.65 * Math.max(flat, 1 - maskAmt)), 0, 0.9);
      cr += (base[q] - cr) * mix; cg += (base[q + 1] - cg) * mix; cb += (base[q + 2] - cb) * mix;
      lum = 0.2126 * cr + 0.7152 * cg + 0.0722 * cb;
    }
    // Texture
    if (recipe.texture !== 0 && base) {
      var ts = recipe.texture / 100 * 2 * (recipe.texture > 0 ? gate : 1);
      cr = clamp(cr + (cr - base[q]) * ts, 0, 1);
      cg = clamp(cg + (cg - base[q + 1]) * ts, 0, 1);
      cb = clamp(cb + (cb - base[q + 2]) * ts, 0, 1);
      lum = 0.2126 * cr + 0.7152 * cg + 0.0722 * cb;
    }
    // Clarity (soft-knee local contrast w/ anti-halo)
    if (recipe.clarity !== 0 && base) {
      var ca = recipe.clarity / 100 * (recipe.clarity > 0 ? gate : 1);
      var blum = 0.2126 * base[q] + 0.7152 * base[q + 1] + 0.0722 * base[q + 2];
      var d = lum - blum;
      var safe = d / (1 + Math.abs(d) * 10);
      var edge = 1 / (1 + Math.abs(d) * 6);
      var nl = clamp(lum + safe * ca * edge, 0, 1);
      var gr = lum > 0.001 ? nl / lum : 1;
      cr = clamp(cr * gr, 0, 1); cg = clamp(cg * gr, 0, 1); cb = clamp(cb * gr, 0, 1);
      lum = nl;
    }
    // Structure (broad contrast from wide base)
    if (recipe.structure !== 0 && wide) {
      var sa = recipe.structure / 100 * (recipe.structure > 0 ? gate : 1);
      var wlum = 0.2126 * wide[q] + 0.7152 * wide[q + 1] + 0.0722 * wide[q + 2];
      var sd = lum - wlum;
      var sSafe = sd / (1 + Math.abs(sd) * 6);
      var sNl = clamp(lum + sSafe * sa * 1.2, 0, 1);
      var sGr = lum > 0.001 ? sNl / lum : 1;
      cr = clamp(cr * sGr, 0, 1); cg = clamp(cg * sGr, 0, 1); cb = clamp(cb * sGr, 0, 1);
      lum = sNl;
    }
    // Sharpen (asymmetric unsharp, TinyLuma limits 0.20 / -0.12)
    if (recipe.sharpen > 0 && base) {
      var bl3 = 0.2126 * base[q] + 0.7152 * base[q + 1] + 0.0722 * base[q + 2];
      var hp2 = lum - bl3;
      hp2 = hp2 > 0 ? Math.min(hp2, 0.20) : Math.max(hp2, -0.12);
      var delta = hp2 * (recipe.sharpen / 100) * 4 * gate;
      if (lum > 0.001) {
        var ratio = (lum + delta) / lum;
        cr = clamp(cr * ratio, 0, 1); cg = clamp(cg * ratio, 0, 1); cb = clamp(cb * ratio, 0, 1);
        lum = clamp(lum + delta, 0, 1);
      }
    }
    // Glow (warm screen from wide low-pass, highlight-weighted)
    if (recipe.glow > 0 && wide) {
      var ga = recipe.glow / 100;
      var gw = smoothstep(0.45, 0.95, lum);
      cr = clamp(cr + (wide[q] * 0.5 + 0.08) * ga * gw, 0, 1);
      cg = clamp(cg + (wide[q + 1] * 0.35 + 0.03) * ga * gw, 0, 1);
      cb = clamp(cb + wide[q + 2] * 0.2 * ga * gw, 0, 1);
    }
    // Halation (red bleed near highlights)
    if (recipe.halation > 0 && wide) {
      var haA = recipe.halation / 100;
      var hw = smoothstep(0.6, 1.0, 0.2126 * wide[q] + 0.7152 * wide[q + 1] + 0.0722 * wide[q + 2]);
      cr = clamp(cr + haA * hw * 0.35, 0, 1);
      cg = clamp(cg - haA * hw * 0.06, 0, 1);
      cb = clamp(cb - haA * hw * 0.08, 0, 1);
    }
    data[q] = cr; data[q + 1] = cg; data[q + 2] = cb;
  }

  // Flare (APPROX anamorphic streak from brightest percentile)
  if (recipe.flare > 0) {
    var fAmt = recipe.flare / 100;
    var thresh = 0.82, count = 0, sx = 0, sy = 0;
    for (i = 0; i < n; i += 7) {
      var qq = i * 3;
      var ll2 = 0.2126 * data[qq] + 0.7152 * data[qq + 1] + 0.0722 * data[qq + 2];
      if (ll2 > thresh) { count++; sx += i % w; sy += Math.floor(i / w); }
    }
    if (count > 0) {
      var cx = sx / count, cy = sy / count;
      for (var yy = 0; yy < h; yy++) {
        for (var xx = 0; xx < w; xx++) {
          var dy = (yy - cy) / h, dxs = (xx - cx) / w;
          var streak = Math.exp(-Math.abs(dy) * 60) * Math.exp(-Math.abs(dxs) * 4);
          if (streak > 0.01) {
            var pi = (yy * w + xx) * 3;
            data[pi] = clamp(data[pi] + streak * fAmt * 0.5, 0, 1);
            data[pi + 1] = clamp(data[pi + 1] + streak * fAmt * 0.38, 0, 1);
            data[pi + 2] = clamp(data[pi + 2] + streak * fAmt * 0.28, 0, 1);
          }
        }
      }
    }
  }

  // Grain (midtone-weighted mono)
  if (recipe.grain > 0) {
    var gAmt = recipe.grain / 100, gSize = recipe.grainSize;
    var rnd = seed || 42;
    function rand() { rnd = (rnd * 1664525 + 1013904223) >>> 0; return rnd / 4294967296 * 2 - 1; }
    var cell = clamp(Math.round(1 + (100 - gSize) / 100 * 3), 1, 4);
    for (var gy = 0; gy < h; gy++) {
      for (var gx = 0; gx < w; gx++) {
        var pi2 = (gy * w + gx) * 3;
        var ll3 = 0.2126 * data[pi2] + 0.7152 * data[pi2 + 1] + 0.0722 * data[pi2 + 2];
        var paper = Math.sin(Math.min(1, Math.max(0, ll3)) * Math.PI); // strongest in midtones
        var nz2 = ((gx % cell === 0 && gy % cell === 0) || cell === 1) ? rand() : rand() * 0.4;
        var rough = recipe.grainRoughness > 0 ? rand() * (recipe.grainRoughness / 100) * 0.7 : 0;
        var dg = (nz2 * 0.5 + rough) * gAmt * 0.09 * (0.25 + 0.75 * paper);
        data[pi2] = clamp(data[pi2] + dg, 0, 1);
        data[pi2 + 1] = clamp(data[pi2 + 1] + dg, 0, 1);
        data[pi2 + 2] = clamp(data[pi2 + 2] + dg, 0, 1);
      }
    }
  }

  // Vignette (positional, after grain — matches upstream)
  var vAmt = recipe.vignetteAmount / 100;
  if (vAmt !== 0) {
    var mid = recipe.vignetteMidpoint / 100, rnd2 = recipe.vignetteRoundness / 100, fea = 0.3 + (recipe.vignetteFeather / 100) * 1.4;
    var ex = 0.5 * (1 + (1 - rnd2) * 0.25), ey = 0.5 * (1 - (1 - rnd2) * 0.1);
    for (var vy = 0; vy < h; vy++) {
      for (var vx = 0; vx < w; vx++) {
        var nx = (vx / w - 0.5) / Math.max(0.2, ex), ny = (vy / h - 0.5) / Math.max(0.2, ey);
        var dist = Math.sqrt(nx * nx + ny * ny);
        var vig = 1 - smoothstep(mid * 0.9, mid * 0.9 + fea, dist);
        var pi3 = (vy * w + vx) * 3;
        if (vAmt < 0) {
          var dk = 1 + vAmt * (1 - vig);
          data[pi3] *= dk; data[pi3 + 1] *= dk; data[pi3 + 2] *= dk;
        } else {
          data[pi3] += (1 - data[pi3]) * vAmt * (1 - vig) * 0.8;
          data[pi3 + 1] += (1 - data[pi3 + 1]) * vAmt * (1 - vig) * 0.8;
          data[pi3 + 2] += (1 - data[pi3 + 2]) * vAmt * (1 - vig) * 0.8;
        }
      }
    }
  }
  return data;
}

// Spot heal on float buffer (ring-average fill, APPROX Poisson).
function applySpots(data, w, h, spots) {
  if (!spots || !spots.length) return;
  spots.forEach(function (s) {
    var cx = Math.round(s.x * w), cy = Math.round(s.y * h), rad = Math.max(2, Math.round(s.r * Math.max(w, h)));
    var acc = [0, 0, 0], cnt = 0;
    for (var y = cy - rad * 2; y <= cy + rad * 2; y += 2) {
      for (var x = cx - rad * 2; x <= cx + rad * 2; x += 2) {
        if (x < 0 || y < 0 || x >= w || y >= h) continue;
        var d = Math.sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy));
        if (d > rad && d < rad * 2) {
          var p = (y * w + x) * 3;
          acc[0] += data[p]; acc[1] += data[p + 1]; acc[2] += data[p + 2]; cnt++;
        }
      }
    }
    if (!cnt) return;
    acc[0] /= cnt; acc[1] /= cnt; acc[2] /= cnt;
    for (var yy = cy - rad; yy <= cy + rad; yy++) {
      for (var xx = cx - rad; xx <= cx + rad; xx++) {
        if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
        var dd = Math.sqrt((xx - cx) * (xx - cx) + (yy - cy) * (yy - cy));
        if (dd <= rad) {
          var fall = 0.5 + 0.5 * Math.cos(dd / rad * Math.PI);
          var q = (yy * w + xx) * 3;
          data[q] += (acc[0] - data[q]) * fall;
          data[q + 1] += (acc[1] - data[q + 1]) * fall;
          data[q + 2] += (acc[2] - data[q + 2]) * fall;
        }
      }
    }
  });
}

// PNG ancillary-chunk preservation (opt-in; fail-soft on CORS/parse).
var COPYABLE_CHUNKS = { cHRM: 1, gAMA: 1, iCCP: 1, sRGB: 1, tEXt: 1, zTXt: 1, iTXt: 1, eXIf: 1, pHYs: 1, sPLT: 1, tIME: 1 };
function pngChunks(bytes) {
  if (bytes.length < 8 || bytes[0] !== 137 || bytes[1] !== 80) return null;
  var pos = 8, chunks = [];
  while (pos + 8 <= bytes.length) {
    var len = (bytes[pos] << 24) | (bytes[pos + 1] << 16) | (bytes[pos + 2] << 8) | bytes[pos + 3];
    var type = String.fromCharCode(bytes[pos + 4], bytes[pos + 5], bytes[pos + 6], bytes[pos + 7]);
    var end = pos + 12 + len;
    if (end > bytes.length) break;
    chunks.push({ type: type, start: pos, end: end });
    pos = end;
    if (type === "IEND") break;
  }
  return chunks;
}
function injectPngMetadata(pngBytes, srcBytes) {
  try {
    var src = pngChunks(srcBytes), out = pngChunks(pngBytes);
    if (!src || !out) return pngBytes;
    var have = {};
    out.forEach(function (c) { have[c.type] = 1; });
    var insert = [];
    var ihdr = out[0];
    src.forEach(function (c) {
      if (COPYABLE_CHUNKS[c.type] && !have[c.type]) {
        for (var i = c.start; i < c.end; i++) insert.push(srcBytes[i]);
      }
    });
    if (!insert.length) return pngBytes;
    var head = pngBytes.slice(0, ihdr.end), tail = pngBytes.slice(ihdr.end);
    var merged = new Uint8Array(head.length + insert.length + tail.length);
    merged.set(head, 0); merged.set(insert, head.length); merged.set(tail, head.length + insert.length);
    return merged;
  } catch (_e) { return pngBytes; }
}

// ── Styles ──────────────────────────────────────────────────────────────

var CSS = [
  ".pp-ws{display:flex;flex-direction:column;gap:8px;height:min(80vh,940px);min-height:480px;background:#101013;color:#e4e4e7;font-size:12px;outline:none;overflow:hidden}",
  ".pp-native-sidebar{height:auto;min-height:0;overflow:visible;background:transparent;gap:8px;color:var(--color-text-primary,#e4e4e7);font-size:var(--font-size-sm,12px)}",
  ".pp-native-sidebar .pp-toolbar{order:3;flex-wrap:wrap;padding:6px 0;border-top:1px solid var(--color-border,#2b2d35)}",
  ".pp-native-sidebar .pp-toolbar .pp-title{width:100%;font-size:var(--font-size-xs,11px);color:var(--color-text-muted,#9aa0ad)}",
  ".pp-native-sidebar .pp-looks{display:block;max-height:180px;overflow:auto;border:0;border-top:1px solid var(--color-border,#2b2d35);padding:8px 0;background:transparent;order:2}",
  ".pp-native-sidebar .pp-insp{max-height:none;border:0;padding:0;background:transparent;overflow:visible;order:1;display:flex;flex-direction:column}",
  ".pp-native-sidebar .pp-insp>.pp-note{order:90}",
  ".pp-native-sidebar .pp-insp>.pp-hist{order:91}",
  ".pp-native-sidebar .pp-main{display:flex;flex-direction:column;gap:8px}",
  ".pp-native-sidebar .pp-main>.pp-stage{display:none}",
  ".pp-native-sidebar[data-post-category=adjust] .pp-insp .pp-group:not([data-group=light]):not([data-group=output]),.pp-native-sidebar[data-post-category=color] .pp-insp .pp-group:not([data-group=color]):not([data-group=curves]):not([data-group=mixer]):not([data-group=grading]):not([data-group=output]),.pp-native-sidebar[data-post-category=detail] .pp-insp .pp-group:not([data-group=detail]):not([data-group=output]),.pp-native-sidebar[data-post-category=effects] .pp-insp .pp-group:not([data-group=effects]):not([data-group=output]),.pp-native-sidebar[data-post-category=crop] .pp-insp .pp-group:not([data-group=output]),.pp-native-sidebar[data-post-category=heal] .pp-insp .pp-group:not([data-group=output]){display:none}",
  ".pp-native-sidebar .pp-film{max-height:76px;overflow-x:auto;overflow-y:hidden}",
  ".pp-native-sidebar .pp-status{font-size:var(--font-size-xs,11px);color:var(--color-text-muted,#9aa0ad)}",
  ".pp-native-sidebar .pp-dot{background:var(--color-accent,#5a7fdb)}",
  ".pp-native-sidebar .pp-thumb.active{border-color:var(--color-accent,#5a7fdb)}",
  ".pp-native-sidebar .pp-curve-tabs button.on{border-color:var(--color-accent,#5a7fdb)}",
  ".pp-toolbar{flex:none;display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:6px 0;background:transparent;border:0;border-radius:0}",
  ".pp-toolbar .pp-title{font-weight:600;margin-right:auto;letter-spacing:.02em}",
  ".pp-btn{background:var(--color-bg-secondary,#24262e);border:1px solid var(--color-border,#3a3d47);color:var(--color-text-primary,#e4e4e7);border-radius:var(--radius-sm,6px);min-height:30px;padding:5px 10px;cursor:pointer;font-size:var(--font-size-sm,12px);line-height:1.2}",
  ".pp-btn:hover{background:var(--color-bg-tertiary,#30333d)}.pp-btn:disabled{opacity:.45;cursor:default}.pp-btn.on{border-color:var(--color-accent,#5a7fdb);color:var(--color-text-primary,#fff);background:var(--color-accent-muted,rgba(90,127,219,.16))}",
  ".pp-btn.primary{background:var(--color-accent-strong,#3b5cc0);border-color:var(--color-accent-strong,#3b5cc0)}",
  ".pp-main{display:grid;grid-template-columns:220px minmax(0,1fr) 264px;gap:8px;min-height:0;flex:1;overflow:hidden}",
  ".pp-looks,.pp-insp{background:#17171b;border:1px solid #26262c;border-radius:8px;padding:8px;overflow-y:auto;min-height:0;max-height:100%}",
  ".pp-stage{position:relative;background:#0a0a0c;border:1px solid #26262c;border-radius:8px;overflow:auto;min-height:0;display:flex;align-items:center;justify-content:center}",
  ".pp-stage canvas{max-width:100%;max-height:100%;cursor:crosshair}",
  ".pp-film{flex:none}",
  ".pp-status{flex:none}",
  ".pp-compare{position:absolute;top:8px;right:8px;display:flex;gap:6px;align-items:center;background:rgba(10,10,12,.75);padding:4px 8px;border-radius:6px}",
  ".pp-divider{position:absolute;top:0;bottom:0;width:2px;background:#d9a441;cursor:ew-resize}",
  ".pp-divider::after{content:'◂ ▸';position:absolute;top:8px;left:-16px;font-size:10px;background:#d9a441;color:#111;border-radius:4px;padding:1px 4px}",
  ".pp-group{border-bottom:1px solid var(--color-border,#2b2d35);padding:2px 0}",
  ".pp-grouphead{display:flex;align-items:center;gap:7px;width:100%;background:none;border:0;color:var(--color-text-primary,#e4e4e7);cursor:pointer;padding:8px 2px;font-size:var(--font-size-sm,12px);font-weight:600;text-align:left}",
  ".pp-chev{color:var(--color-text-muted,#9aa0ad);width:12px;flex:none}",
  ".pp-insptools{display:flex;gap:4px;margin-bottom:4px}",
  ".pp-dot{width:7px;height:7px;border-radius:50%;background:#d9a441;display:none}.pp-group.has-edits .pp-dot{display:inline-block}",
  ".pp-grouphead .pp-reset{margin-left:auto;font-size:var(--font-size-xs,11px);color:var(--color-accent,#5a7fdb);background:none;border:none;cursor:pointer;text-decoration:underline}",
  ".pp-row{display:grid;grid-template-columns:96px minmax(0,1fr) 52px;gap:8px;align-items:center;padding:5px 0}",
  ".pp-row label{color:var(--color-text-secondary,#b6b6bd);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
  ".pp-row input[type=range]{width:100%;accent-color:var(--color-accent,#5a7fdb);height:18px}",
  ".pp-row input[type=number]{width:52px;box-sizing:border-box;background:var(--color-bg-primary,#17191f);border:1px solid var(--color-border,#3a3d47);color:var(--color-text-primary,#e4e4e7);border-radius:var(--radius-sm,5px);font-size:var(--font-size-xs,11px);padding:4px 5px;min-height:28px}",
  ".pp-note{color:var(--color-text-muted,#9aa0ad);font-size:var(--font-size-xs,11px)}",
  ".pp-film{display:flex;gap:6px;align-items:center;background:#17171b;border:1px solid #26262c;border-radius:8px;padding:6px 8px;overflow-x:auto}",
  ".pp-thumb{width:56px;height:56px;object-fit:cover;border-radius:6px;border:2px solid transparent;cursor:pointer;background:#0a0a0c}",
  ".pp-thumb.active{border-color:#d9a441}",
  ".pp-hist{width:100%;height:38px;background:var(--color-bg-primary,#17191f);border:1px solid var(--color-border,#2b2d35);border-radius:var(--radius-sm,5px)}",
  ".pp-curve-tabs{display:flex;gap:4px;margin:4px 0}",
  ".pp-curve-tabs button.on{border-color:#d9a441}",
  ".pp-status{color:#8b8b94;font-size:11px;min-height:14px}",
  "@media (max-width:1100px){.pp-main{grid-template-columns:minmax(0,1fr) 264px}.pp-looks{display:none}.pp-looks.open{display:block;position:absolute;z-index:5;max-width:260px}}",
  "@media (max-width:800px){.pp-main{grid-template-columns:minmax(0,1fr)}.pp-insp{max-height:300px}}",
].join("\n");
function ensureStyle() {
  if (_styleInjected) return;
  _styleInjected = true;
  var s = document.createElement("style");
  s.setAttribute("data-pp", "1");
  s.textContent = CSS;
  document.head.appendChild(s);
}

// ── Workspace ───────────────────────────────────────────────────────────

var PP_STORE = (typeof window !== "undefined" && window.__ppStore) ||
  { imgs: {}, recipes: {}, undo: {}, redo: {}, luts: [], ui: {} };
if (typeof window !== "undefined") window.__ppStore = PP_STORE;

function itemKeyOf(it) {
  if (!it) return "";
  if (it.file) return "file:" + (it.file.name || "?") + ":" + (it.file.size || 0);
  return "url:" + (it.url || "");
}

export function mountPostprocessWorkspace(host, opts) {
  ensureStyle();
  opts = opts || {};
  var sourceUrl = opts.sourceUrl || "";
  host.innerHTML = "";
  var ws = el("div", { class: "pp-ws" + (opts.nativeSidebar ? " pp-native-sidebar" : ""), "data-testid": "pp-workspace", tabindex: "0" });
  host.appendChild(ws);

  var UI = PP_STORE.ui;
  var S = {
    items: [], active: 0,
    compare: !!UI.compare, comparePos: UI.comparePos || 50,
    zoom: UI.zoom || 0, // 0=fit, else scale
    tool: null, // tools never survive a remount mid-gesture; reset deliberately
    brushR: UI.brushR || 0.02, brushHard: UI.brushHard || 0.7,
    undo: [], redo: [],
    luts: PP_STORE.luts, lutFav: storeGet(LS_LUTFAV, {}),
    cropDrag: null, healDrag: false,
    renderRev: 0, sourceBytes: null,
  };
  function persistUi() {
    PP_STORE.ui = {
      compare: S.compare, comparePos: S.comparePos, zoom: S.zoom,
      brushR: S.brushR, brushHard: S.brushHard,
    };
  }
  function bindStacks() {
    var k = itemKeyOf(cur());
    if (!PP_STORE.undo[k]) PP_STORE.undo[k] = [];
    if (!PP_STORE.redo[k]) PP_STORE.redo[k] = [];
    S.undo = PP_STORE.undo[k];
    S.redo = PP_STORE.redo[k];
    syncUndoBtns();
  }
  window.__ppRecipe = null;

  // Toolbar
  var toolbar = el("div", { class: "pp-toolbar", "data-testid": "pp-toolbar" });
  var title = el("span", { class: "pp-title", text: "Post Processing · TinyLuma engine" });
  toolbar.appendChild(title);
  function btn(label, testid, titleText, fn) {
    var b = el("button", { type: "button", class: "pp-btn", "data-testid": testid, text: label, title: titleText || label });
    b.addEventListener("click", fn);
    toolbar.appendChild(b);
    return b;
  }
  var undoBtn = btn("↩ Undo", "pp-undo", "Undo (Ctrl+Z)", doUndo);
  var redoBtn = btn("↪ Redo", "pp-redo", "Redo (Ctrl+Y)", doRedo);
  var cmpBtn = btn("◑ Compare", "pp-compare", "Before / after ( \\)", function () { S.compare = !S.compare; cmpBtn.classList.toggle("on", S.compare); persistUi(); refreshCompare(); });
  cmpBtn.classList.toggle("on", S.compare);
  var cropBtn = btn("⛶ Crop", "pp-crop", "Crop tool (C)", function () { setTool(S.tool === "crop" ? null : "crop"); });
  var healBtn = btn("◍ Heal", "pp-heal", "Spot heal (J)", function () { setTool(S.tool === "heal" ? null : "heal"); });
  var wbBtn = btn("WB", "pp-wb", "White-balance picker (W)", function () { setTool(S.tool === "wb" ? null : "wb"); });
  btn("Save", "pp-save", "Store recipe locally", saveRecipe);
  btn("Export", "pp-export", "Render full-res and download", doExport);
  ws.appendChild(toolbar);

  // Main grid
  var main = el("div", { class: "pp-main" });
  ws.appendChild(main);
  var looks = el("div", { class: "pp-looks", "data-testid": "pp-looks" });
  var stage = el("div", { class: "pp-stage", "data-testid": "pp-canvas" });
  var insp = el("div", { class: "pp-insp", "data-testid": "pp-inspector" });
  main.appendChild(looks); main.appendChild(stage); main.appendChild(insp);

  var view = document.createElement("canvas");
  view.setAttribute("data-testid", "pp-view");
  stage.appendChild(view);
  var cmpBar = el("div", { class: "pp-compare" });
  var cmpLabel = el("span", { class: "pp-note", text: "compare off (\\ toggles)" });
  cmpBar.appendChild(cmpLabel);
  stage.appendChild(cmpBar);
  var divider = el("div", { class: "pp-divider", "data-testid": "pp-compare-divider", style: "display:none;left:50%" });
  stage.appendChild(divider);

  var film = el("div", { class: "pp-film", "data-testid": "pp-filmstrip" });
  ws.appendChild(film);
  var status = el("div", { class: "pp-status", "data-testid": "pp-status" });
  ws.appendChild(status);
  function say(t) { status.textContent = t || ""; }

  // ── Items / recipes ──
  function cur() { return S.items[S.active]; }
  function recipe() { var c = cur(); return c ? c.recipe : null; }
  function snapshot() { return clone(recipe()); }
  // Undo checkpoint. `before` is the PRE-mutation state; when omitted the
  // current state is stored (correct only for call sites that checkpoint
  // before mutating). Slider gestures capture it on first input.
  function commit(label, before) {
    if (!cur()) return;
    S.undo.push({
      label: label || "edit", item: S.active,
      state: (before !== undefined && before !== null) ? before : snapshot(),
    });
    if (S.undo.length > 80) S.undo.shift();
    S.redo.length = 0;
    syncUndoBtns();
  }
  function doUndo() {
    var u = S.undo.pop();
    if (!u) return;
    S.redo.push({ item: u.item, state: snapshot() });
    S.items[u.item].recipe = u.state;
    S.active = u.item;
    afterRecipeChange();
    syncUndoBtns();
  }
  function doRedo() {
    var r = S.redo.pop();
    if (!r) return;
    S.undo.push({ item: r.item, state: snapshot() });
    S.items[r.item].recipe = r.state;
    S.active = r.item;
    afterRecipeChange();
    syncUndoBtns();
  }
  function syncUndoBtns() { undoBtn.disabled = !S.undo.length; redoBtn.disabled = !S.redo.length; }
  syncUndoBtns();

  function addItem(name, url, file) {
    var probe = { url: url || "", file: file || null };
    var key = itemKeyOf(probe);
    for (var ei = 0; ei < S.items.length; ei++) {
      if (itemKeyOf(S.items[ei]) === key) { loadItem(ei); return S.items[ei]; }
    }
    var item = { id: uid(), name: name || "image", url: url || "", file: file || null, img: PP_STORE.imgs[key] || null, recipe: defaultRecipe(), lut: null };
    if (PP_STORE.recipes[key]) item.recipe = Object.assign(defaultRecipe(), clone(PP_STORE.recipes[key]));
    else {
      var saved = storeGet(LS_RECIPE, null);
      if (saved && url && saved.url === url && saved.recipe) item.recipe = Object.assign(defaultRecipe(), saved.recipe);
    }
    // Re-link a previously imported LUT by id.
    if (item.recipe.lutId && PP_STORE.luts) {
      for (var li = 0; li < PP_STORE.luts.length; li++) {
        if (PP_STORE.luts[li].id === item.recipe.lutId) { item.lut = PP_STORE.luts[li]; break; }
      }
    }
    S.items.push(item);
    if (S.items.length === 1) S.active = 0;
    PP_STORE.session = PP_STORE.session || [];
    PP_STORE.files = PP_STORE.files || {};
    var recorded = PP_STORE.session.some(function (e) { return e && e.key === key; });
    if (!recorded) PP_STORE.session.push({ key: key, kind: file ? "file" : "url", name: item.name, url: item.url });
    if (file) PP_STORE.files[key] = file;
    renderFilm();
    loadItem(S.items.length - 1);
    return item;
  }

  // Rebuild the filmstrip session after a Studio re-render (same document):
  // images, recipes, and undo stacks come from the module store — no
  // re-upload, no pixel refetch.
  function restoreSession() {
    var sess = PP_STORE.session || [];
    PP_STORE.files = PP_STORE.files || {};
    sess.forEach(function (entry) {
      if (!entry) return;
      if (entry.kind === "file") {
        var f = PP_STORE.files[entry.key];
        if (f) addItem(entry.name, "", f);
      } else if (entry.url) {
        addItem(entry.name, entry.url, null);
      }
    });
  }

  function loadItem(idx) {
    S.active = idx;
    var item = cur();
    if (!item) return;
    bindStacks();
    renderFilm(); buildInspector(); renderLooks();
    if (item.img && item.img.complete && item.img.naturalWidth) {
      prepareCanvases(item);
      render();
      return;
    }
    say("Loading image…");
    var img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = function () {
      item.img = img;
      PP_STORE.imgs[itemKeyOf(item)] = img;
      prepareCanvases(item);
      say("");
      render();
    };
    img.onerror = function () { say("Could not load source pixels (remote file may block cross-origin reads). Upload the file instead."); };
    if (item.file) img.src = URL.createObjectURL(item.file);
    else img.src = item.url;
    // Keep source bytes for PNG metadata preservation (fail-soft).
    if (item.url && !item.file) {
      fetch(item.url).then(function (r) { return r.arrayBuffer(); }).then(function (buf) {
        item.srcBytes = new Uint8Array(buf);
      }).catch(function () {});
    } else if (item.file && /png$/i.test(item.file.name || "")) {
      item.file.arrayBuffer().then(function (buf) { item.srcBytes = new Uint8Array(buf); }).catch(function () {});
    }
  }

  // ── Canvases ──
  var srcCanvas = document.createElement("canvas"); // full-res source
  var workCanvas = document.createElement("canvas"); // preview-res working
  function prepareCanvases(item) {
    var iw = item.img.naturalWidth, ih = item.img.naturalHeight;
    srcCanvas.width = iw; srcCanvas.height = ih;
    srcCanvas.getContext("2d").drawImage(item.img, 0, 0);
    var sc = Math.min(1, PREVIEW_MAX / Math.max(iw, ih));
    workCanvas.width = Math.max(1, Math.round(iw * sc));
    workCanvas.height = Math.max(1, Math.round(ih * sc));
    workCanvas.getContext("2d").drawImage(item.img, 0, 0, workCanvas.width, workCanvas.height);
  }

  var renderQueued = false;
  function scheduleRender() {
    persistUi(); // every visual change is remount-safe (memory-only write)
    if (renderQueued) return;
    renderQueued = true;
    requestAnimationFrame(function () { renderQueued = false; render(); });
  }
  function currentLut() { var c = cur(); return c ? c.lut : null; }

  function render() {
    var item = cur();
    if (!item || !item.img) return;
    var t0 = (typeof performance !== "undefined" && performance.now) ? performance.now() : 0;
    var r = item.recipe;
    window.__ppRecipe = { url: item.url, name: item.name, recipe: clone(r) };
    try {
      var wctx = workCanvas.getContext("2d");
      // Rebuild working buffer from source each render (heal first, like upstream).
      var w = workCanvas.width, h = workCanvas.height;
      wctx.drawImage(item.img, 0, 0, w, h);
      var id = wctx.getImageData(0, 0, w, h);
      var f = new Float32Array(w * h * 3);
      for (var i = 0; i < w * h; i++) {
        f[i * 3] = srgbToLin(id.data[i * 4] / 255);
        f[i * 3 + 1] = srgbToLin(id.data[i * 4 + 1] / 255);
        f[i * 3 + 2] = srgbToLin(id.data[i * 4 + 2] / 255);
      }
      // Heal runs on linear base before color (matches upstream order).
      applySpots(f, w, h, r.spots);
      // Color pipeline works display-referred; convert back for engine parity.
      for (var k = 0; k < w * h; k++) {
        f[k * 3] = linToSrgb(clamp(f[k * 3], 0, 1));
        f[k * 3 + 1] = linToSrgb(clamp(f[k * 3 + 1], 0, 1));
        f[k * 3 + 2] = linToSrgb(clamp(f[k * 3 + 2], 0, 1));
      }
      processPixels(f, w, h, r, currentLut(), 42);
      var out = wctx.createImageData(w, h);
      for (var j = 0; j < w * h; j++) {
        out.data[j * 4] = clamp(f[j * 3], 0, 1) * 255;
        out.data[j * 4 + 1] = clamp(f[j * 3 + 1], 0, 1) * 255;
        out.data[j * 4 + 2] = clamp(f[j * 3 + 2], 0, 1) * 255;
        out.data[j * 4 + 3] = 255;
      }
      // Crop + straighten at draw time (non-destructive recipe).
      drawResult(item, out);
      drawHistogram(f, w, h);
      markEditedGroups();
      if (t0) {
        try { window.__ppLastRenderMs = Math.round(performance.now() - t0); } catch (_e) {}
        window.__ppRenderCount = (window.__ppRenderCount || 0) + 1;
      }
    } catch (e) {
      try { window.__ppLastRenderError = String((e && e.message) || e); } catch (_e2) {}
      say("Render failed: " + (e && e.message));
    }
  }

  function drawResult(item, processed) {
    var r = item.recipe;
    var tmp = document.createElement("canvas");
    tmp.width = processed.width; tmp.height = processed.height;
    tmp.getContext("2d").putImageData(processed, 0, 0);
    var cw = processed.width, ch = processed.height;
    var sx = Math.round(r.crop.x * cw), sy = Math.round(r.crop.y * ch);
    var sw = Math.max(1, Math.round(r.crop.w * cw)), sh = Math.max(1, Math.round(r.crop.h * ch));
    var ang = (r.crop.angle || 0) * Math.PI / 180;
    var vw = ang !== 0 ? Math.round(Math.abs(sw * Math.cos(ang)) + Math.abs(sh * Math.sin(ang))) : sw;
    var vh = ang !== 0 ? Math.round(Math.abs(sw * Math.sin(ang)) + Math.abs(sh * Math.cos(ang))) : sh;
    view.width = vw; view.height = vh;
    var vctx = view.getContext("2d");
    vctx.fillStyle = "#0a0a0c"; vctx.fillRect(0, 0, vw, vh);
    vctx.save();
    vctx.translate(vw / 2, vh / 2);
    if (ang !== 0) vctx.rotate(ang);
    vctx.drawImage(tmp, sx, sy, sw, sh, -sw / 2, -sh / 2, sw, sh);
    vctx.restore();
    applyZoom();
    refreshCompare();
  }

  function applyZoom() {
    if (S.zoom && S.zoom > 0) {
      view.style.width = Math.round(view.width * S.zoom) + "px";
      view.style.maxWidth = "none"; view.style.maxHeight = "none";
    } else {
      view.style.width = ""; view.style.maxWidth = "100%"; view.style.maxHeight = "62vh";
    }
  }

  function refreshCompare() {
    persistUi();
    var on = S.compare && cur() && cur().img;
    divider.style.display = on ? "block" : "none";
    cmpLabel.textContent = on ? ("after " + S.comparePos + "% — \\ toggles") : "compare off (\\ toggles)";
    if (!on) { view.style.clipPath = ""; return; }
    view.style.clipPath = "inset(0 0 0 " + S.comparePos + "%)";
    divider.style.left = S.comparePos + "%";
  }

  // ── Inspector ──
  var groupMeta = [];
  function sliderRow(parent, label, min, max, step, get, set, fmt) {
    var slug = String(label).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    var row = el("div", { class: "pp-row", "data-testid": "pp-slider-" + slug });
    var lab = el("label", { text: label, title: label + " (double-click resets)" });
    var range = document.createElement("input");
    range.type = "range"; range.min = min; range.max = max; range.step = step; range.value = get();
    var num = document.createElement("input");
    num.type = "number"; num.min = min; num.max = max; num.step = step; num.value = get();
    function show(v) { num.value = fmt ? fmt(v) : v; }
    var gestureBefore = null; // pre-drag snapshot: one undo step per gesture
    range.addEventListener("input", function () {
      if (gestureBefore === null) gestureBefore = snapshot();
      set(parseFloat(range.value)); show(range.value); markEditedGroups(); scheduleRender();
    });
    range.addEventListener("change", function () { commit(label, gestureBefore); gestureBefore = null; saveDraft(); });
    num.addEventListener("change", function () {
      var v = clamp(parseFloat(num.value) || 0, min, max);
      var before = snapshot();
      range.value = v; set(v); commit(label, before); show(v); markEditedGroups(); scheduleRender(); saveDraft();
    });
    lab.addEventListener("dblclick", function () {
      var d = defaultRecipe();
      var key = row.getAttribute("data-key");
      if (key && d[key] !== undefined) {
        var before2 = snapshot();
        set(d[key]); range.value = d[key]; show(d[key]);
        commit(label + " reset", before2); markEditedGroups(); scheduleRender(); saveDraft();
      }
    });
    row.appendChild(lab); row.appendChild(range); row.appendChild(num);
    row.setAttribute("data-key", label);
    parent.appendChild(row);
    row._sync = function () { range.value = get(); show(get()); };
    return row;
  }

  var LS_GROUPS = "comfymodal.studio.postprocess.groups.v1";
  function groupOpenState() { return storeGet(LS_GROUPS, { light: true }) || {}; }
  function setGroupOpen(id, open) {
    var st = groupOpenState();
    st[id] = !!open;
    storeSet(LS_GROUPS, st);
  }
  function group(parent, id, title, keys, build, openDefault) {
    var g = el("div", { class: "pp-group", "data-group": id });
    var head = el("button", { type: "button", class: "pp-grouphead", "aria-expanded": "false" });
    var chev = el("span", { class: "pp-chev", text: "▸", "aria-hidden": "true" });
    head.appendChild(chev);
    head.appendChild(el("span", { class: "pp-dot" }));
    head.appendChild(el("span", { text: title }));
    var rst = el("span", { class: "pp-reset", text: "reset", role: "button", tabindex: "0" });
    rst.addEventListener("click", function (e) {
      e.stopPropagation();
      var d = defaultRecipe(), r = recipe();
      var before = snapshot();
      keys.forEach(function (k) { r[k] = clone(d[k]); });
      commit(title + " reset", before); buildInspector(); scheduleRender(); saveDraft();
    });
    head.appendChild(rst);
    var body = el("div", { class: "pp-groupbody" });
    var st = groupOpenState();
    var isOpen = st[id] !== undefined ? !!st[id] : !!openDefault;
    function applyOpen() {
      body.style.display = isOpen ? "" : "none";
      chev.textContent = isOpen ? "▾" : "▸";
      head.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }
    head.addEventListener("click", function () { isOpen = !isOpen; setGroupOpen(id, isOpen); applyOpen(); });
    g.appendChild(head); g.appendChild(body);
    parent.appendChild(g);
    groupMeta.push({ id: id, keys: keys, el: g, setOpen: function (o) { isOpen = !!o; setGroupOpen(id, isOpen); applyOpen(); } });
    build(body);
    applyOpen();
    return body;
  }
  function setAllGroups(open) {
    groupMeta.forEach(function (gm) { if (gm.setOpen) gm.setOpen(open); });
  }

  function markEditedGroups() {
    var r = recipe(), d = defaultRecipe();
    if (!r) return;
    groupMeta.forEach(function (gm) {
      var edited = gm.keys.some(function (k) { return JSON.stringify(r[k]) !== JSON.stringify(d[k]); });
      gm.el.classList.toggle("has-edits", edited);
    });
    var rows = insp.querySelectorAll(".pp-row");
    rows.forEach(function (row) { if (row._sync) { try { row._sync(); } catch (_e) {} } });
  }

  function buildInspector() {
    insp.innerHTML = ""; groupMeta = [];
    var r = recipe();
    if (!r) { insp.appendChild(el("p", { class: "pp-note", text: "Pick or upload an image to edit." })); return; }
    // Histogram is useful context, but stays a quiet secondary strip.
    insp.appendChild(el("div", { class: "pp-note", text: "Histogram", style: "margin:4px 0" }));
    var hc = document.createElement("canvas");
    hc.className = "pp-hist"; hc.width = 248; hc.height = 64;
    hc.setAttribute("data-testid", "pp-histogram");
    insp.appendChild(hc);
    insp._hist = hc;

    group(insp, "light", "Light", ["exposure", "brightness", "contrast", "highlights", "shadows", "whites", "blacks"], function (b) {
      [["Exposure", -5, 5, 0.1, "exposure"], ["Brightness", -100, 100, 1, "brightness"],
       ["Contrast", -100, 100, 1, "contrast"], ["Highlights", -100, 100, 1, "highlights"],
       ["Shadows", -100, 100, 1, "shadows"], ["Whites", -100, 100, 1, "whites"],
       ["Blacks", -100, 100, 1, "blacks"]].forEach(function (s) {
        sliderRow(b, s[0], s[1], s[2], s[3], function () { return r[s[4]]; }, function (v) { r[s[4]] = v; }).setAttribute("data-key", s[4]);
      });
    }, true);
    group(insp, "color", "Color", ["temp", "tint", "hue", "saturation", "vibrance"], function (b) {
      [["Temperature", -100, 100, 1, "temp"], ["Tint", -100, 100, 1, "tint"],
       ["Hue", -180, 180, 1, "hue"], ["Saturation", -100, 100, 1, "saturation"],
       ["Vibrance", -100, 100, 1, "vibrance"]].forEach(function (s) {
        sliderRow(b, s[0], s[1], s[2], s[3], function () { return r[s[4]]; }, function (v) { r[s[4]] = v; }).setAttribute("data-key", s[4]);
      });
      var pick = el("button", { type: "button", class: "pp-btn", text: "WB picker (W)", title: "Click the image to sample neutral gray" });
      pick.addEventListener("click", function () { setTool("wb"); });
      b.appendChild(pick);
    });
    group(insp, "curves", "Curves", ["curves"], function (b) { buildCurveEditor(b, r); }, false);
    group(insp, "mixer", "Color mixer", ["mixer"], function (b) { buildMixer(b, r); }, false);
    group(insp, "grading", "Color grading", ["grading"], function (b) { buildGrading(b, r); }, false);
    group(insp, "detail", "Details", ["texture", "clarity", "structure", "sharpen", "detailMasking", "dehaze", "noiseChroma", "noiseLuma", "noiseDetail"], function (b) {
      [["Texture", -100, 100, 1, "texture"], ["Clarity", -100, 100, 1, "clarity"],
       ["Structure", -100, 100, 1, "structure"], ["Sharpen", 0, 150, 1, "sharpen"],
       ["Detail masking", 0, 100, 1, "detailMasking"], ["Dehaze", -100, 100, 1, "dehaze"],
       ["NR chroma", 0, 100, 1, "noiseChroma"], ["NR luma", 0, 100, 1, "noiseLuma"],
       ["NR detail", 0, 100, 1, "noiseDetail"]].forEach(function (s) {
        sliderRow(b, s[0], s[1], s[2], s[3], function () { return r[s[4]]; }, function (v) { r[s[4]] = v; }).setAttribute("data-key", s[4]);
      });
    });
    group(insp, "effects", "Effects", ["grain", "grainSize", "grainRoughness", "vignetteAmount", "vignetteMidpoint", "vignetteRoundness", "vignetteFeather", "glow", "halation", "flare", "lutIntensity"], function (b) {
      [["Grain", 0, 100, 1, "grain"], ["Grain size", 0, 100, 1, "grainSize"],
       ["Grain roughness", 0, 100, 1, "grainRoughness"], ["Glow", 0, 100, 1, "glow"],
       ["Halation", 0, 100, 1, "halation"], ["Light flares", 0, 100, 1, "flare"],
       ["Vignette", -100, 100, 1, "vignetteAmount"], ["V. midpoint", 0, 100, 1, "vignetteMidpoint"],
       ["V. roundness", -100, 100, 1, "vignetteRoundness"], ["V. feather", 0, 100, 1, "vignetteFeather"],
       ["LUT intensity", 0, 100, 1, "lutIntensity"]].forEach(function (s) {
        sliderRow(b, s[0], s[1], s[2], s[3], function () { return r[s[4]]; }, function (v) { r[s[4]] = v; }).setAttribute("data-key", s[4]);
      });
    });
    group(insp, "output", "Output", ["format", "quality", "embedMetadata"], function (b) {
      var fr = el("div", { class: "pp-row" });
      fr.appendChild(el("label", { text: "Format" }));
      var sel = document.createElement("select");
      ["png", "jpeg", "webp"].forEach(function (f) {
        var o = document.createElement("option"); o.value = f; o.textContent = f.toUpperCase();
        if (r.format === f) o.selected = true;
        sel.appendChild(o);
      });
      sel.addEventListener("change", function () { commit("format"); r.format = sel.value; saveDraft(); });
      fr.appendChild(sel);
      var q = document.createElement("input");
      q.type = "number"; q.min = 1; q.max = 100; q.value = r.quality;
      q.addEventListener("change", function () { commit("quality"); r.quality = clamp(parseInt(q.value, 10) || 90, 1, 100); saveDraft(); });
      fr.appendChild(q);
      b.appendChild(fr);
      sliderRow(b, "Quality", 1, 100, 1, function () { return r.quality; }, function (v) { r.quality = Math.round(v); markEditedGroups(); }).setAttribute("data-key", "quality");
      var mrow = el("div", { class: "pp-row" });
      mrow.appendChild(el("label", { text: "Keep PNG metadata" }));
      var chk = document.createElement("input");
      chk.type = "checkbox"; chk.checked = !!r.embedMetadata;
      chk.addEventListener("change", function () { commit("metadata"); r.embedMetadata = chk.checked; saveDraft(); });
      mrow.appendChild(chk);
      mrow.appendChild(el("span", { class: "pp-note", text: "tEXt/zTXt/iTXt/eXIf passthrough" }));
      b.appendChild(mrow);
    });
    markEditedGroups();
  }

  function drawHistogram(f, w, h) {
    var hc = insp._hist;
    if (!hc) return;
    var ctx = hc.getContext("2d");
    ctx.clearRect(0, 0, hc.width, hc.height);
    var bins = [new Array(64).fill(0), new Array(64).fill(0), new Array(64).fill(0)];
    for (var i = 0; i < w * h; i += 3) {
      bins[0][Math.min(63, (f[i * 3] * 64) | 0)]++;
      bins[1][Math.min(63, (f[i * 3 + 1] * 64) | 0)]++;
      bins[2][Math.min(63, (f[i * 3 + 2] * 64) | 0)]++;
    }
    var mx = 1;
    bins.forEach(function (b) { b.forEach(function (v) { if (v > mx) mx = v; }); });
    var cols = ["rgba(248,113,113,.85)", "rgba(74,222,128,.85)", "rgba(96,165,250,.85)"];
    bins.forEach(function (b, bi) {
      ctx.fillStyle = cols[bi];
      for (var x = 0; x < 64; x++) {
        var hh = b[x] / mx * hc.height;
        ctx.fillRect(x * hc.width / 64, hc.height - hh, hc.width / 64 - 0.5, hh);
      }
    });
  }

  // ── Curve editor ──
  function buildCurveEditor(parent, r) {
    var tabs = el("div", { class: "pp-curve-tabs" });
    var svgWrap = el("div", {});
    parent.appendChild(tabs); parent.appendChild(svgWrap);
    var chan = "master";
    var chanBtns = {};
    ["master", "r", "g", "b"].forEach(function (c) {
      var b2 = el("button", { type: "button", class: "pp-btn" + (c === chan ? " on" : ""), text: c === "master" ? "Master" : c.toUpperCase() });
      b2.addEventListener("click", function () { chan = c; Object.keys(chanBtns).forEach(function (k) { chanBtns[k].classList.toggle("on", k === c); }); draw(); });
      chanBtns[c] = b2; tabs.appendChild(b2);
    });
    var NS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("width", "232"); svg.setAttribute("height", "150");
    svg.style.background = "#0a0a0c"; svg.style.border = "1px solid #34343c"; svg.style.borderRadius = "6px";
    svgWrap.appendChild(svg);
    svgWrap.appendChild(el("p", { class: "pp-note", text: "Click adds a point (max 16) · drag moves · double-click removes · endpoints stay." }));
    function draw() {
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      var pts = r.curves[chan];
      var table = bakeCurveTable(pts);
      var path = "";
      for (var i = 0; i < 256; i += 2) {
        var X = 8 + (i / 255) * 216, Y = 142 - table[i] * 134;
        path += (i === 0 ? "M" : "L") + X.toFixed(1) + " " + Y.toFixed(1);
      }
      var p = document.createElementNS(NS, "path");
      p.setAttribute("d", path); p.setAttribute("stroke", "#5a7fdb"); p.setAttribute("fill", "none"); p.setAttribute("stroke-width", "1.5");
      svg.appendChild(p);
      pts.forEach(function (pt, idx) {
        var c = document.createElementNS(NS, "circle");
        c.setAttribute("cx", 8 + pt[0] * 216); c.setAttribute("cy", 142 - pt[1] * 134);
        c.setAttribute("r", idx === 0 || idx === pts.length - 1 ? 4 : 5);
        c.setAttribute("fill", "#e4e4e7"); c.style.cursor = "grab";
        c.addEventListener("dblclick", function (e) {
          e.stopPropagation();
          if (idx > 0 && idx < pts.length - 1) {
            var before = snapshot();
            pts.splice(idx, 1); commit("curve point", before); draw(); scheduleRender(); saveDraft();
          }
        });
        c.addEventListener("pointerdown", function (e) {
          e.stopPropagation(); c.setPointerCapture(e.pointerId);
          var dragBefore = snapshot();
          function mv(ev) {
            var rect = svg.getBoundingClientRect();
            var nx = clamp((ev.clientX - rect.left - 8) / 216, 0, 1);
            var ny = clamp(1 - (ev.clientY - rect.top - 8) / 134, 0, 1);
            if (idx === 0) nx = 0; if (idx === pts.length - 1) nx = 1;
            var prev = pts[idx - 1], next = pts[idx + 1];
            if (prev) nx = Math.max(nx, prev[0] + 1 / 4096);
            if (next) nx = Math.min(nx, next[0] - 1 / 4096);
            pt[0] = nx; pt[1] = ny; draw(); scheduleRender();
          }
          function up() { c.removeEventListener("pointermove", mv); c.removeEventListener("pointerup", up); commit("curve", dragBefore); saveDraft(); }
          c.addEventListener("pointermove", mv); c.addEventListener("pointerup", up);
        });
        svg.appendChild(c);
      });
    }
    svg.addEventListener("dblclick", function () {});
    svg.addEventListener("click", function (e) {
      if (e.target !== svg) return;
      var pts = r.curves[chan];
      if (pts.length >= 16) { say("Curve point limit is 16."); return; }
      var rect = svg.getBoundingClientRect();
      var nx = clamp((e.clientX - rect.left - 8) / 216, 0, 1);
      var ny = clamp(1 - (e.clientY - rect.top - 8) / 134, 0, 1);
      var before = snapshot();
      pts.push([nx, ny]); pts.sort(function (a, b2) { return a[0] - b2[0]; });
      commit("curve point", before); draw(); scheduleRender(); saveDraft();
    });
    draw();
  }

  // ── Mixer / grading ──
  function buildMixer(parent, r) {
    MIXER_BANDS.forEach(function (name, bi) {
      parent.appendChild(el("div", { class: "pp-note", text: name, style: "font-weight:600;margin-top:4px" }));
      [["H", -100, 100, "h"], ["S", -100, 100, "s"], ["L", -100, 100, "l"]].forEach(function (s) {
        sliderRow(parent, name + " " + s[0], s[1], s[2], 1,
          function () { return r.mixer[bi][s[3]]; },
          function (v) { r.mixer[bi][s[3]] = v; }).setAttribute("data-key", "mixer");
      });
    });
  }
  function buildGrading(parent, r) {
    [["Shadows", "shadow"], ["Midtones", "mid"], ["Highlights", "high"], ["Global", "global"]].forEach(function (g) {
      parent.appendChild(el("div", { class: "pp-note", text: g[0], style: "font-weight:600;margin-top:4px" }));
      sliderRow(parent, g[0] + " hue", 0, 360, 1, function () { return r.grading[g[1]].h; }, function (v) { r.grading[g[1]].h = v; }).setAttribute("data-key", "grading");
      sliderRow(parent, g[0] + " sat", 0, 100, 1, function () { return r.grading[g[1]].s; }, function (v) { r.grading[g[1]].s = v; }).setAttribute("data-key", "grading");
      sliderRow(parent, g[0] + " lum", -100, 100, 1, function () { return r.grading[g[1]].l; }, function (v) { r.grading[g[1]].l = v; }).setAttribute("data-key", "grading");
    });
    sliderRow(parent, "Blending", 0, 100, 1, function () { return r.grading.blend; }, function (v) { r.grading.blend = v; }).setAttribute("data-key", "grading");
    sliderRow(parent, "Balance", -100, 100, 1, function () { return r.grading.balance; }, function (v) { r.grading.balance = v; }).setAttribute("data-key", "grading");
  }

  // ── Looks (presets + LUT) ──
  function renderLooks() {
    looks.innerHTML = "";
    looks.appendChild(el("div", { class: "pp-note", text: "Looks", style: "font-weight:700;font-size:13px" }));
    if (!cur() || !recipe()) {
      looks.appendChild(el("p", { class: "pp-note", text: "Presets and LUTs appear once an image is loaded." }));
      return;
    }
    var user = storeGet(LS_PRESETS, []);
    looks.appendChild(el("div", { class: "pp-note", text: "Presets", style: "font-weight:600;margin-top:6px" }));
    BUILTIN_PRESETS.concat(user).forEach(function (p) {
      var b = el("button", { type: "button", class: "pp-btn", text: p.name, style: "display:block;width:100%;margin:2px 0;text-align:left" });
      b.addEventListener("click", function () {
        var keep = recipe(); var incoming = clone(p.recipe);
        incoming.crop = keep.crop; incoming.spots = keep.spots; // presets carry look, not geometry
        commit("preset " + p.name);
        cur().recipe = incoming;
        buildInspector(); scheduleRender(); saveDraft();
      });
      looks.appendChild(b);
    });
    var saveRow = el("div", { style: "display:flex;gap:4px;margin:6px 0" });
    var nameIn = document.createElement("input");
    nameIn.placeholder = "Preset name"; nameIn.style.flex = "1";
    nameIn.className = "pp-btn"; nameIn.style.cursor = "text";
    var saveB = el("button", { type: "button", class: "pp-btn", text: "Save" });
    saveB.addEventListener("click", function () {
      var nm = (nameIn.value || "").trim() || ("Look " + (user.length + 1));
      user.push({ name: nm, recipe: snapshot() });
      storeSet(LS_PRESETS, user); renderLooks(); say("Preset saved: " + nm);
    });
    saveRow.appendChild(nameIn); saveRow.appendChild(saveB);
    looks.appendChild(saveRow);
    var allB = el("button", { type: "button", class: "pp-btn", text: "Apply look to all", title: "Copy current look (not crop/spots) to every filmstrip image" });
    allB.addEventListener("click", function () {
      var src = snapshot();
      commit("apply to all");
      S.items.forEach(function (it, idx) {
        if (idx === S.active) return;
        var keepCrop = it.recipe.crop, keepSpots = it.recipe.spots;
        it.recipe = clone(src); it.recipe.crop = keepCrop; it.recipe.spots = keepSpots;
      });
      scheduleRender(); saveDraft(); say("Look applied to " + S.items.length + " images.");
    });
    looks.appendChild(allB);

    looks.appendChild(el("div", { class: "pp-note", text: "LUT library (.cube)", style: "font-weight:600;margin-top:10px" }));
    var search = document.createElement("input");
    search.placeholder = "Search LUTs…"; search.style.width = "100%"; search.className = "pp-btn"; search.style.cursor = "text";
    looks.appendChild(search);
    var lutList = el("div", {});
    looks.appendChild(lutList);
    var importB = el("button", { type: "button", class: "pp-btn", text: "Import .cube", style: "margin-top:6px" });
    importB.addEventListener("click", function () {
      var fi = document.createElement("input");
      fi.type = "file"; fi.accept = ".cube"; fi.multiple = true;
      fi.addEventListener("change", function () {
        Array.from(fi.files || []).forEach(function (f) {
          var rd = new FileReader();
          rd.onload = function () {
            var lut = parseCube(rd.result);
            if (!lut) { say("Could not parse " + f.name + " (need LUT_3D_SIZE + data)."); return; }
            lut.name = (f.name || "lut").replace(/\.cube$/i, ""); lut.id = uid();
            S.luts.push(lut); paintLuts();
          };
          rd.readAsText(f);
        });
      });
      fi.click();
    });
    looks.appendChild(importB);
    function paintLuts() {
      lutList.innerHTML = "";
      var q = (search.value || "").toLowerCase();
      var noneB = el("button", { type: "button", class: "pp-btn" + (!recipe().lutId ? " on" : ""), text: "None", style: "display:block;width:100%;margin:2px 0;text-align:left" });
      noneB.addEventListener("click", function () { commit("lut none"); recipe().lutId = ""; cur().lut = null; recipe().lutIntensity = 0; buildInspector(); scheduleRender(); saveDraft(); paintLuts(); });
      lutList.appendChild(noneB);
      S.luts.filter(function (l) { return !q || (l.name || "").toLowerCase().indexOf(q) !== -1; }).forEach(function (l) {
        var row = el("div", { style: "display:flex;gap:4px;align-items:center" });
        var b = el("button", { type: "button", class: "pp-btn" + (recipe().lutId === l.id ? " on" : ""), text: (S.lutFav[l.id] ? "★ " : "") + l.name + " (" + l.size + "³)", style: "flex:1;text-align:left;margin:2px 0" });
        b.addEventListener("click", function () {
          commit("lut " + l.name);
          recipe().lutId = l.id; cur().lut = l;
          if (recipe().lutIntensity === 0) recipe().lutIntensity = 100;
          buildInspector(); scheduleRender(); saveDraft(); paintLuts();
        });
        var fav = el("button", { type: "button", class: "pp-btn", text: S.lutFav[l.id] ? "★" : "☆", title: "Favorite" });
        fav.addEventListener("click", function () {
          if (S.lutFav[l.id]) delete S.lutFav[l.id]; else S.lutFav[l.id] = 1;
          storeSet(LS_LUTFAV, S.lutFav); paintLuts();
        });
        row.appendChild(b); row.appendChild(fav);
        lutList.appendChild(row);
      });
      if (!S.luts.length) lutList.appendChild(el("p", { class: "pp-note", text: "No LUTs yet — import .cube files." }));
    }
    search.addEventListener("input", paintLuts);
    paintLuts();
  }

  // ── Filmstrip ──
  function renderFilm() {
    film.innerHTML = "";
    S.items.forEach(function (it, idx) {
      var t = document.createElement("img");
      t.className = "pp-thumb" + (idx === S.active ? " active" : "");
      if (it.file && !it._objUrl) { try { it._objUrl = URL.createObjectURL(it.file); } catch (_e) {} }
      t.src = it.file ? (it._objUrl || "") : it.url;
      t.title = it.name || ("Image " + (idx + 1));
      t.addEventListener("click", function () { if (idx !== S.active) { commit("switch image"); loadItem(idx); } });
      film.appendChild(t);
    });
    var up = el("button", { type: "button", class: "pp-btn", "data-testid": "pp-add", text: "+ Add", title: "Add images to the session" });
    up.addEventListener("click", function () {
      var fi = document.createElement("input");
      fi.type = "file"; fi.accept = "image/*"; fi.multiple = true;
      fi.addEventListener("change", function () {
        Array.from(fi.files || []).forEach(function (f) { addItem(f.name, "", f); });
      });
      fi.click();
    });
    film.appendChild(up);
    if (S.items.length > 1) {
      var rm = el("button", { type: "button", class: "pp-btn", text: "Remove", title: "Remove current image (Del)" });
      rm.addEventListener("click", removeCurrent);
      film.appendChild(rm);
    }
    film.appendChild(el("span", { class: "pp-note", text: S.items.length + " image(s) · ←/→ navigates" }));
  }
  function removeCurrent() {
    if (S.items.length < 2) return;
    var gone = S.items[S.active];
    if (gone) {
      var gk = itemKeyOf(gone);
      PP_STORE.session = (PP_STORE.session || []).filter(function (e) { return e && e.key !== gk; });
    }
    S.items.splice(S.active, 1);
    loadItem(Math.max(0, S.active - 1));
  }

  // ── Tools on canvas ──
  function setTool(t) {
    S.tool = t;
    cropBtn.classList.toggle("on", t === "crop");
    healBtn.classList.toggle("on", t === "heal");
    wbBtn.classList.toggle("on", t === "wb");
    view.style.cursor = t ? "crosshair" : "default";
    say(t === "crop" ? "Drag a crop rect · Enter applies · Esc cancels." :
      t === "heal" ? "Click blemishes to heal · [ ] sizes brush · Enter commits · Esc undoes." :
      t === "wb" ? "Click a neutral gray area to set white balance." : "");
  }
  var overlay = null;
  function stagePos(e) {
    var vr = view.getBoundingClientRect();
    return { x: clamp((e.clientX - vr.left) / vr.width, 0, 1), y: clamp((e.clientY - vr.top) / vr.height, 0, 1) };
  }
  view.addEventListener("pointerdown", function (e) {
    ws.focus();
    if (S.tool === "crop") {
      var p = stagePos(e);
      S.cropDrag = { x0: p.x, y0: p.y, x1: p.x, y1: p.y };
      drawOverlay();
      view.setPointerCapture(e.pointerId);
    } else if (S.tool === "heal") {
      healAt(e);
    } else if (S.tool === "wb") {
      pickWB(e);
    } else if (S.compare) {
      var r = stage.getBoundingClientRect();
      S.comparePos = clamp(Math.round((e.clientX - r.left) / r.width * 100), 0, 100);
      refreshCompare();
    }
  });
  view.addEventListener("pointermove", function (e) {
    if (S.tool === "crop" && S.cropDrag) {
      var p = stagePos(e);
      S.cropDrag.x1 = p.x; S.cropDrag.y1 = p.y;
      drawOverlay(); scheduleRenderCropPreview();
    }
  });
  view.addEventListener("pointerup", function () {
    if (S.tool === "crop" && S.cropDrag) {
      var d = S.cropDrag, r = recipe();
      var before = snapshot();
      var nx = Math.min(d.x0, d.x1), ny = Math.min(d.y0, d.y1);
      var nw = Math.abs(d.x1 - d.x0), nh = Math.abs(d.y1 - d.y0);
      r.crop.x = clamp(nx, 0, 1); r.crop.y = clamp(ny, 0, 1);
      r.crop.w = clamp(nw || 1, 0.01, 1); r.crop.h = clamp(nh || 1, 0.01, 1);
      if (r.crop.x + r.crop.w > 1) r.crop.w = 1 - r.crop.x;
      if (r.crop.y + r.crop.h > 1) r.crop.h = 1 - r.crop.y;
      commit("crop", before); clearOverlay(); scheduleRender(); saveDraft();
      S.cropDrag = null;
    }
  });
  function scheduleRenderCropPreview() {
    if (!S.cropDrag) return;
    var d = S.cropDrag, r = recipe();
    var keep = { x: r.crop.x, y: r.crop.y, w: r.crop.w, h: r.crop.h };
    r.crop.x = clamp(Math.min(d.x0, d.x1), 0, 1); r.crop.y = clamp(Math.min(d.y0, d.y1), 0, 1);
    r.crop.w = clamp(Math.abs(d.x1 - d.x0) || 0.01, 0.01, 1); r.crop.h = clamp(Math.abs(d.y1 - d.y0) || 0.01, 0.01, 1);
    render();
    r.crop.x = keep.x; r.crop.y = keep.y; r.crop.w = keep.w; r.crop.h = keep.h;
  }
  function drawOverlay() {
    clearOverlay();
    if (!S.cropDrag) return;
    overlay = el("div", { style: "position:absolute;border:1.5px dashed #d9a441;pointer-events:none;background:rgba(217,164,65,.08)" });
    var d = S.cropDrag;
    overlay.style.left = (Math.min(d.x0, d.x1) * 100) + "%";
    overlay.style.top = (Math.min(d.y0, d.y1) * 100) + "%";
    overlay.style.width = (Math.abs(d.x1 - d.x0) * 100) + "%";
    overlay.style.height = (Math.abs(d.y1 - d.y0) * 100) + "%";
    stage.appendChild(overlay);
  }
  function clearOverlay() { if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay); overlay = null; }

  function viewPixel(e) {
    var vr = view.getBoundingClientRect();
    var px = clamp(Math.round((e.clientX - vr.left) / vr.width * (view.width - 1)), 0, view.width - 1);
    var py = clamp(Math.round((e.clientY - vr.top) / vr.height * (view.height - 1)), 0, view.height - 1);
    return { px: px, py: py };
  }
  function healAt(e) {
    var r = recipe(), p = stagePos(e);
    var before = snapshot();
    r.spots.push({ x: p.x, y: p.y, r: S.brushR });
    commit("heal spot", before); scheduleRender(); saveDraft();
    say(S.items[S.active].recipe.spots.length + " heal spot(s).");
  }
  function pickWB(e) {
    try {
      var v = viewPixel(e);
      var ctx = view.getContext("2d");
      var d = ctx.getImageData(Math.max(0, v.px - 4), Math.max(0, v.py - 4), 9, 9).data;
      var ar = 0, ag = 0, ab = 0, n2 = d.length / 4;
      for (var i = 0; i < d.length; i += 4) { ar += d[i]; ag += d[i + 1]; ab += d[i + 2]; }
      ar /= n2 * 255; ag /= n2 * 255; ab /= n2 * 255;
      var r = recipe(), lum = 0.2126 * ar + 0.7152 * ag + 0.0722 * ab || 1;
      var before = snapshot();
      // Nudge temp/tint so sampled patch goes neutral.
      r.temp = clamp(r.temp + ((ab - ar) / lum) * 60, -100, 100);
      r.tint = clamp(r.tint + ((ag - (ar + ab) / 2) / lum) * 80, -100, 100);
      commit("wb pick", before); buildInspector(); scheduleRender(); saveDraft();
      say("White balance sampled.");
    } catch (_e) { say("WB pick failed on this image."); }
  }

  // Divider drag
  divider.addEventListener("pointerdown", function (e) {
    e.preventDefault();
    function mv(ev) {
      var r = stage.getBoundingClientRect();
      S.comparePos = clamp(Math.round((ev.clientX - r.left) / r.width * 100), 0, 100);
      refreshCompare();
    }
    function up() { document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up); }
    document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
  });

  // Keyboard
  ws.addEventListener("keydown", function (e) {
    if (/INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || "")) return;
    var k = e.key;
    if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "z" && !e.shiftKey) { e.preventDefault(); doUndo(); }
    else if ((e.ctrlKey || e.metaKey) && (k.toLowerCase() === "y" || (k.toLowerCase() === "z" && e.shiftKey))) { e.preventDefault(); doRedo(); }
    else if (k === "\\") { S.compare = !S.compare; cmpBtn.classList.toggle("on", S.compare); refreshCompare(); }
    else if (k === "c" || k === "C") setTool(S.tool === "crop" ? null : "crop");
    else if (k === "j" || k === "J") setTool(S.tool === "heal" ? null : "heal");
    else if (k === "w" || k === "W") setTool(S.tool === "wb" ? null : "wb");
    else if (k === "Escape") {
      if (S.tool === "crop") { S.cropDrag = null; clearOverlay(); setTool(null); render(); }
      else if (S.tool === "heal") {
        var r = recipe();
        if (r.spots.length) { var before = snapshot(); r.spots.pop(); commit("heal undo", before); scheduleRender(); saveDraft(); }
        else setTool(null);
      }
      else setTool(null);
    }
    else if (k === "Enter") { if (S.tool) { setTool(null); saveDraft(); } }
    else if (k === "ArrowRight" && S.items.length > 1) { commit("switch image"); loadItem((S.active + 1) % S.items.length); }
    else if (k === "ArrowLeft" && S.items.length > 1) { commit("switch image"); loadItem((S.active - 1 + S.items.length) % S.items.length); }
    else if (k === "Delete" || k === "Backspace") { if (S.items.length > 1) removeCurrent(); }
    else if ((e.ctrlKey || e.metaKey) && (k === "+" || k === "=")) { e.preventDefault(); S.zoom = (S.zoom || 1) * 1.25; applyZoom(); }
    else if ((e.ctrlKey || e.metaKey) && k === "-") { e.preventDefault(); S.zoom = (S.zoom || 1) / 1.25; applyZoom(); }
    else if ((e.ctrlKey || e.metaKey) && k === "0") { e.preventDefault(); S.zoom = 0; applyZoom(); }
    else if (k === "[" || k === "]") {
      var d = k === "]" ? 1.25 : 0.8;
      if (e.shiftKey) S.brushHard = clamp(S.brushHard * d, 0.05, 1);
      else S.brushR = clamp(S.brushR * d, 0.002, 0.15);
      say("Brush r=" + (S.brushR * 100).toFixed(1) + "% hardness=" + Math.round(S.brushHard * 100) + "%");
    }
  });
  // Space-drag pan
  var spaceDown = false;
  ws.addEventListener("keydown", function (e) { if (e.key === " ") spaceDown = true; });
  ws.addEventListener("keyup", function (e) { if (e.key === " ") spaceDown = false; });
  stage.addEventListener("wheel", function (e) {
    if (!e.ctrlKey) return;
    e.preventDefault();
    S.zoom = clamp((S.zoom || 1) * (e.deltaY < 0 ? 1.1 : 0.9), 0.2, 8);
    applyZoom();
  }, { passive: false });

  // ── Save / export ──
  function saveDraft() {
    var item = cur();
    if (!item) return;
    PP_STORE.recipes[itemKeyOf(item)] = clone(item.recipe);
    storeSet(LS_RECIPE, { url: item.url, name: item.name, recipe: item.recipe });
    window.__ppRecipe = { url: item.url, name: item.name, recipe: clone(item.recipe) };
  }
  function saveRecipe() { saveDraft(); say("Recipe saved locally — reopen this image to resume."); }

  function renderFullRes(item, done) {
    try {
      var iw = srcCanvas.width, ih = srcCanvas.height;
      var sctx = srcCanvas.getContext("2d");
      var full = sctx.getImageData(0, 0, iw, ih);
      var f = new Float32Array(iw * ih * 3);
      for (var i = 0; i < iw * ih; i++) {
        f[i * 3] = full.data[i * 4] / 255; f[i * 3 + 1] = full.data[i * 4 + 1] / 255; f[i * 3 + 2] = full.data[i * 4 + 2] / 255;
      }
      applySpots(f, iw, ih, item.recipe.spots);
      processPixels(f, iw, ih, item.recipe, item.lut, 42);
      var r = item.recipe;
      var cw = Math.max(1, Math.round(r.crop.w * iw)), ch = Math.max(1, Math.round(r.crop.h * ih));
      var sx = Math.round(r.crop.x * iw), sy = Math.round(r.crop.y * ih);
      var out = document.createElement("canvas");
      out.width = cw; out.height = ch;
      var octx = out.getContext("2d");
      var oid = octx.createImageData(cw, ch);
      for (var y = 0; y < ch; y++) {
        for (var x = 0; x < cw; x++) {
          var sp = ((sy + y) * iw + (sx + x)) * 3, dp = (y * cw + x) * 4;
          oid.data[dp] = clamp(f[sp], 0, 1) * 255;
          oid.data[dp + 1] = clamp(f[sp + 1], 0, 1) * 255;
          oid.data[dp + 2] = clamp(f[sp + 2], 0, 1) * 255;
          oid.data[dp + 3] = 255;
        }
      }
      octx.putImageData(oid, 0, 0);
      if (r.crop.angle) { // straighten at export
        var ang = r.crop.angle * Math.PI / 180;
        var rw = Math.round(Math.abs(cw * Math.cos(ang)) + Math.abs(ch * Math.sin(ang)));
        var rh = Math.round(Math.abs(cw * Math.sin(ang)) + Math.abs(ch * Math.cos(ang)));
        var rot = document.createElement("canvas"); rot.width = rw; rot.height = rh;
        var rctx = rot.getContext("2d");
        rctx.translate(rw / 2, rh / 2); rctx.rotate(ang); rctx.drawImage(out, -cw / 2, -ch / 2);
        done(rot);
      } else done(out);
    } catch (e) { say("Full-res render failed: " + (e && e.message)); }
  }

  function doExport() {
    var item = cur();
    if (!item || !item.img) { say("Nothing to export yet."); return; }
    say("Rendering full resolution…");
    setTimeout(function () {
      renderFullRes(item, function (canvas) {
        var fmt = item.recipe.format || "png";
        var mime = fmt === "jpeg" ? "image/jpeg" : fmt === "webp" ? "image/webp" : "image/png";
        var q = clamp((item.recipe.quality || 90) / 100, 0.01, 1);
        canvas.toBlob(function (blob) {
          if (!blob) { say("Export encoding failed."); return; }
          function download(bytes, type) {
            var b = bytes ? new Blob([bytes], { type: type }) : blob;
            var a = document.createElement("a");
            var stem = (item.name || "postprocessed").replace(/\.[a-z0-9]+$/i, "");
            a.href = URL.createObjectURL(b);
            a.download = stem + "_edited." + fmt;
            document.body.appendChild(a); a.click();
            setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 4000);
            say("Exported " + a.download + " (" + Math.round(b.size / 1024) + " KB).");
          }
          if (fmt === "png" && item.recipe.embedMetadata && item.srcBytes) {
            blob.arrayBuffer().then(function (buf) {
              download(injectPngMetadata(new Uint8Array(buf), item.srcBytes), "image/png");
            }).catch(function () { download(null); });
          } else download(null);
        }, mime, q);
      });
    }, 30);
  }

  function afterRecipeChange() {
    buildInspector(); renderLooks(); renderFilm(); scheduleRender(); saveDraft();
  }

  // Boot
  buildInspector(); renderLooks();
  restoreSession();
  if (sourceUrl) addItem("Studio output", sourceUrl, null);
  if (!S.items.length) {
    insp.innerHTML = "";
    insp.appendChild(el("p", { class: "pp-note", text: "No Studio output on the canvas yet. Upload an image, or run a generation and return here." }));
    var up0 = el("button", { type: "button", class: "pp-btn", "data-testid": "pp-upload-empty", text: "Upload image" });
    up0.addEventListener("click", function () {
      var fi = document.createElement("input");
      fi.type = "file"; fi.accept = "image/*"; fi.multiple = true;
      fi.addEventListener("change", function () {
        Array.from(fi.files || []).forEach(function (f) { addItem(f.name, "", f); });
      });
      fi.click();
    });
    insp.appendChild(up0);
  }
  return {
    setSource: function (url) { addItem("Studio output", url, null); },
    // The native Studio shell owns the image surface; this is the same
    // engine canvas, moved into that surface by studio-playground.js.
    stage: stage,
    workspace: ws,
  };
}
