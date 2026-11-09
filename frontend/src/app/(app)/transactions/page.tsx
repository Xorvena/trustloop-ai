"use client";
import { Search } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { PolicyChecks, RiskSummary } from "@/components/shared/Checks";
import { PayPalCheckout } from "@/components/shopping/PayPalCheckout";
import { Button, Card, ConfirmDialog, EmptyState, ErrorState, Modal, PageHeader, SkeletonRows, StatusBadge, useToast } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/utils";
import type { AuditEntry, Proposal, TxRow } from "@/types";

interface Detail extends TxRow { proposal: Proposal; receipt: Record<string, string> | null; audit: AuditEntry[] }
const sel = "rounded-lg border border-navy-600 bg-navy-900 px-3 py-2 text-sm";

function DetailView({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { data, error, loading, reload } = useApi<Detail>(`/api/transactions/${id}`);
  const done = useCallback(() => { reload(); onChanged(); }, [reload, onChanged]);
  const toast = useToast();
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  async function cancel() {
    setCancelling(true);
    try { await api(`/api/proposals/${id}/cancel`, { method: "POST" }); toast("ok", "Proposal cancelled."); setConfirmCancel(false); done(); }
    catch (e) { toast("err", e instanceof ApiError ? e.message : "Could not cancel"); setConfirmCancel(false); } finally { setCancelling(false); }
  }
  if (loading && !data) return <SkeletonRows n={3} />;
  if (error || !data) return <ErrorState message={error ?? "Not found"} onRetry={reload} />;
  const p = data.proposal;
  return (
    <div className="space-y-4 text-sm">
      <div className="flex items-center justify-between"><div><p className="font-medium text-strong">{data.product_name}</p><p className="text-slate-500">{data.merchant} · {formatMoney(data.amount, data.currency)}</p></div><StatusBadge value={data.state} /></div>
      <PolicyChecks checks={p.decision_explanation.checks} />
      <RiskSummary risk={p.risk} />
      {(data.state === "AUTHORIZED" || data.state === "PAYPAL_ORDER_CREATED") && <PayPalCheckout proposalId={data.id} onDone={done} />}
      {["PENDING_APPROVAL", "AUTHORIZED", "PAYPAL_ORDER_CREATED"].includes(data.state) && (
        <div><Button variant="danger" onClick={() => setConfirmCancel(true)}>Cancel this proposal</Button><p className="mt-1 text-xs text-slate-500">Unpaid. Cancelling frees its budget and makes it impossible to pay.</p></div>)}
      <ConfirmDialog open={confirmCancel} danger busy={cancelling} title="Cancel this proposal?" confirmLabel="Cancel proposal" onConfirm={cancel} onClose={() => setConfirmCancel(false)}
        body={<>This cannot be undone. A cancelled proposal can never be paid, even if a PayPal order exists.</>} />
      {data.receipt && <div className="rounded-lg bg-navy-900 p-3"><p className="mb-1 font-medium text-strong">Receipt</p>{Object.entries(data.receipt).filter(([, v]) => v).map(([k, v]) => <p key={k} className="text-xs text-slate-400"><span className="text-slate-600">{k.replaceAll("_", " ")}:</span> <span className="font-mono">{v}</span></p>)}</div>}
      <div><p className="mb-1 font-medium text-strong">Audit trail</p><ul className="space-y-1">{data.audit.map((a) => <li key={a.id} className="text-xs text-slate-400"><span className="font-mono text-violet-400">{a.action}</span> · {a.actor} · {formatDate(a.timestamp)}</li>)}</ul></div>
    </div>
  );
}

export default function Transactions() {
  const [q, setQ] = useState(""); const [state, setState] = useState(""); const [decision, setDecision] = useState(""); const [sort, setSort] = useState("created_at"); const [order, setOrder] = useState("desc");
  const [open, setOpen] = useState<string | null>(null);
  const path = useMemo(() => { const p = new URLSearchParams({ sort, order }); if (q) p.set("q", q); if (state) p.set("state", state); if (decision) p.set("decision", decision); return `/api/transactions?${p}`; }, [q, state, decision, sort, order]);
  const { data, error, loading, reload } = useApi<TxRow[]>(path);

  function exportCsv() {
    if (!data?.length) return;
    const rows = [["id", "product", "merchant", "amount", "currency", "agent", "decision", "state", "payment_status", "created_at"], ...data.map((t) => [t.id, t.product_name, t.merchant, t.amount, t.currency, t.agent_id, t.decision ?? "", t.state, t.payment_status ?? "", t.created_at])];
    const csv = rows.map((r) => r.map((c) => `"${String(c).replaceAll('"', '""')}"`).join(",")).join("\n");
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })), download: "trustloop-transactions.csv" });
    a.click(); URL.revokeObjectURL(a.href);
  }

  return (
    <>
      <PageHeader title="Transaction History" subtitle="Every proposal with its decision and payment outcome." actions={<Button variant="outline" onClick={exportCsv} disabled={!data?.length}>Export CSV</Button>} />
      <Card className="mb-4 flex flex-wrap items-center gap-3 p-4">
        <div className="relative"><Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" /><input aria-label="Search" placeholder="Search product, merchant, ID" value={q} onChange={(e) => setQ(e.target.value)} className={`${sel} pl-9`} /></div>
        <select aria-label="State" className={sel} value={state} onChange={(e) => setState(e.target.value)}><option value="">All states</option>{["PENDING_APPROVAL", "AUTHORIZED", "PAYPAL_ORDER_CREATED", "CAPTURED", "BLOCKED", "REJECTED", "EXPIRED", "FAILED"].map((s) => <option key={s}>{s}</option>)}</select>
        <select aria-label="Decision" className={sel} value={decision} onChange={(e) => setDecision(e.target.value)}><option value="">All decisions</option>{["APPROVED", "REQUIRES_APPROVAL", "REVIEW", "BLOCKED"].map((s) => <option key={s}>{s}</option>)}</select>
        <select aria-label="Sort" className={sel} value={sort} onChange={(e) => setSort(e.target.value)}><option value="created_at">Sort: date</option><option value="amount">Sort: amount</option><option value="merchant">Sort: merchant</option></select>
        <select aria-label="Order" className={sel} value={order} onChange={(e) => setOrder(e.target.value)}><option value="desc">Descending</option><option value="asc">Ascending</option></select>
      </Card>
      <Card className="overflow-x-auto p-2">
        {loading && !data ? <div className="p-3"><SkeletonRows /></div> : error ? <div className="p-3"><ErrorState message={error} onRetry={reload} /></div> : !data?.length ? <EmptyState title="No transactions match" hint="Adjust filters or create a purchase proposal." /> : (
          <table className="w-full text-left text-sm"><thead className="text-xs text-slate-500"><tr><th className="p-3">ID</th><th>Product</th><th>Agent</th><th>Amount</th><th>Decision</th><th>Status</th><th>Payment</th><th>When</th></tr></thead>
            <tbody className="divide-y divide-navy-700">{data.map((t) => (
              <tr key={t.id} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setOpen(t.id)} onClick={() => setOpen(t.id)} className="cursor-pointer hover:bg-navy-800">
                <td className="p-3 font-mono text-xs text-slate-500">{t.id.slice(0, 8)}</td><td className="text-slate-200">{t.product_name}<div className="text-xs text-slate-500">{t.merchant}</div></td><td className="text-slate-400">{t.agent_name}</td>
                <td>{formatMoney(t.amount, t.currency)}</td><td><StatusBadge value={t.decision} /></td><td><StatusBadge value={t.state} /></td><td>{t.payment_status ? <StatusBadge value={t.payment_status} /> : <span className="text-xs text-slate-500">{["AUTHORIZED", "PAYPAL_ORDER_CREATED"].includes(t.state) ? "Not paid yet" : "—"}</span>}</td><td className="text-xs text-slate-500">{formatDate(t.created_at)}</td></tr>))}</tbody></table>)}
      </Card>
      <Modal open={!!open} onClose={() => setOpen(null)} title="Transaction details">{open && <DetailView id={open} onChanged={reload} />}</Modal>
    </>
  );
}
