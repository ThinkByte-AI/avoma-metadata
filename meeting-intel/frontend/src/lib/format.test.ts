import { describe, expect, it } from "vitest";
import { formatBytes, formatDuration, formatTimestamp } from "./format";

describe("formatDuration", () => {
  it("formats hours and minutes", () => {
    expect(formatDuration(3900)).toBe("1h 05m");
    expect(formatDuration(2520)).toBe("42m");
    expect(formatDuration(0)).toBe("0m");
  });
  it("shows a dash when unknown", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });
});

describe("formatTimestamp", () => {
  it("formats m:ss and h:mm:ss", () => {
    expect(formatTimestamp(245)).toBe("4:05");
    expect(formatTimestamp(3729)).toBe("1:02:09");
    expect(formatTimestamp(59.9)).toBe("0:59");
    expect(formatTimestamp(0)).toBe("0:00");
  });
  it("never shows negative time", () => {
    expect(formatTimestamp(-3)).toBe("0:00");
  });
});

describe("formatBytes", () => {
  it("uses decimal units", () => {
    expect(formatBytes(53_250_000_000)).toBe("53.3 GB");
    expect(formatBytes(1500)).toBe("1.5 KB");
    expect(formatBytes(999)).toBe("999 B");
    expect(formatBytes(0)).toBe("0 B");
  });
});

describe("displayEmail", async () => {
  const { displayEmail } = await import("./format");
  it("hides values that are not email addresses", () => {
    expect(displayEmail("harsha jakku")).toBeNull();
    expect(displayEmail(null)).toBeNull();
    expect(displayEmail("a@b.co")).toBe("a@b.co");
  });
});
