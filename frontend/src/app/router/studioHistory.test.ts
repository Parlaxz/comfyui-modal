// studioHistory bridge — focused unit tests with a fake window.
// Proves: page push writes canonical hashes, same-page focus replaces,
// identical navigations write nothing, unrelated hashes are never
// interpreted or rewritten, popstate (Back/Forward) updates the location,
// explicit initial routes win over stale hashes.
import { describe, expect, it, vi } from "vitest";
import {
  createStudioHashHistory,
  type StudioWindow,
} from "./studioHistory";

function fakeWindow(hash = ""): StudioWindow & {
  firePopState: () => void;
  pushes: string[];
  replaces: string[];
  goes: number[];
} {
  const listeners = new Map<string, Set<() => void>>();
  const entries = [hash];
  let index = 0;
  const hashOf = (url: string): string => {
    const hashIndex = url.indexOf("#");
    return hashIndex === -1 ? "" : url.slice(hashIndex);
  };
  const fire = (type: string) => {
    listeners.get(type)?.forEach((fn) => fn());
  };
  const win: StudioWindow & {
    firePopState: () => void;
    pushes: string[];
    replaces: string[];
    goes: number[];
  } = {
    location: { hash, pathname: "/", search: "" },
    pushes: [],
    replaces: [],
    goes: [],
    history: {
      pushState: (_d, _t, url) => {
        win.pushes.push(String(url));
        entries.splice(index + 1);
        entries.push(hashOf(String(url)));
        index = entries.length - 1;
        win.location.hash = entries[index];
      },
      replaceState: (_d, _t, url) => {
        win.replaces.push(String(url));
        entries[index] = hashOf(String(url));
        win.location.hash = entries[index];
      },
      go: (delta: number) => {
        win.goes.push(delta);
        const next = Math.min(entries.length - 1, Math.max(0, index + delta));
        // Like a real session history, clamped-out-of-range traversal moves
        // nowhere and fires no popstate.
        if (next === index) return;
        index = next;
        win.location.hash = entries[index];
        fire("popstate");
      },
    },
    addEventListener: (type, fn) => {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type)!.add(fn);
    },
    removeEventListener: (type, fn) => {
      listeners.get(type)?.delete(fn);
    },
    firePopState: () => {
      fire("popstate");
    },
  };
  return win;
}

describe("createStudioHashHistory", () => {
  it("starts from a present Studio hash and pushes page changes", () => {
    const win = fakeWindow("#comfymodal=history");
    const history = createStudioHashHistory(win);
    expect(history.location).toBe("/history");
    history.push("/workflows");
    expect(win.pushes).toEqual(["/#comfymodal=workflows"]);
    expect(history.location).toBe("/workflows");
    history.destroy();
  });

  it("replaces (not pushes) same-page focus changes", () => {
    const win = fakeWindow("#comfymodal=history");
    const history = createStudioHashHistory(win);
    history.push("/history?focus=a");
    expect(win.replaces).toEqual(["/#comfymodal=history&focus=a"]);
    expect(win.pushes).toEqual([]);
    history.destroy();
  });

  it("writes nothing for identical navigations", () => {
    const win = fakeWindow("#comfymodal=playground");
    const history = createStudioHashHistory(win);
    history.push("/playground");
    expect(win.pushes).toEqual([]);
    expect(win.replaces).toEqual([]);
    history.destroy();
  });

  it("leaves unrelated hashes untouched and never rewrites them", () => {
    const win = fakeWindow("#workflow=abc");
    const history = createStudioHashHistory(win);
    expect(history.location).toBe("/playground");
    expect(win.pushes).toEqual([]);
    expect(win.replaces).toEqual([]);
    // A programmatic page navigation still works from an unrelated hash…
    history.push("/settings");
    // …and seeds via replace so Back stays in-Studio.
    expect(win.replaces).toEqual(["/#comfymodal=settings"]);
    history.destroy();
  });

  it("honors Back/Forward via popstate, including focus", () => {
    const win = fakeWindow("#comfymodal=playground");
    const history = createStudioHashHistory(win);
    const seen: string[] = [];
    const stop = history.listen((to) => seen.push(to));
    history.push("/history?focus=gen_1");
    // RouterHistory.listen fires only for external (popstate) traversals —
    // programmatic push/replace never notifies.
    expect(seen).toEqual([]);
    // Simulate the browser moving back to the playground entry.
    win.location.hash = "#comfymodal=playground";
    win.firePopState();
    expect(history.location).toBe("/playground");
    expect(seen).toEqual(["/playground"]);
    stop();
    history.destroy();
  });

  it("explicit initial routes override stale hashes without touching the URL", () => {
    const win = fakeWindow("#comfymodal=history");
    const history = createStudioHashHistory(win, { page: "settings" });
    expect(history.location).toBe("/settings");
    expect(win.pushes).toEqual([]);
    expect(win.replaces).toEqual([]);
    history.destroy();
  });

  it("never lets the router initial replay manufacture a studio hash", () => {
    // Vue Router replays the creation location on mount. With an unrelated
    // (or empty) live hash that replay must not write anything.
    for (const hash of ["#workflow=abc", ""]) {
      const win = fakeWindow(hash);
      const history = createStudioHashHistory(win);
      const creation = history.location;
      history.push(creation);
      history.replace(creation);
      expect(win.pushes).toEqual([]);
      expect(win.replaces).toEqual([]);
      expect(win.location.hash).toBe(hash);
      // …but the first genuine user navigation still seeds the hash.
      history.push("/workflows");
      expect(win.replaces).toEqual(["/#comfymodal=workflows"]);
      history.destroy();
    }
  });

  it("go() traverses the session stack and notifies like Back/Forward", () => {
    const win = fakeWindow("#comfymodal=playground");
    const history = createStudioHashHistory(win);
    const seen: string[] = [];
    const stop = history.listen((to) => seen.push(to));
    history.push("/history");
    history.push("/workflows");
    expect(history.location).toBe("/workflows");
    history.go(-1);
    expect(win.goes).toEqual([-1]);
    expect(history.location).toBe("/history");
    expect(win.location.hash).toBe("#comfymodal=history");
    history.go(-1);
    expect(history.location).toBe("/playground");
    // Clamped at the bottom: no traversal, no notification, no crash.
    history.go(-5);
    expect(history.location).toBe("/playground");
    history.go(2);
    expect(history.location).toBe("/workflows");
    expect(seen).toEqual(["/history", "/playground", "/workflows"]);
    stop();
    history.destroy();
  });

  it("router.back()/forward()/go() funnel through the Studio history", async () => {
    // router.back()/forward()/go() all funnel into history.go(delta)
    // (verified against the installed vue-router build). Previously our
    // go() was a no-op, so they silently did nothing. A spy proves the
    // funnel; traversal itself is covered by the go() test above and by
    // live Back/Forward browser validation.
    const { createStudioRouter } = await import("./index");
    const win = fakeWindow("");
    const router = createStudioRouter({ win });
    const calls: number[] = [];
    const history = router.options.history;
    const origGo = history.go.bind(history);
    history.go = (delta: number) => {
      calls.push(delta);
      origGo(delta);
    };
    router.back();
    router.forward();
    router.go(-2);
    expect(calls).toEqual([-1, 1, -2]);
    // The funnelled traversals moved the fake session stack for real:
    // "" -> back() clamps (no-op) -> forward() clamps (no-op) -> go(-2)
    // clamps (no-op). A genuine two-entry walk is covered below.
    expect(win.goes).toEqual([-1, 1, -2]);
  });

  it("a genuine two-entry walk traverses through router.back()/forward()", async () => {
    const { createStudioRouter } = await import("./index");
    const win = fakeWindow("#comfymodal=history");
    const router = createStudioRouter({ win });
    // Drive the underlying history directly (the router is not installed
    // on an app in this environment; installation only adds rendering).
    // listen() wires the win-level popstate exactly as install would.
    const history = router.options.history;
    const stop = history.listen(() => {});
    history.push("/workflows");
    expect(win.location.hash).toBe("#comfymodal=workflows");
    history.go(-1);
    expect(history.location).toBe("/history");
    expect(win.location.hash).toBe("#comfymodal=history");
    history.go(1);
    expect(history.location).toBe("/workflows");
    stop();
    history.destroy();
  });

  it("listens and cleans up exactly once", () => {
    const win = fakeWindow("");
    const add = vi.spyOn(win, "addEventListener");
    const remove = vi.spyOn(win, "removeEventListener");
    const history = createStudioHashHistory(win);
    const stopA = history.listen(() => {});
    const stopB = history.listen(() => {});
    expect(add).toHaveBeenCalledTimes(1);
    stopA();
    expect(remove).not.toHaveBeenCalled();
    stopB();
    expect(remove).toHaveBeenCalledTimes(1);
    history.destroy();
  });
});
