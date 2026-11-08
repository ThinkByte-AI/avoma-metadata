import { describe, expect, it } from "vitest";
import { filterSegments, findActiveSegment } from "./transcript";

const segs = [{ start_sec: 10 }, { start_sec: 20 }, { start_sec: 35 }];

describe("findActiveSegment", () => {
  it("handles empty and before-first", () => {
    expect(findActiveSegment([], 5)).toBe(-1);
    expect(findActiveSegment(segs, 9.9)).toBe(-1);
  });
  it("finds the last segment that has started", () => {
    expect(findActiveSegment(segs, 10)).toBe(0);
    expect(findActiveSegment(segs, 34.9)).toBe(1);
    expect(findActiveSegment(segs, 35)).toBe(2);
    expect(findActiveSegment(segs, 9999)).toBe(2);
  });
});

describe("filterSegments", () => {
  const texts = [{ text: "Revenue grew. revenue!" }, { text: "Nothing here" }, { text: "REVENUE targets" }];
  it("finds case-insensitive matches with ranges", () => {
    expect(filterSegments(texts, "revenue")).toEqual([
      { index: 0, ranges: [[0, 7], [14, 21]] },
      { index: 2, ranges: [[0, 7]] },
    ]);
  });
  it("returns nothing for a blank query", () => {
    expect(filterSegments(texts, "  ")).toEqual([]);
  });
});
