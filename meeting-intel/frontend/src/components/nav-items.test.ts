import { describe, expect, it } from "vitest";
import { NAV_ITEMS, visibleNavItems } from "./nav-items";

describe("navigation", () => {
  it("follows the spec order", () => {
    expect(NAV_ITEMS.map((i) => i.label)).toEqual([
      "Overview", "Search Meetings", "All Meetings", "Participants", "AI Assistant", "Analytics", "Data Ingestion", "Settings",
    ]);
  });
  it("hides Data Ingestion from standard users", () => {
    expect(visibleNavItems(false).map((i) => i.label)).not.toContain("Data Ingestion");
    expect(visibleNavItems(true).map((i) => i.label)).toContain("Data Ingestion");
  });
});
