import { describe, expect, it } from "vitest";
import { splitCitations } from "./citations";

describe("splitCitations", () => {
  it("splits text and citation markers in order", () => {
    expect(splitCitations("Revenue grew [1][3].")).toEqual([
      { type: "text", value: "Revenue grew " },
      { type: "cite", n: 1 },
      { type: "cite", n: 3 },
      { type: "text", value: "." },
    ]);
  });

  it("ignores brackets that are not plain numbers", () => {
    expect(splitCitations("See [x] and [10a] here")).toEqual([{ type: "text", value: "See [x] and [10a] here" }]);
  });

  it("handles a marker at the start, multi-digit numbers and empty input", () => {
    expect(splitCitations("[12] first")).toEqual([
      { type: "cite", n: 12 },
      { type: "text", value: " first" },
    ]);
    expect(splitCitations("")).toEqual([]);
  });
});
