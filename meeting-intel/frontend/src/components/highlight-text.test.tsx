import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HighlightText, mergeRanges } from "./highlight-text";

describe("HighlightText", () => {
  it("marks exactly the given range", () => {
    const { container } = render(<HighlightText text="Revenue grew" ranges={[[0, 7]]} />);
    const marks = container.querySelectorAll("mark");
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe("Revenue");
    expect(container.textContent).toBe("Revenue grew");
  });

  it("merges overlapping ranges", () => {
    expect(mergeRanges([[0, 3], [2, 5], [8, 9]])).toEqual([[0, 5], [8, 9]]);
    expect(mergeRanges([[5, 2]])).toEqual([]);
  });

  it("renders script text as plain text", () => {
    const { container } = render(<HighlightText text="<script>alert(1)</script>" ranges={[[0, 8]]} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toBe("<script>alert(1)</script>");
  });

  it("clamps ranges to the text and uses a softer style for semantic matches", () => {
    const { container } = render(<HighlightText text="abc" ranges={[[1, 99]]} variant="semantic" />);
    const mark = container.querySelector("mark")!;
    expect(mark.textContent).toBe("bc");
    expect(mark.dataset.variant).toBe("semantic");
  });
});
