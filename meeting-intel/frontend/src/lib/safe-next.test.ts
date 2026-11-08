import { describe, expect, it } from "vitest";
import { safeNext } from "./safe-next";

describe("safeNext", () => {
  it("keeps same-site paths with their query", () => {
    expect(safeNext("/overview?x=1")).toBe("/overview?x=1");
    expect(safeNext("/search?q=a%20b#r")).toBe("/search?q=a%20b#r");
  });

  it.each([
    ["/\\evil.com"],
    ["//evil.com"],
    ["https://evil.com"],
    ["javascript:alert(1)"],
    ["\\\\evil.com"],
    [""],
    [null],
  ])("falls back for %s", (next) => {
    expect(safeNext(next)).toBe("/overview");
  });
});
