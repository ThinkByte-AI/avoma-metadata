import { describe, expect, it } from "vitest";
import { embedPercent, progressPercent } from "./ingestion";

describe("progressPercent", () => {
  it("is processed / to_process", () => {
    expect(progressPercent({ processed: 5, to_process: 10 })).toBe(50);
  });
  it("is 0 when unknown", () => {
    expect(progressPercent({})).toBe(0);
    expect(progressPercent({ processed: 3 })).toBe(0);
    expect(progressPercent({ processed: 0, to_process: 0 })).toBe(0);
  });
  it("is capped at 100", () => {
    expect(progressPercent({ processed: 12, to_process: 10 })).toBe(100);
  });
});

describe("embedPercent", () => {
  it("is embedded / to_embed with the same rules", () => {
    expect(embedPercent({ embedded: 1, to_embed: 4 })).toBe(25);
    expect(embedPercent({ embedded: 9 })).toBe(0);
    expect(embedPercent({ embedded: 9, to_embed: 3 })).toBe(100);
  });
});
