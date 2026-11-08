import { describe, expect, it } from "vitest";
import { DEFAULT_REQUEST, requestToSearchParams, searchParamsToRequest } from "./search-params";
import type { SearchRequest } from "./types";

const FULL: SearchRequest = {
  q: "revenue growth",
  mode: "semantic",
  sort: "date_desc",
  page: 3,
  page_size: 20,
  filters: {
    participant_ids: [4, 9],
    speaker_ids: [2],
    owner: "Harsha",
    title: "weekly sync",
    date_preset: "30d",
    date_from: "2025-01-01",
    date_to: "2025-12-31",
    min_duration_min: 10,
    max_duration_min: 90,
    has_recording: true,
    has_transcript: false,
  },
};

describe("search params", () => {
  it("round-trips every field", () => {
    const p = requestToSearchParams(FULL);
    expect(p.get("participants")).toBe("4,9");
    expect(p.get("rec")).toBe("1");
    expect(p.get("tx")).toBe("0");
    expect(searchParamsToRequest(p)).toEqual(FULL);
  });

  it("omits defaults", () => {
    expect(requestToSearchParams(DEFAULT_REQUEST).toString()).toBe("");
    expect(searchParamsToRequest(new URLSearchParams())).toEqual(DEFAULT_REQUEST);
  });

  it("ignores junk values", () => {
    const r = searchParamsToRequest(new URLSearchParams("mode=bogus&page=-4&participants=1,x,3&preset=forever&mindur=abc"));
    expect(r.mode).toBe("auto");
    expect(r.page).toBe(1);
    expect(r.filters).toEqual({ participant_ids: [1, 3] });
  });

  it("keeps a query with special characters intact", () => {
    const r = { ...DEFAULT_REQUEST, q: 'price & "Q3" 100%' };
    expect(searchParamsToRequest(requestToSearchParams(r)).q).toBe('price & "Q3" 100%');
  });
});
