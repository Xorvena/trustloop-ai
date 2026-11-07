import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const calls: { path: string; method?: string }[] = [];
let budget: unknown;
vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {},
  auth: { get: () => "t", set: () => {}, clear: () => {} },
  api: vi.fn(async (path: string, init: { method?: string } = {}) => { calls.push({ path, ...init }); if (path === "/api/budget") return budget; return {}; }),
}));
import { BudgetPanel } from "@/components/shopping/BudgetPanel";

const stuck = { policy_active: true, currency: "INR", max_budget: "75000.00", committed: "62990.00", remaining: "12010.00",
  items: [{ proposal_id: "p1", product_name: "Aero 14 Developer Laptop", merchant: "TechMart India", amount: "62990.00", currency: "INR", state: "AUTHORIZED", cancellable: true, created_at: "2026-11-06T10:00:00", authorization_expires_at: new Date(Date.now() + 20 * 60000).toISOString() },
          { proposal_id: "p2", product_name: "Lite 13 Student Laptop", merchant: "GadgetWorld", amount: "1000.00", currency: "INR", state: "CAPTURED", cancellable: false, created_at: "2026-11-05T10:00:00", authorization_expires_at: null }] };
beforeEach(() => { calls.length = 0; budget = stuck; });

describe("BudgetPanel", () => {
  it("shows remaining budget and flags unpaid proposals", async () => {
    render(<BudgetPanel />);
    expect(await screen.findByText(/budget remaining/)).toBeInTheDocument();
    expect(screen.getByText(/₹12,010\.00/)).toBeInTheDocument();
    expect(screen.getByText("1 unpaid")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "84");
  });
  it("explains what is using the budget and lets the user cancel only the unpaid one", async () => {
    render(<BudgetPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /What's using my budget/ }));
    expect(screen.getByText(/Aero 14 Developer Laptop/)).toBeInTheDocument();
    expect(screen.getByText(/paid \(counts permanently\)/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Cancel" })).toHaveLength(1);          // the captured purchase has no cancel button
  });
  it("cancels after confirmation via POST", async () => {
    render(<BudgetPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /What's using my budget/ }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel proposal" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/proposals/p1/cancel" && c.method === "POST")).toBe(true));
  });
  it("tells the user when no policy is active", async () => {
    budget = { policy_active: false, currency: "INR", max_budget: null, committed: "0", remaining: null, items: [] };
    render(<BudgetPanel />);
    expect(await screen.findByText(/No active policy/)).toBeInTheDocument();
  });
});
