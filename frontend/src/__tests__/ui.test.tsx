import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PolicyChecks, RiskSummary } from "@/components/shared/Checks";
import { EmptyState, ErrorState, StatusBadge } from "@/components/shared/ui";
import { formatMoney, timeLeft } from "@/lib/utils";

describe("utils", () => {
  it("formats INR with Indian grouping", () => { expect(formatMoney("75000", "INR")).toContain("75,000"); });
  it("reports expiry", () => { expect(timeLeft(new Date(Date.now() - 1000).toISOString())).toBe("Expired"); });
  it("treats zone-less backend timestamps as UTC", () => {
    const future = new Date(Date.now() + 5 * 60000).toISOString().replace("Z", "");
    expect(timeLeft(future)).toMatch(/^[45]m/);
  });
});

describe("components", () => {
  it("StatusBadge renders readable status", () => { render(<StatusBadge value="REQUIRES_APPROVAL" />); expect(screen.getByText("REQUIRES APPROVAL")).toBeInTheDocument(); });
  it("EmptyState shows hint", () => { render(<EmptyState title="Nothing" hint="Try later" />); expect(screen.getByText("Try later")).toBeInTheDocument(); });
  it("ErrorState is an alert", () => { render(<ErrorState message="boom" />); expect(screen.getByRole("alert")).toHaveTextContent("boom"); });
  it("PolicyChecks lists failed and passed rules", () => {
    render(<PolicyChecks checks={[{ rule: "agent_active", passed: true, severity: "BLOCK", detail: "ok" }, { rule: "budget_remaining", passed: false, severity: "BLOCK", detail: "too much" }]} />);
    expect(screen.getByText(/too much/)).toBeInTheDocument(); expect(screen.getByText("agent_active")).toBeInTheDocument();
  });
  it("RiskSummary labels AI advisory signals and disclaims fraud detection", () => {
    render(<RiskSummary risk={{ score: 40, level: "medium", ai_used: true, signals: [], ai_signals: [{ code: "x", points: 5, detail: "odd wording", source: "gemini_advisory" }] }} />);
    expect(screen.getByText(/AI advisory/)).toBeInTheDocument(); expect(screen.getByText(/not fraud detection/)).toBeInTheDocument();
  });
});
