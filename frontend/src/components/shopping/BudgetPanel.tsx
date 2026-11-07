"use client";
import { ChevronDown, ChevronUp, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Button, Card, ConfirmDialog, ErrorState, Skeleton, StatusBadge, useToast } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/lib/api";
import { formatMoney, timeLeft } from "@/lib/utils";
import type { Budget, BudgetItem } from "@/types";

/** Shows how much of the policy budget is committed and WHICH proposals hold it, with a Cancel button for unpaid ones.
 *  Without this, an approved-but-unpaid purchase silently reserves budget and later purchases get BLOCKED. */
export function BudgetPanel({ refreshKey = 0, onChanged }: { refreshKey?: number; onChanged?: () => void }) {
  const { data, error, loading, reload } = useApi<Budget>("/api/budget");
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<BudgetItem | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (refreshKey) void reload(); }, [refreshKey, reload]);

  async function cancel() {
    if (!target) return; setBusy(true);
    try { await api(`/api/proposals/${target.proposal_id}/cancel`, { method: "POST" }); toast("ok", "Proposal cancelled. Its budget is free again."); setTarget(null); await reload(); onChanged?.(); }
    catch (e) { toast("err", e instanceof ApiError ? e.message : "Could not cancel"); setTarget(null); } finally { setBusy(false); }
  }

  if (loading && !data) return <Skeleton className="h-16 w-full" />;
  if (error || !data) return <ErrorState message={error ?? "Budget unavailable"} onRetry={reload} />;
  if (!data.policy_active) return <Card className="p-4 text-sm text-warn">No active policy: every purchase is blocked until you activate one in Policy Builder.</Card>;
  const max = Number(data.max_budget), used = Number(data.committed), pct = Math.min(100, max > 0 ? (used / max) * 100 : 0);
  const unpaid = data.items.filter((i) => i.cancellable).length;

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-slate-300"><Wallet className="h-4 w-4 text-violet-400" />
          <span><b className="text-white">{formatMoney(data.remaining ?? 0, data.currency)}</b> budget remaining <span className="text-slate-500">· {formatMoney(used, data.currency)} of {formatMoney(max, data.currency)} committed</span></span>
          {unpaid > 0 && <Badge tone="amber">{unpaid} unpaid</Badge>}</div>
        <button className="flex items-center gap-1 text-xs text-violet-400 hover:underline" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide" : "What's using my budget?"}{open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}</button>
      </div>
      <div className="mt-2 h-1.5 rounded bg-navy-700" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}><div className={`h-1.5 rounded ${pct > 85 ? "bg-bad" : "bg-violet-500"}`} style={{ width: `${pct}%` }} /></div>
      {open && (
        <div className="mt-3 space-y-2">
          {data.items.length === 0 ? <p className="text-sm text-slate-500">Nothing is counted against your budget.</p> : data.items.map((i) => (
            <div key={i.proposal_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-navy-900 p-3 text-sm">
              <div><p className="text-slate-200">{i.product_name} <span className="text-slate-500">· {formatMoney(i.amount, i.currency)}</span></p>
                <p className="flex items-center gap-2 text-xs text-slate-500"><StatusBadge value={i.state} />{i.state === "CAPTURED" ? "paid (counts permanently)" : i.authorization_expires_at ? `unpaid · authorization ${timeLeft(i.authorization_expires_at).toLowerCase()}` : "unpaid"}</p></div>
              {i.cancellable && <Button variant="danger" onClick={() => setTarget(i)}>Cancel</Button>}
            </div>))}
          <p className="text-xs text-slate-500">Unpaid authorizations stop counting when they expire. Paid purchases count toward the total budget.</p>
        </div>)}
      <ConfirmDialog open={!!target} danger busy={busy} title="Cancel this proposal?" confirmLabel="Cancel proposal" onConfirm={cancel} onClose={() => setTarget(null)}
        body={target && <>This releases <b>{formatMoney(target.amount, target.currency)}</b> held for <b>{target.product_name}</b>. It can no longer be paid, even if a PayPal order exists.</>} />
    </Card>
  );
}
