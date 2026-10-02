// F3 Follow-Up A — History V2 Browser Download unit tests.
//
// Covers the shared download helper (web/history-v2-download.js): MIME →
// extension authority, deterministic collision-free filename construction,
// sanitization and length bounds, plus structural invariants of the button
// builder (explicit fetch only, per-button in-flight guard, object-URL
// cleanup, truthful failure recovery, zero export-state coupling).  Browser
// click/fetch behavior is covered by studio-fake-history-v2-download.spec.mjs.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  buildHistoryDownloadFilename,
  mimeToExtension,
  sanitizeFilenamePart,
} from "../web/history-v2-browser-download.js";

// ── MIME → extension (response Blob MIME is the authority) ───────────────

assert.equal(mimeToExtension("image/webp"), "webp");
assert.equal(mimeToExtension("image/png"), "png");
assert.equal(mimeToExtension("image/jpeg"), "jpg");
assert.equal(mimeToExtension("image/jpg; charset=binary"), "jpg");
assert.equal(mimeToExtension("IMAGE/PNG"), "png");
assert.equal(mimeToExtension("image/avif"), "avif");
// Unknown image subtype passes through sanitized.
assert.equal(mimeToExtension("image/x-jxl"), "xjxl");
// Missing/malformed MIME falls back to png — never derived from a URL or a
// Preview filename.
assert.equal(mimeToExtension(""), "png");
assert.equal(mimeToExtension(null), "png");
assert.equal(mimeToExtension("application/json"), "png");

// ── Sanitization ──────────────────────────────────────────────────────────

assert.equal(sanitizeFilenamePart("Portrait Pro"), "Portrait_Pro");
assert.equal(sanitizeFilenamePart('  bad:*?"/<>|name  '), "bad_name");
assert.equal(sanitizeFilenamePart("a___b"), "a___b");
assert.equal(sanitizeFilenamePart(""), "");
assert.equal(sanitizeFilenamePart(null), "");
assert.equal(sanitizeFilenamePart("abc", 2), "ab");

// ── Deterministic filename BASE construction (ext appended from MIME) ────

const meta = {
  workflow: "Portrait Pro",
  generationId: "gen_ok",
  seed: 1000,
  outputIndex: 0,
};
assert.equal(
  buildHistoryDownloadFilename(Object.assign({}, meta, { variant: "preview" })),
  "Portrait_Pro_seed1000_out0_preview_gen_ok"
);
assert.equal(
  buildHistoryDownloadFilename(Object.assign({}, meta, { variant: "original" })),
  "Portrait_Pro_seed1000_out0_original_gen_ok"
);
// Distinct logical outputs never share a name; featured state is not an input.
assert.notEqual(
  buildHistoryDownloadFilename(Object.assign({}, meta, { variant: "original", outputIndex: 1 })),
  buildHistoryDownloadFilename(Object.assign({}, meta, { variant: "original", outputIndex: 0 }))
);
// No timestamp input: identical metadata → identical name, always.
assert.equal(
  buildHistoryDownloadFilename(Object.assign({}, meta, { variant: "preview" })),
  buildHistoryDownloadFilename(Object.assign({}, meta, { variant: "preview" }))
);
// Producer filename wins when it looks like a filename; its extension is
// never trusted (the response Blob MIME decides) and identity parts survive
// so duplicate producer names across outputs cannot collide silently.
const producerBase = buildHistoryDownloadFilename({
  producerFilename: "ComfyUI_00001_.png",
  workflow: "W",
  generationId: "g1",
  outputIndex: 0,
  variant: "original",
});
assert.ok(producerBase.indexOf("ComfyUI_00001") === 0, "producer base preferred");
assert.ok(producerBase.indexOf("_out0_original_g1") !== -1, "output identity retained");
// Non-filename producer strings are ignored → constructed identity used.
assert.equal(
  buildHistoryDownloadFilename({ producerName: undefined, workflow: "W", variant: "preview" }),
  "W_preview"
);
// Empty metadata still yields a usable bounded base.
assert.equal(buildHistoryDownloadFilename({ variant: "original" }), "original");
assert.equal(buildHistoryDownloadFilename(null), "image");
// Length bound.
assert.ok(buildHistoryDownloadFilename({
  workflow: "w".repeat(300),
  generationId: "g".repeat(300),
  seed: 123456789,
  outputIndex: 10,
  variant: "original",
}).length <= 100);

// ── Button-builder structural contract (browser behavior lives in the
// fake-browser suite; here we pin the invariants that must not regress) ──

const src = readFileSync(
  fileURLToPath(new URL("../web/history-v2-browser-download.js", import.meta.url)),
  "utf8"
);
// Explicit fetch only — no module-scope or render-time asset GETs.
assert.ok(src.includes("await fetch(o.url)"), "download must fetch explicitly on click");
assert.ok(src.includes("inFlight"), "per-button in-flight guard required");
assert.ok(src.includes("URL.createObjectURL"), "blob object URL required");
assert.ok(src.includes("URL.revokeObjectURL"), "object URL must be revoked");
assert.ok(src.includes("a.download = filename"), "anchor download attribute required");
// Truthful failure surface + recovery.
assert.ok(src.includes('"HTTP " + resp.status'), "HTTP failures must be surfaced");
assert.ok(src.includes("Empty asset response"), "empty blob must fail truthfully");
assert.ok(src.includes("btn.disabled = false"), "button must re-enable after failure");
assert.ok(src.includes("Download failed: "), "bounded failure note required");
assert.ok(src.includes("Downloaded "), "success note required");
// No dead controls: absent URL ⇒ no button.
assert.ok(src.includes("if (!o.url) return null;"), "absent URL must render no control");
// Browser download writes ZERO export state: no POSTs, no repo calls at all.
assert.ok(!src.includes("upsert_export_record"), "no export-record coupling");
assert.ok(!src.includes("/run-history/"), "no legacy save route");
assert.ok(!src.includes("method:"), "helper performs GETs only");
// F10 distinction pin: Browser Download labels never say "Export", and the
// configured-folder Export helper lives in its own module with its own
// transport — the two action families stay structurally separate.
assert.ok(!/\bExport\b/.test(src.replace(/\/\/[^\n]*/g, "")), "download labels never use Export wording");
const exportHelperSrc = readFileSync(
  fileURLToPath(new URL("../web/history-v2-export.js", import.meta.url)),
  "utf8",
);
assert.ok(exportHelperSrc.includes("buildConfiguredExportButton"), "configured Export helper exists");
assert.ok(!exportHelperSrc.includes("createObjectURL"), "configured Export never blob-downloads");

console.log("PASS: history-v2-download MIME/filename/control invariants");
