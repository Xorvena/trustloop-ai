"use client";
import { useEffect, useRef, useState } from "react";
import { ErrorState, Skeleton, useToast } from "@/components/shared/ui";
import { api, ApiError } from "@/lib/api";

interface PayPalConfig { client_id: string | null; currency: string; configured: boolean; inr_rate: string; environment: string; disable_funding?: string }
interface PayPalButtons { render: (el: HTMLElement) => Promise<void>; close: () => void }
interface PayPalSdk { Buttons: (o: {
  createOrder: () => Promise<string>; onApprove: (d: { orderID: string }) => Promise<void>;
  onError: (e: unknown) => void; onCancel: () => void; style?: Record<string, string | boolean>;
}) => PayPalButtons }
declare global { interface Window { paypal?: PayPalSdk } }

/** Renders PayPal Sandbox buttons. The browser sends ONLY the proposal id; the backend decides the amount. */
export function PayPalCheckout({ proposalId, onDone }: { proposalId: string; onDone: () => void }) {
  const toast = useToast();
  const box = useRef<HTMLDivElement>(null);
  const doneRef = useRef(onDone);               // keep the latest callback WITHOUT re-rendering the buttons: remounting them mid-checkout kills the popup
  useEffect(() => { doneRef.current = onDone; });
  const [cfg, setCfg] = useState<PayPalConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api<PayPalConfig>("/api/payments/config").then(setCfg).catch((e) => setError(e.message)); }, []);

  useEffect(() => {
    if (!cfg?.configured || !cfg.client_id) return;
    let buttons: PayPalButtons | null = null;
    let cancelled = false;
    const mount = async () => {
      if (cancelled || !window.paypal || !box.current) return;
      buttons = window.paypal.Buttons({
        style: { layout: "vertical", shape: "rect", label: "pay", tagline: false },
        createOrder: async () => (await api<{ paypal_order_id: string }>("/api/payments/create-order", { method: "POST", body: { proposal_id: proposalId } })).paypal_order_id,
        onApprove: async (d) => {
          try {
            const r = await api<{ already_captured: boolean }>("/api/payments/capture", { method: "POST", body: { paypal_order_id: d.orderID } });
            toast("ok", r.already_captured ? "Payment was already captured." : "Payment captured and verified by the backend.");
          } catch (e) { toast("err", e instanceof ApiError ? e.message : "Capture failed"); }
          doneRef.current();
        },
        onCancel: () => toast("err", "Checkout cancelled. No payment was made."),
        onError: (e) => {
          console.error("PayPal checkout error", e);
          toast("err", e instanceof ApiError ? e.message : `PayPal checkout error: ${(e as Error)?.message ?? "unknown"}`.slice(0, 220));
        },
      });
      try { await buttons.render(box.current); } catch (e) { if (!cancelled) setError(`Could not display PayPal buttons: ${(e as Error)?.message ?? "unknown error"}`); }
    };
    const id = "paypal-sdk";
    const existing = document.getElementById(id) as HTMLScriptElement | null;
    if (existing && window.paypal) void mount();
    else {
      const funding = cfg.disable_funding ? `&disable-funding=${encodeURIComponent(cfg.disable_funding)}` : "";
      const s = existing ?? Object.assign(document.createElement("script"), {
        id, src: `https://www.paypal.com/sdk/js?client-id=${encodeURIComponent(cfg.client_id)}&currency=${cfg.currency}&intent=capture${funding}`,
      });
      s.addEventListener("load", () => void mount());
      s.addEventListener("error", () => setError("Could not load the PayPal SDK."));
      if (!existing) document.body.appendChild(s);
    }
    return () => { cancelled = true; try { buttons?.close(); } catch { /* ignore */ } };
  }, [cfg, proposalId, toast]);

  if (error) return <ErrorState message={error} />;
  if (!cfg) return <Skeleton className="h-24 w-full" />;
  if (!cfg.configured) return <ErrorState message="PayPal sandbox credentials are not configured on the backend (PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET). Payment is unavailable until they are set." />;
  return (
    <div>
      <p className="mb-2 text-xs text-slate-500">PayPal {cfg.environment} · settles in {cfg.currency} (demo rate 1 {cfg.currency} = ₹{cfg.inr_rate}). No real money moves.</p>
      {/* The PayPal buttons live in a LIGHT iframe. In a dark-scheme page the browser paints such iframes opaque white; telling the
          wrapper it is `light` makes the iframe transparent so the buttons sit directly on the card. */}
      <div style={{ colorScheme: "light" }}><div ref={box} data-testid="paypal-buttons" /></div>
      <p className="mt-2 text-xs text-slate-500">Allow pop-ups for this site. Sign in with a <b>PayPal Sandbox buyer</b> account (developer.paypal.com → Sandbox → Accounts), not your real PayPal login.</p>
    </div>
  );
}
