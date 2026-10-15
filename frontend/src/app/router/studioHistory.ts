// Modal Studio Vue substrate — vue-router history over the frozen hash.
//
// Vue Router normally owns the URL (web-hash `#/...` or HTML5 paths).
// Studio cannot use either: the public contract is `#comfymodal=<page>`
// and nothing else. This module is the small adapter that lets Vue Router
// manage in-app navigation while the address bar keeps speaking the frozen
// contract — page changes push history, same-page focus changes replace,
// unrelated ComfyUI hashes are never interpreted or rewritten.
//
// Design: implement vue-router's `RouterHistory` interface against
// `location.hash`, translating router locations (`/history?focus=x`) to
// Studio hashes (`#comfymodal=history&focus=x`). Back/Forward arrives via
// `popstate`; hashes that do not parse as Studio routes are reported as
// the default location WITHOUT rewriting the URL.

import type { HistoryState, RouterHistory } from "vue-router";
import {
  decideHistoryAction,
  isStudioPage,
  parseStudioHash,
  resolveInitialRoute,
  serializeStudioHash,
  type StudioPage,
  type StudioRoute,
} from "./studioRoute";

export interface StudioWindow {
  location: { hash: string; pathname: string; search: string };
  history: {
    pushState(data: unknown, title: string, url?: string | URL | null): void;
    replaceState(data: unknown, title: string, url?: string | URL | null): void;
  };
  addEventListener(type: string, listener: () => void): void;
  removeEventListener(type: string, listener: () => void): void;
}

const ROUTER_BASE = "/";
const DEFAULT_ROUTE: StudioRoute = { page: "playground", focus: null };

function routeToRouterLocation(route: StudioRoute): string {
  const query = route.focus ? `?focus=${encodeURIComponent(route.focus)}` : "";
  return `/${route.page}${query}`;
}

function routerLocationToRoute(fullPath: string): StudioRoute {
  const [path, queryString] = fullPath.split("?");
  const pagePart = path.replace(/^\//, "");
  const page: StudioPage = isStudioPage(pagePart) ? pagePart : DEFAULT_ROUTE.page;
  let focus: string | null = null;
  if (queryString) {
    for (const pair of queryString.split("&")) {
      const eq = pair.indexOf("=");
      if (eq === -1) continue;
      if (decodeURIComponent(pair.slice(0, eq)) !== "focus") continue;
      try {
        const decoded = decodeURIComponent(pair.slice(eq + 1));
        focus = decoded === "" ? null : decoded;
      } catch {
        focus = null;
      }
      break;
    }
  }
  return { page, focus };
}

/** Read the current hash as a Studio route, or null when unrelated. */
export function readHashRoute(win: StudioWindow): StudioRoute | null {
  const parsed = parseStudioHash(win.location.hash);
  if (!parsed.matched || !isStudioPage(parsed.page)) return null;
  return { page: parsed.page, focus: parsed.focus };
}

/** Write a Studio route to the hash, preserving host pathname/search. */
function writeHashRoute(
  win: StudioWindow,
  route: StudioRoute,
  action: "push" | "replace",
): void {
  const hash = serializeStudioHash(route);
  if (!hash) return;
  const url = win.location.pathname + win.location.search + hash;
  if (action === "push") win.history.pushState({}, "", url);
  else win.history.replaceState({}, "", url);
}

/**
 * Build a vue-router history that speaks `#comfymodal=…`.
 *
 * `initial` mirrors the shell precedence: an explicit opener route wins
 * over a stale URL hash for that invocation; otherwise a present Studio
 * hash is honored and the default applies. An unrelated hash is left
 * untouched (never replaced on init).
 */
export function createStudioHashHistory(
  win: StudioWindow,
  initial?: { page: unknown; focus?: string | null },
): RouterHistory {
  // Explicit opener intent wins over a stale URL hash for that
  // invocation; otherwise a present Studio hash is honored, else default.
  // An unrelated hash is left untouched (never replaced on init).
  let current: StudioRoute = resolveInitialRoute(initial, win.location.hash);

  let currentLocation = routeToRouterLocation(current);
  let currentState: HistoryState = {};
  // The location reported at creation. Vue Router replays it as its
  // initial navigation; that replay must never rewrite a URL that was
  // never a Studio route (unrelated ComfyUI hash or empty hash). Only a
  // genuine subsequent user navigation may seed the hash.
  const creationLocation = currentLocation;
  const listeners = new Set<(to: string, from: string) => void>();
  let listening = false;

  const onPopState = () => {
    const from = currentLocation;
    const next = readHashRoute(win);
    // Unrelated hash on Back/Forward: report the default location so the
    // router renders something sane, but never rewrite the host URL.
    current = next ?? { ...DEFAULT_ROUTE };
    currentLocation = routeToRouterLocation(current);
    listeners.forEach((fn) => fn(currentLocation, from));
  };

  // Vue Router replays the creation location as its initial navigation.
  // When the live URL was never a Studio route, that replay must not
  // manufacture a Studio hash — the first genuine user navigation seeds it.
  const isInitialReplay = (
    livePrev: StudioRoute | null,
    targetLocation: string,
  ): boolean => livePrev === null && targetLocation === creationLocation;

  return {
    get base() {
      return ROUTER_BASE;
    },
    get location() {
      return currentLocation;
    },
    get state() {
      return currentState;
    },
    createHref: (to) => {
      // RouterLinks render the PUBLIC Studio hash (never `#/page`): hover
      // status, copy-link, middle-click, and open-in-new-tab all speak the
      // frozen `#comfymodal=<page>` contract.
      const hash = serializeStudioHash(routerLocationToRoute(to));
      return hash === "" ? "#" + to : hash;
    },
    replace: (to, data) => {
      // Prev derives from the LIVE hash (not internal state) so a stale or
      // unrelated URL seeds via replace — same rule as the legacy shell.
      const prev = readHashRoute(win);
      const target = routerLocationToRoute(to);
      const targetLocation = routeToRouterLocation(target);
      current = target;
      if (data !== undefined) currentState = data;
      currentLocation = targetLocation;
      if (isInitialReplay(prev, targetLocation)) return;
      if (decideHistoryAction(prev, target) !== "none") {
        writeHashRoute(win, target, "replace");
      }
    },
    push: (to, data) => {
      const prev = readHashRoute(win);
      const target = routerLocationToRoute(to);
      const targetLocation = routeToRouterLocation(target);
      current = target;
      if (data !== undefined) currentState = data;
      currentLocation = targetLocation;
      if (isInitialReplay(prev, targetLocation)) return;
      const action = decideHistoryAction(prev, target);
      if (action === "push") writeHashRoute(win, target, "push");
      else if (action === "replace") writeHashRoute(win, target, "replace");
    },
    go: () => {
      // Back/Forward traversal belongs to the browser (popstate); the
      // router never drives it programmatically in Studio.
    },
    listen: (callback) => {
      const wrapped = (to: string, from: string) => {
        callback(to, from, { type: "pop", direction: "unknown", delta: 0 } as never);
      };
      listeners.add(wrapped);
      if (!listening) {
        win.addEventListener("popstate", onPopState);
        listening = true;
      }
      return () => {
        listeners.delete(wrapped);
        if (listeners.size === 0 && listening) {
          win.removeEventListener("popstate", onPopState);
          listening = false;
        }
      };
    },
    destroy: () => {
      listeners.clear();
      if (listening) {
        win.removeEventListener("popstate", onPopState);
        listening = false;
      }
    },
  };
}
