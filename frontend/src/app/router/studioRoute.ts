// Modal Studio Vue substrate — frozen Studio route codec.
//
// The public URL contract is owned by the product, not by this migration:
//
//   #comfymodal=<page>              — canonical page route
//   #comfymodal=<page>&focus=<id>   — page route plus ONE optional focus id
//
// Exactly five pages; `backend` stays the route key even though its UI
// label reads "Manage Modal". Unrelated ComfyUI hashes are never
// interpreted or rewritten. Malformed Studio hashes fail soft.
//
// This mirrors the semantics of web/studio-routing.js (which remains the
// authority for the production old Studio during the parallel-replacement
// window). The two implementations are intentionally parallel, not shared:
// sharing a module across the Vite bundle boundary and the legacy
// extension scripts would couple their builds. The vitest suite pins
// parity on the contract vectors. Final production cutover deletes the
// legacy file, leaving this codec as the single owner.

export const STUDIO_HASH_KEY = "comfymodal";

export const STUDIO_PAGES = [
  "playground",
  "history",
  "workflows",
  "backend",
  "settings",
] as const;

export type StudioPage = (typeof STUDIO_PAGES)[number];

/** UI labels. Only the label differs from the route key for `backend`. */
export const STUDIO_PAGE_LABELS: Record<StudioPage, string> = {
  playground: "Playground",
  history: "History",
  workflows: "Workflows",
  backend: "Manage Modal",
  settings: "Settings",
};

export function isStudioPage(id: unknown): id is StudioPage {
  return (
    typeof id === "string" &&
    (STUDIO_PAGES as readonly string[]).indexOf(id) !== -1
  );
}

export interface StudioRoute {
  page: StudioPage;
  focus: string | null;
}

export interface ParsedStudioHash {
  matched: boolean;
  page: StudioPage | "";
  focus: string | null;
}

function safeDecode(value: string): string | null {
  try {
    return decodeURIComponent(value);
  } catch {
    return null;
  }
}

/** Parse a raw location hash. Never throws; non-Studio hashes → matched:false. */
export function parseStudioHash(hash: string): ParsedStudioHash {
  const unmatched: ParsedStudioHash = { matched: false, page: "", focus: null };
  if (typeof hash !== "string") return unmatched;
  const raw = hash.charAt(0) === "#" ? hash.slice(1) : hash;
  if (raw === "") return unmatched;

  const segments = raw.split("&");
  const head = segments[0];
  const headEq = head.indexOf("=");
  if (headEq === -1) return unmatched;
  if (safeDecode(head.slice(0, headEq)) !== STUDIO_HASH_KEY) return unmatched;

  const page = safeDecode(head.slice(headEq + 1));
  if (!isStudioPage(page)) return unmatched;

  let focus: string | null = null;
  for (let i = 1; i < segments.length; i++) {
    const seg = segments[i];
    const segEq = seg.indexOf("=");
    if (segEq === -1) continue;
    if (safeDecode(seg.slice(0, segEq)) !== "focus") continue;
    const decoded = safeDecode(seg.slice(segEq + 1));
    focus = decoded === null || decoded === "" ? null : decoded;
    break;
  }
  return { matched: true, page, focus };
}

/** Serialize a route to canonical hash form, or "" for non-routes. */
export function serializeStudioHash(route: {
  page: unknown;
  focus?: string | null;
}): string {
  if (!isStudioPage(route?.page)) return "";
  const focus =
    typeof route.focus === "string" && route.focus !== "" ? route.focus : null;
  return (
    "#" + STUDIO_HASH_KEY + "=" + route.page +
    (focus ? "&focus=" + encodeURIComponent(focus) : "")
  );
}

/**
 * History decision between two routes (either may be null/unrouted).
 *   next unrouted        → "none"    (never manage unrelated host hashes)
 *   prev unrouted        → "replace" (seed the current entry so Back stays in-Studio)
 *   different page       → "push"    (page changes create history entries)
 *   same page, new focus → "replace" (selection identity within a page)
 *   identical            → "none"    (no duplicate no-op entries)
 */
export function decideHistoryAction(
  prev: { page: unknown; focus?: string | null } | null,
  next: { page: unknown; focus?: string | null } | null,
): "push" | "replace" | "none" {
  if (!next || !isStudioPage(next.page)) return "none";
  if (!prev || !isStudioPage(prev.page)) return "replace";
  if (next.page !== prev.page) return "push";
  const prevFocus = prev.focus || null;
  const nextFocus = next.focus || null;
  return prevFocus === nextFocus ? "none" : "replace";
}

/** Resolve an explicit opener route or a present hash, else the default. */
export function resolveInitialRoute(
  explicit: { page: unknown; focus?: string | null } | undefined,
  locationHash: string,
): StudioRoute {
  if (explicit && isStudioPage(explicit.page)) {
    return {
      page: explicit.page,
      focus:
        typeof explicit.focus === "string" && explicit.focus !== ""
          ? explicit.focus
          : null,
    };
  }
  const parsed = parseStudioHash(locationHash);
  if (parsed.matched && isStudioPage(parsed.page)) {
    return { page: parsed.page, focus: parsed.focus };
  }
  return { page: "playground", focus: null };
}
