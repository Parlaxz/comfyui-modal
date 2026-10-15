// persistence.ts — focused unit tests.
// Proves: read/write/delete, malformed JSON fallback, Zod-invalid fallback,
// default behavior, namespaced keys.
import { describe, expect, it } from "vitest";
import { z } from "zod";
import {
  definePersisted,
  PERSISTENCE_NAMESPACE,
  type PersistedStore,
} from "./persistence";

function testStore(seed: Record<string, string> = {}): PersistedStore & { raw: Map<string, string> } {
  const raw = new Map(Object.entries(seed));
  return {
    raw,
    getItem: (k) => (raw.has(k) ? raw.get(k)! : null),
    setItem: (k, v) => {
      raw.set(k, v);
    },
    removeItem: (k) => {
      raw.delete(k);
    },
  };
}

describe("definePersisted", () => {
  it("writes and reads back under a namespaced key", () => {
    const store = testStore();
    const pref = definePersisted("shell.density", "comfortable", undefined, store);
    expect(pref.key).toBe(PERSISTENCE_NAMESPACE + "shell.density");
    expect(pref.read()).toBe("comfortable");
    pref.write("compact");
    expect(pref.read()).toBe("compact");
    expect(store.raw.get(PERSISTENCE_NAMESPACE + "shell.density")).toBe('"compact"');
  });

  it("deletes back to the fallback", () => {
    const store = testStore();
    const pref = definePersisted("x", "fallback", undefined, store);
    pref.write("custom");
    pref.remove();
    expect(pref.read()).toBe("fallback");
  });

  it("malformed JSON fails safely to the fallback", () => {
    const store = testStore({ [PERSISTENCE_NAMESPACE + "x"]: "{not json" });
    const pref = definePersisted("x", "fallback", undefined, store);
    expect(pref.read()).toBe("fallback");
  });

  it("Zod-invalid values fail safely to the fallback", () => {
    const schema = z.enum(["comfortable", "compact"]);
    const store = testStore({ [PERSISTENCE_NAMESPACE + "shell.density"]: '"mega-wide"' });
    const pref = definePersisted("shell.density", "comfortable", schema, store);
    expect(pref.read()).toBe("comfortable");
  });

  it("Zod-valid values pass through", () => {
    const schema = z.object({ section: z.string() });
    const store = testStore({
      [PERSISTENCE_NAMESPACE + "ui"]: JSON.stringify({ section: "studio" }),
    });
    const pref = definePersisted("ui", { section: "default" }, schema, store);
    expect(pref.read()).toEqual({ section: "studio" });
  });

  it("missing keys and throwing storage resolve to the fallback", () => {
    const empty = testStore();
    expect(definePersisted("absent", 42, undefined, empty).read()).toBe(42);
    const bomb: PersistedStore = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };
    const pref = definePersisted("x", "fallback", undefined, bomb);
    expect(pref.read()).toBe("fallback");
    expect(() => pref.write("v")).not.toThrow();
    expect(() => pref.remove()).not.toThrow();
  });
});
