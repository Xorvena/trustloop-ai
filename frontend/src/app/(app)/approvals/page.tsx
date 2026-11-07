"use client";
import { Check, Clock, X } from "lucide-react";
import { useEffect, useState } from "react";
import { PolicyChecks, RiskSummary } from "@/components/shared/Checks";
import { PayPalCheckout } from "@/components/shopping/PayPalCheckout";
import { ProductImage } from "@/components/shopping/ProductImage";
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Modal, PageHeader, SkeletonRows, StatusBadge, useToast } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/lib/api";
import { formatMoney, timeLeft } from "@/lib/utils";
import type { Approval } from "@/types";

export default function Approvals() {
  const { data, error, loading, reload } = useApi<Approval[]>("/api/approvals/pending");
  const toast = useToast();
  const [now, setNow] = useState(Date.now());
  const [pending, setPending] = useState<{ a: Approval; decision: "approve" | "reject" } | null>(null);
  const [busy, setBusy] = useState(false);
  const [pay, setPay] = useState<string | null>(null);

  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);

  async function decide() {
    if (!pending) return; setBusy(true);
    try {
      await api(`/api/approvals/${pending.a.id}/decision`, { method: "POST", body: { decision: pending.decision } });
      toast("ok", pending.decision === "approve" ? "Approved. The backend revalidated all rules." : "Rejected.");
      if (pending.decision === "approve") setPay(pending.a.proposal_id);
      setPending(null); reload();
    } catch (e) { toast("err", e instanceof ApiError ? e.message : "Decision failed"); setPending(null); reload(); } finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader title="Approval Center" subtitle="Each approval is bound to the exact amount, merchant, product, agent and expiry shown." />
      {loading && !data ? <SkeletonRows n={3} /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.length ? <Card><EmptyState title="Nothing awaiting approval" hint="Purchases above your approval threshold, or from unapproved merchants, appear here." /></Card> : (
        <div className="grid gap-4 xl:grid-cols-2">{data.map((a) => {
          const left = timeLeft(a.expires_at, now);
          return (
            <Card key={a.id} className="p-5">
              <div className="flex gap-4">
                <ProductImage src={a.image_url} source={a.image_source} name={a.product_name} className="h-20 w-24 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium text-white">{a.product_name}</p><Badge tone={a.kind === "REVIEW" ? "amber" : "violet"}>{a.kind.replaceAll("_", " ")}</Badge></div>
                  <p className="text-sm text-slate-400">{a.merchant}</p>
                  <p className="mt-1 text-xl font-semibold text-white">{formatMoney(a.amount, a.currency)}</p>
                  <p className="mt-1 text-xs text-slate-500">Agent {a.agent_name} <span className="font-mono">({a.agent_id})</span> · trust {a.agent_trust_score ?? "—"}/100 <span className="text-slate-600">(informational only)</span></p>
                </div>
              </div>
              <p className="mt-3 rounded-lg bg-navy-900 p-3 text-sm text-slate-300"><span className="text-slate-500">Why approval is needed: </span>{a.reason}</p>
              <details className="mt-3 text-sm"><summary className="cursor-pointer text-violet-400">Policy checks and risk assessment</summary><div className="mt-2 space-y-3"><PolicyChecks checks={a.policy_evaluation.checks} /><RiskSummary risk={a.risk} /></div></details>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
                <span className={`flex items-center gap-1 text-sm ${left === "Expired" ? "text-bad" : "text-warn"}`}><Clock className="h-4 w-4" />{left}</span>
                <div className="flex gap-2"><Button variant="danger" onClick={() => setPending({ a, decision: "reject" })}><X className="h-4 w-4" />Reject</Button>
                  <Button variant="success" disabled={left === "Expired"} onClick={() => setPending({ a, decision: "approve" })}><Check className="h-4 w-4" />Approve</Button></div>
              </div>
            </Card>);
        })}</div>)}
      <ConfirmDialog open={!!pending} danger={pending?.decision === "reject"} busy={busy} title={pending?.decision === "approve" ? "Approve this purchase?" : "Reject this purchase?"}
        confirmLabel={pending?.decision === "approve" ? "Approve" : "Reject"} onConfirm={decide} onClose={() => setPending(null)}
        body={pending && <>You are {pending.decision === "approve" ? "authorizing" : "rejecting"} <b>{formatMoney(pending.a.amount, pending.a.currency)}</b> to <b>{pending.a.merchant}</b> for <b>{pending.a.product_name}</b>. Payment still requires PayPal checkout, and the backend revalidates everything first.</>} />
      <Modal open={!!pay} onClose={() => setPay(null)} title="Complete payment">
        {pay && <div className="space-y-3"><p className="text-sm text-slate-400">Approved. Pay with your PayPal Sandbox buyer account.</p><PayPalCheckout proposalId={pay} onDone={() => { setPay(null); reload(); }} /></div>}
      </Modal>
    </>
  );
}
