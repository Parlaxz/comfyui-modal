// Modal Studio Vue substrate — explicit persistence helper.
//
// One deliberate alternative to a Pinia persistence plugin: persistence is
// opt-in per value, never per store. This makes intentional persistence
// easy (a named preference with a fallback) without making whole-store
// persistence easy (which would silently durable server entities,
// operation state, and other things that must stay in memory).
//
// Rules:
// - Keys are namespaced (`comfymodal.studio.vue.<name>`).
// - Reads never throw: malformed JSON or Zod-invalid values resolve to the
//   caller-provided fallback.
// - Values are plain JSON; nothing here knows about stores, Pinia, or the
//   backend. Do NOT persist operation state or server entities with this.

import type { z } from "zod";

export const PERSISTENCE_NAMESPACE = "comfymodal.studio.vue.";

export interface PersistedStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

function memoryStore(): PersistedStore {
  const map = new Map<string, string>();
  return {
    getItem: (key) => (map.has(key) ? map.get(key)! : null),
    setItem: (key, value) => {
      map.set(key, value);
    },
    removeItem: (key) => {
      map.delete(key);
    },
  };
}

function defaultStore(): PersistedStore {
  try {
    if (typeof localStorage !== "undefined") {
      const probe = "__comfymodal_probe__";
      localStorage.setItem(probe, "1");
      localStorage.removeItem(probe);
      return localStorage;
    }
  } catch {
    // Storage unavailable (private mode, SSR, tests): fall back to memory
    // so callers never have to branch.
  }
  return memoryStore();
}

export interface Persisted<T> {
  readonly key: string;
  read(): T;
  write(value: T): void;
  remove(): void;
}

/**
 * Define one explicitly persisted value.
 *
 * @param name     Short key suffix; namespaced automatically.
 * @param fallback Value returned when nothing usable is stored.
 * @param schema   Optional Zod schema for nontrivial durable values.
 *                 Malformed or schema-invalid data resolves to `fallback`.
 * @param storage  Injectable storage (defaults to guarded localStorage).
 */
export function definePersisted<T>(
  name: string,
  fallback: T,
  schema?: z.ZodType<T>,
  storage?: PersistedStore,
): Persisted<T> {
  const key = PERSISTENCE_NAMESPACE + name;
  const store = storage ?? defaultStore();
  return {
    key,
    read(): T {
      let raw: string | null = null;
      try {
        raw = store.getItem(key);
      } catch {
        return fallback;
      }
      if (raw === null) return fallback;
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        return fallback;
      }
      if (!schema) return (parsed ?? fallback) as T;
      const result = schema.safeParse(parsed);
      return result.success ? result.data : fallback;
    },
    write(value: T): void {
      try {
        store.setItem(key, JSON.stringify(value));
      } catch {
        // Persistence is best-effort; a full/blocked store must never
        // break the UI that wanted to remember a preference.
      }
    },
    remove(): void {
      try {
        store.removeItem(key);
      } catch {
        // Same best-effort rule as write.
      }
    },
  };
}
