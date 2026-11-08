import { render, screen } from "@testing-library/react";
import { Mic } from "lucide-react";
import { describe, expect, it } from "vitest";
import { StatCard } from "./stat-card";

describe("StatCard", () => {
  it("renders the label and the formatted value", () => {
    render(<StatCard label="Audio storage" value={53_250_000_000} format={(n) => `${(n / 1e9).toFixed(1)} GB`} icon={Mic} />);
    expect(screen.getByText("Audio storage")).toBeInTheDocument();
    expect(screen.getByText("53.3 GB")).toBeInTheDocument();
  });

  it("uses thousands separators by default", () => {
    render(<StatCard label="Meetings" value={3152} />);
    expect(screen.getByText((3152).toLocaleString())).toBeInTheDocument();
  });

  it("shows a skeleton instead of the value while loading", () => {
    const { container } = render(<StatCard label="Meetings" value={undefined} loading />);
    expect(screen.getByText("Meetings")).toBeInTheDocument();
    expect(container.querySelector('[data-slot="skeleton"]')).not.toBeNull();
    expect(screen.queryByText("—")).toBeNull();
  });

  it("shows a dash when there is no value and it is not loading", () => {
    render(<StatCard label="Meetings" value={undefined} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
