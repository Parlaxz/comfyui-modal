// Modal Studio Vue substrate — minimal API helper.
//
// Only what Phase 1 needs: JSON requests under the `/comfymodal` base with
// structured error extraction and AbortSignal/timeout support.
//
// Deliberately NOT forced through here: NDJSON batch streams, FormData
// image uploads, blobs, reboot-disconnect flows, long polling. Those keep
// their specialized transports; a generic helper must not flatten them.

export const STUDIO_API_BASE = "/comfymodal";

export interface RequestJsonOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  /**
   * Opt-in deadline for this call. There is deliberately NO universal
   * default: long polls, reboot disconnects, and streaming transports must
   * never inherit a generic timeout. Callers that need a bound pass one
   * explicitly (domain APIs own their deadlines).
   */
  timeoutMs?: number;
  headers?: Record<string, string>;
}

/** Canonical frontend error: message first, details preserved. */
export class StudioHttpError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(status: number, message: string, payload?: unknown) {
    super(message);
    this.name = "StudioHttpError";
    this.status = status;
    this.payload = payload;
  }
}

/**
 * Extract a human-usable message from an unknown error payload.
 * Precedence: string → `.message` → `.error` → nested
 * `detail/message/code` → HTTP fallback. Pinned by test.
 */
export function extractErrorMessage(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim() !== "") return payload;
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    for (const key of ["message", "error"] as const) {
      const value = record[key];
      if (typeof value === "string" && value.trim() !== "") return value;
    }
    const detail = record["detail"];
    if (typeof detail === "string" && detail.trim() !== "") return detail;
    if (detail && typeof detail === "object") {
      const nested = detail as Record<string, unknown>;
      for (const key of ["message", "code"] as const) {
        const value = nested[key];
        if (typeof value === "string" && value.trim() !== "") return value;
      }
    }
  }
  return fallback;
}

function combineSignals(
  external: AbortSignal | undefined,
  timeoutMs: number | undefined,
): { signal: AbortSignal | undefined; cleanup: () => void } {
  if (timeoutMs === undefined) {
    if (!external) return { signal: undefined, cleanup: () => {} };
    return { signal: external, cleanup: () => {} };
  }
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(new DOMException("Request timed out", "TimeoutError")),
    timeoutMs,
  );
  const onExternalAbort = () => controller.abort(external?.reason);
  if (external) {
    if (external.aborted) controller.abort(external.reason);
    else external.addEventListener("abort", onExternalAbort, { once: true });
  }
  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer);
      external?.removeEventListener("abort", onExternalAbort);
    },
  };
}

export async function requestJson<T>(
  path: string,
  options: RequestJsonOptions = {},
  fetchImpl: typeof fetch = fetch,
): Promise<T> {
  const {
    method = "GET",
    body,
    signal: externalSignal,
    timeoutMs,
    headers = {},
  } = options;
  const { signal, cleanup } = combineSignals(externalSignal, timeoutMs);
  try {
    // A pre-aborted signal rejects without touching fetch (native fetch
    // semantics: an aborted signal never dispatches a request).
    if (signal && signal.aborted) throw signal.reason;
    const response = await fetchImpl(STUDIO_API_BASE + path, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
    const text = await response.text();
    let payload: unknown = null;
    if (text !== "") {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = text;
      }
    }
    if (!response.ok) {
      throw new StudioHttpError(
        response.status,
        extractErrorMessage(payload, `Request failed with status ${response.status}`),
        payload,
      );
    }
    return payload as T;
  } finally {
    cleanup();
  }
}
