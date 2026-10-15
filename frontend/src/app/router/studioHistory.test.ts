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
} {
  const listeners = new Map<string, Set<() => void>>();
  const win: StudioWindow & {
    firePopState: () => void;
    pushes: string[];
    replaces: string[];
  } = {
    location: { hash, pathname: "/", search: "" },
    pushes: [],
    replaces: [],
    history: {
      pushState: (_d, _t, url) => {
        win.pushes.push(String(url));
        const hashIndex = String(url).indexOf("#");
        win.location.hash = hashIndex === -1 ? "" : String(url).slice(hashIndex);
      },
      replaceState: (_d, _t, url) => {
        win.replaces.push(String(url));
        const hashIndex = String(url).indexOf("#");
        win.location.hash = hashIndex === -1 ? "" : String(url).slice(hashIndex);
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
      listeners.get("popstate")?.forEach((fn) => fn());
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
