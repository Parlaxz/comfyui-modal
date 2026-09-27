// Modal Studio — Routing
//
// Pure helpers for the frozen Studio URL contract (Phase I1 §3.8, I9):
//
//   #comfymodal=<page>              — canonical page route
//   #comfymodal=<page>&focus=<id>   — page route plus ONE optional focus id
//
// Canonical pages: playground | history | workflows | backend | settings.
// Hash-only: the ComfyUI host pathname/search are never touched. No router
// library, no dependencies, no DOM, no storage, no network. Decoded values
// are treated as opaque identifiers only (never HTML/markup).
//
// Fail-soft rules: unrelated hash / missing page / unknown page / malformed
// percent encoding never throw and never fabricate a route.

// Hash key is frozen product vocabulary; the five ids are the only pages the
// shell can mount.
export const STUDIO_HASH_KEY = "comfymodal";
export const ROUTE_PAGES = ["playground", "history", "workflows", "backend", "settings"];

export function isCanonicalPage(id) {
  return typeof id === "string" && ROUTE_PAGES.indexOf(id) !== -1;
}

// decodeURIComponent that never throws: malformed sequences resolve to null
// so callers can drop the value instead of crashing.
function _safeDecode(value) {
  try {
    return decodeURIComponent(value);
  } catch (_err) {
    return null;
  }
}

/**
 * Parse a location.hash into a Studio route.
 * @param {string} hash raw hash string (leading "#" optional)
 * @returns {{matched: boolean, page: string, focus: string|null}}
 *   matched=false for anything that is not a valid Studio route (unrelated
 *   host hash, missing/unknown page). focus=null when absent or unusable.
 */
export function parseStudioHash(hash) {
  const unmatched = { matched: false, page: "", focus: null };
  if (typeof hash !== "string") return unmatched;
  let raw = hash.charAt(0) === "#" ? hash.slice(1) : hash;
  if (raw === "") return unmatched;

  const segments = raw.split("&");
  const head = segments[0];
  const headEq = head.indexOf("=");
  if (headEq === -1) return unmatched;
  if (_safeDecode(head.slice(0, headEq)) !== STUDIO_HASH_KEY) return unmatched;

  // Unknown/malformed page → not a Studio route (fail soft, never guess).
  const page = _safeDecode(head.slice(headEq + 1));
  if (!isCanonicalPage(page)) return unmatched;

  // At most one focus value: the FIRST focus segment wins; every other
  // parameter (known or unknown) is ignored.
  let focus = null;
  for (let i = 1; i < segments.length; i++) {
    const seg = segments[i];
    const segEq = seg.indexOf("=");
    if (segEq === -1) continue;
    if (_safeDecode(seg.slice(0, segEq)) !== "focus") continue;
    const decoded = _safeDecode(seg.slice(segEq + 1));
    // Malformed percent encoding drops the focus but keeps the page route.
    focus = decoded === null || decoded === "" ? null : decoded;
    break;
  }
  return { matched: true, page: page, focus: focus };
}

/**
 * Serialize a route to the canonical hash form.
 * @param {{page: string, focus?: string|null}} route
 * @returns {string} "#comfymodal=<page>" (plus "&focus=<encoded>") or ""
 *   when the route carries no canonical page.
 */
export function serializeStudioHash(route) {
  const page = route && route.page;
  if (!isCanonicalPage(page)) return "";
  const focus =
    route && typeof route.focus === "string" && route.focus !== "" ? route.focus : null;
  return (
    "#comfymodal=" + page +
    (focus ? "&focus=" + encodeURIComponent(focus) : "")
  );
}

/**
 * History decision between two parsed routes (either may be null/unrouted).
 *   next unrouted            → "none"    (never manage unrelated host hashes)
 *   prev unrouted            → "replace" (seed the current entry before the
 *                                          first pushed page so Back stays in-Studio)
 *   different page           → "push"    (page changes create history entries)
 *   same page, new focus     → "replace" (selection identity within a page)
 *   identical                → "none"    (no duplicate no-op entries)
 */
export function routeHistoryAction(prevRoute, nextRoute) {
  if (!nextRoute || !isCanonicalPage(nextRoute.page)) return "none";
  if (!prevRoute || !isCanonicalPage(prevRoute.page)) return "replace";
  if (nextRoute.page !== prevRoute.page) return "push";
  const prevFocus = prevRoute.focus || null;
  const nextFocus = nextRoute.focus || null;
  return prevFocus === nextFocus ? "none" : "replace";
}
