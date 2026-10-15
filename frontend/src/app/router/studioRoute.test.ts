// studioRoute codec — focused unit tests.
// Proves the frozen contract: five routes serialize/parse, focus support,
// unrelated hashes never match, malformed hashes fail soft, push/replace
// intent matrix, explicit-opener precedence. Mirrors the legacy
// web/studio-routing.js vectors so the parallel implementations stay in parity.
import { describe, expect, it } from "vitest";
import {
  decideHistoryAction,
  isStudioPage,
  parseStudioHash,
  resolveInitialRoute,
  serializeStudioHash,
  STUDIO_PAGES,
  STUDIO_PAGE_LABELS,
} from "./studioRoute";

describe("studioRoute codec", () => {
  it("has exactly five pages; backend keeps its route key with a Manage Modal label", () => {
    expect([...STUDIO_PAGES]).toEqual([
      "playground",
      "history",
      "workflows",
      "backend",
      "settings",
    ]);
    expect(STUDIO_PAGE_LABELS.backend).toBe("Manage Modal");
    expect(isStudioPage("docs")).toBe(false);
    expect(isStudioPage("backend")).toBe(true);
  });

  it("serializes and parses all five routes", () => {
    for (const page of STUDIO_PAGES) {
      const hash = serializeStudioHash({ page });
      expect(hash).toBe(`#comfymodal=${page}`);
      expect(parseStudioHash(hash)).toEqual({ matched: true, page, focus: null });
    }
  });

  it("round-trips focus values", () => {
    expect(serializeStudioHash({ page: "history", focus: "gen_123" })).toBe(
      "#comfymodal=history&focus=gen_123",
    );
    expect(parseStudioHash("#comfymodal=history&focus=gen_123")).toEqual({
      matched: true,
      page: "history",
      focus: "gen_123",
    });
    expect(parseStudioHash("#comfymodal=settings&focus=my%20section").focus).toBe(
      "my section",
    );
    expect(parseStudioHash("#comfymodal=history&focus=").focus).toBeNull();
  });

  it("never interprets unrelated ComfyUI hashes", () => {
    for (const hash of [
      "",
      "#",
      "#workflow=abc",
      "#comfyui",
      "#/graph/123",
      "comfymodal-vue=playground",
    ]) {
      expect(parseStudioHash(hash).matched).toBe(false);
    }
    expect(serializeStudioHash({ page: "docs" })).toBe("");
  });

  it("malformed Studio hashes fail soft, never throw", () => {
    expect(parseStudioHash("#comfymodal=nothing").matched).toBe(false);
    expect(parseStudioHash("#comfymodal=").matched).toBe(false);
    expect(parseStudioHash("#comfymodal=%E0%A4%A").matched).toBe(false);
    // Malformed focus keeps the page route, drops the focus.
    expect(parseStudioHash("#comfymodal=history&focus=%E0%A4%A")).toEqual({
      matched: true,
      page: "history",
      focus: null,
    });
    // First focus wins; unknown params ignored.
    expect(
      parseStudioHash("#comfymodal=history&foo=1&focus=one&focus=two").focus,
    ).toBe("one");
  });

  it("implements the push/replace/none history matrix", () => {
    expect(
      decideHistoryAction({ page: "playground", focus: null }, { page: "history", focus: null }),
    ).toBe("push");
    expect(
      decideHistoryAction({ page: "history", focus: null }, { page: "history", focus: "a" }),
    ).toBe("replace");
    expect(
      decideHistoryAction({ page: "history", focus: "a" }, { page: "history", focus: "a" }),
    ).toBe("none");
    expect(decideHistoryAction(null, { page: "playground", focus: null })).toBe("replace");
    expect(
      decideHistoryAction({ page: "playground", focus: null }, { page: "docs", focus: null }),
    ).toBe("none");
    expect(decideHistoryAction({ page: "playground", focus: null }, null)).toBe("none");
  });

  it("explicit opener overrides a stale hash; close-era hashes are honored on open", () => {
    expect(
      resolveInitialRoute({ page: "settings" }, "#comfymodal=history"),
    ).toEqual({ page: "settings", focus: null });
    expect(resolveInitialRoute(undefined, "#comfymodal=backend")).toEqual({
      page: "backend",
      focus: null,
    });
    expect(resolveInitialRoute(undefined, "#unrelated")).toEqual({
      page: "playground",
      focus: null,
    });
    expect(resolveInitialRoute({ page: "docs" }, "#comfymodal=history")).toEqual({
      page: "history",
      focus: null,
    });
  });
});
