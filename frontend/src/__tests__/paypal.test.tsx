import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

let config: Record<string, unknown>;
vi.mock("@/lib/api", () => ({
  ApiError: class extends Error {},
  auth: { get: () => "t", set: () => {}, clear: () => {} },
  api: vi.fn(async (path: string) => (path === "/api/payments/config" ? config : {})),
}));
import { PayPalCheckout } from "@/components/shopping/PayPalCheckout";

const buttonsFactory = vi.fn();
const render_ = vi.fn(async () => {});
const close = vi.fn();

beforeEach(() => {
  buttonsFactory.mockReset(); render_.mockClear(); close.mockClear();
  buttonsFactory.mockImplementation(() => ({ render: render_, close }));
  (window as unknown as { paypal: unknown }).paypal = { Buttons: buttonsFactory };
  document.getElementById("paypal-sdk")?.remove();
  const s = document.createElement("script"); s.id = "paypal-sdk"; document.body.appendChild(s);     // pretend the SDK is already loaded
  config = { client_id: "cid", currency: "USD", configured: true, inr_rate: "83.00", environment: "sandbox", disable_funding: "" };
});

describe("PayPalCheckout", () => {
  it("renders the buttons without a tagline, inside a wrapper that keeps the light PayPal iframe transparent", async () => {
    render(<PayPalCheckout proposalId="p1" onDone={() => {}} />);
    await waitFor(() => expect(render_).toHaveBeenCalled());
    expect(buttonsFactory.mock.calls[0][0].style).toMatchObject({ tagline: false, label: "pay" });
    expect(screen.getByTestId("paypal-buttons").parentElement).toHaveStyle({ colorScheme: "light" });
  });
  it("does NOT re-mount the buttons when the parent re-renders with a new callback (that would kill an open PayPal popup)", async () => {
    const { rerender } = render(<PayPalCheckout proposalId="p1" onDone={() => {}} />);
    await waitFor(() => expect(render_).toHaveBeenCalledTimes(1));
    rerender(<PayPalCheckout proposalId="p1" onDone={() => {}} />);
    rerender(<PayPalCheckout proposalId="p1" onDone={() => {}} />);
    expect(buttonsFactory).toHaveBeenCalledTimes(1);
    expect(close).not.toHaveBeenCalled();
  });
  it("re-mounts when the proposal changes", async () => {
    const { rerender } = render(<PayPalCheckout proposalId="p1" onDone={() => {}} />);
    await waitFor(() => expect(render_).toHaveBeenCalledTimes(1));
    rerender(<PayPalCheckout proposalId="p2" onDone={() => {}} />);
    await waitFor(() => expect(buttonsFactory).toHaveBeenCalledTimes(2));
    expect(close).toHaveBeenCalledTimes(1);
  });
  it("tells the user to allow pop-ups and use a sandbox buyer account", async () => {
    render(<PayPalCheckout proposalId="p1" onDone={() => {}} />);
    expect(await screen.findByText(/Allow pop-ups for this site/)).toBeInTheDocument();
    expect(screen.getByText(/PayPal Sandbox buyer/)).toBeInTheDocument();
  });
  it("shows a clear error when PayPal credentials are missing", async () => {
    config = { ...config, configured: false, client_id: null };
    render(<PayPalCheckout proposalId="p1" onDone={() => {}} />);
    expect(await screen.findByText(/credentials are not configured/)).toBeInTheDocument();
  });
  it("shows a visible error when the buttons fail to render", async () => {
    render_.mockRejectedValueOnce(new Error("popup blocked"));
    render(<PayPalCheckout proposalId="p1" onDone={() => {}} />);
    expect(await screen.findByText(/Could not display PayPal buttons: popup blocked/)).toBeInTheDocument();
  });
});
