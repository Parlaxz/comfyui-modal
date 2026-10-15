// http.ts — focused unit tests.
// Proves: base path, JSON round-trip, structured error extraction
// precedence, AbortSignal + timeout behavior.
import { describe, expect, it, vi } from "vitest";
import {
  extractErrorMessage,
  requestJson,
  STUDIO_API_BASE,
  StudioHttpError,
} from "./http";

function jsonResponse(status: number, body: unknown): Response {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return new Response(text, {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("extractErrorMessage", () => {
  it("follows the pinned precedence", () => {
    expect(extractErrorMessage("plain string", "fb")).toBe("plain string");
    expect(extractErrorMessage({ message: "m" }, "fb")).toBe("m");
    expect(extractErrorMessage({ error: "e" }, "fb")).toBe("e");
    expect(extractErrorMessage({ message: "m", error: "e" }, "fb")).toBe("m");
    expect(extractErrorMessage({ detail: "d" }, "fb")).toBe("d");
    expect(extractErrorMessage({ detail: { message: "dm" } }, "fb")).toBe("dm");
    expect(extractErrorMessage({ detail: { code: "c" } }, "fb")).toBe("c");
    expect(extractErrorMessage(null, "fb")).toBe("fb");
    expect(extractErrorMessage({ other: 1 }, "fb")).toBe("fb");
    expect(extractErrorMessage("", "fb")).toBe("fb");
  });
});

describe("requestJson", () => {
  it("requests under the /comfymodal base and parses JSON", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { ok: true }));
    const result = await requestJson<{ ok: boolean }>(
      "/config",
      {},
      fetchImpl as unknown as typeof fetch,
    );
    expect(result).toEqual({ ok: true });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(STUDIO_API_BASE + "/config");
    expect(init.method).toBe("GET");
  });

  it("throws structured errors on non-OK responses", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(500, { error: "kaput" }));
    const failure = await requestJson("/deploy", {}, fetchImpl as unknown as typeof fetch).catch(
      (e) => e,
    );
    expect(failure).toBeInstanceOf(StudioHttpError);
    expect((failure as StudioHttpError).status).toBe(500);
    expect((failure as StudioHttpError).message).toBe("kaput");
  });

  it("honors an external abort", async () => {
    const controller = new AbortController();
    controller.abort();
    const fetchImpl = vi.fn(async (_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      }),
    );
    await expect(
      requestJson("/config", { signal: controller.signal }, fetchImpl as typeof fetch),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("imposes no deadline unless the caller opts in", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { ok: true }));
    await requestJson("/config", {}, fetchImpl as unknown as typeof fetch);
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.signal).toBeUndefined();
  });

  it("enforces an explicit caller deadline when the server never answers", async () => {
    const fetchImpl = async (_url: string, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () =>
          reject(new DOMException("Timed out", "TimeoutError")),
        );
      });
    await expect(
      requestJson("/config", { timeoutMs: 10 }, fetchImpl as typeof fetch),
    ).rejects.toMatchObject({ name: "TimeoutError" });
  });
});
