"use client";
import { Bot, ClipboardCheck, ShieldAlert, ShieldCheck, Wallet } from "lucide-react";
import Link from "next/link";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, Card, EmptyState, ErrorState, PageHeader, Skeleton, SkeletonRows, StatusBadge, useToast } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/utils";
import type { Overview } from "@/types";

interface Spending { daily: { date: string; spend: number; approved: number; blocked: number; pending: number; risk_avg: number }[] }

function Stat({ label, value, icon: Icon, tone }: { label: string; value: string | number; icon: typeof Wallet; tone?: string }) {
  return <Card className="p-5"><div className="flex items-center justify-between"><p className="text-sm text-slate-400">{label}</p><Icon className={`h-4 w-4 ${tone ?? "text-violet-400"}`} /></div><p className="mt-2 text-2xl font-semibold text-white">{value}</p></Card>;
}

export default function Dashboard() {
  const { data, error, loading, reload } = useApi<Overview>("/api/analytics/overview");
  const sp = useApi<Spending>("/api/analytics/spending");
  const toast = useToast();

  async function seed() {
    try { const r = await api<{ seeded: boolean; detail?: string }>("/api/demo/seed", { method: "POST" }); toast("ok", r.seeded ? "Demo agents, merchants and policy created." : r.detail ?? "Skipped"); reload(); }
    catch (e) { toast("err", e instanceof ApiError ? e.message : "Failed"); }
  }

  if (loading && !data) return <div className="space-y-4"><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24" />)}</div><SkeletonRows /></div>;
  if (error || !data) return <ErrorState message={error ?? "No data"} onRetry={reload} />;
  const spend = Object.entries(data.total_spending).map(([c, v]) => formatMoney(v, c)).join(" + ") || formatMoney(0);

  return (
    <>
      <PageHeader title="Command Center" subtitle="Live data from your TRUSTLOOP backend. Nothing on this screen is demo data." actions={data.total_agents === 0 ? <Button onClick={seed}>Create demo setup</Button> : undefined} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Stat label="Total spending" value={spend} icon={Wallet} />
        <Stat label="Approved" value={data.approved_transactions} icon={ShieldCheck} tone="text-ok" />
        <Stat label="Blocked" value={data.blocked_transactions} icon={ShieldAlert} tone="text-bad" />
        <Stat label="Pending approvals" value={data.pending_approvals} icon={ClipboardCheck} tone="text-warn" />
        <Stat label="Active agents" value={`${data.active_agents}/${data.total_agents}`} icon={Bot} />
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="p-5 xl:col-span-2">
          <h2 className="mb-3 font-medium text-white">Captured spending by day</h2>
          {sp.loading ? <Skeleton className="h-56" /> : !sp.data?.daily.length ? <EmptyState title="No activity yet" hint="Spending appears here after a PayPal capture." /> : (
            <ResponsiveContainer width="100%" height={220}><AreaChart data={sp.data.daily}><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.5} /><stop offset="100%" stopColor="#8b5cf6" stopOpacity={0} /></linearGradient></defs>
              <CartesianGrid stroke="#1d2750" vertical={false} /><XAxis dataKey="date" stroke="#64748b" fontSize={12} /><YAxis stroke="#64748b" fontSize={12} /><Tooltip contentStyle={{ background: "#0f1630", border: "1px solid #2a3563", borderRadius: 8 }} />
              <Area dataKey="spend" stroke="#8b5cf6" fill="url(#g)" /></AreaChart></ResponsiveContainer>)}
        </Card>
        <Card className="p-5">
          <h2 className="mb-3 font-medium text-white">Agent trust scores</h2>
          {!data.agent_trust.length ? <EmptyState title="No agents" /> : <ul className="space-y-3">{data.agent_trust.map((a) => (
            <li key={a.agent_id}><div className="flex justify-between text-sm"><span className="text-slate-300">{a.agent_name}</span><span className="text-white">{a.score}</span></div><div className="mt-1 h-1.5 rounded bg-navy-700"><div className="h-1.5 rounded bg-violet-500" style={{ width: `${a.score}%` }} /></div></li>))}</ul>}
        </Card>
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="overflow-x-auto p-5 xl:col-span-2">
          <div className="mb-3 flex justify-between"><h2 className="font-medium text-white">Recent transactions</h2><Link href="/transactions" className="text-sm text-violet-400">View all</Link></div>
          {!data.recent_transactions.length ? <EmptyState title="No transactions yet" hint="Ask the AI shopping assistant for a product to start." action={<Link href="/shop"><Button>Open AI Shopping</Button></Link>} /> : (
            <table className="w-full text-left text-sm"><thead className="text-xs text-slate-500"><tr><th className="pb-2">Product</th><th>Agent</th><th>Amount</th><th>Decision</th><th>State</th></tr></thead>
              <tbody className="divide-y divide-navy-700">{data.recent_transactions.map((t) => <tr key={t.id}><td className="py-2 text-slate-200">{t.product_name}<div className="text-xs text-slate-500">{t.merchant}</div></td><td className="text-slate-400">{t.agent_name}</td><td>{formatMoney(t.amount, t.currency)}</td><td><StatusBadge value={t.decision} /></td><td><StatusBadge value={t.state} /></td></tr>)}</tbody></table>)}
        </Card>
        <div className="space-y-4">
          <Card className="p-5"><h2 className="mb-3 font-medium text-white">Risk alerts</h2>
            {!data.risk_alerts.length ? <p className="text-sm text-slate-500">No high-risk proposals.</p> : <ul className="space-y-2">{data.risk_alerts.map((a) => <li key={a.proposal_id} className="rounded-lg border border-red-500/20 bg-red-500/5 p-2 text-sm"><div className="flex justify-between"><span className="text-slate-200">{a.product_name}</span><Badge tone="red">{a.level} · {a.score}</Badge></div><p className="text-xs text-slate-500">{a.signals.join(", ")}</p></li>)}</ul>}</Card>
          <Card className="p-5"><h2 className="mb-3 font-medium text-white">Agent activity</h2>
            {!data.activity.length ? <p className="text-sm text-slate-500">No events yet.</p> : <ul className="space-y-2">{data.activity.slice(0, 8).map((a) => <li key={a.id} className="text-xs"><span className="font-mono text-violet-400">{a.action}</span><span className="text-slate-500"> · {a.actor} · {formatDate(a.timestamp)}</span></li>)}</ul>}</Card>
        </div>
      </div>
      <Card className="mt-4 p-5"><h2 className="mb-3 font-medium text-white">Decisions per day</h2>
        {!sp.data?.daily.length ? <p className="text-sm text-slate-500">No data.</p> : <ResponsiveContainer width="100%" height={180}><BarChart data={sp.data.daily}><CartesianGrid stroke="#1d2750" vertical={false} /><XAxis dataKey="date" stroke="#64748b" fontSize={12} /><YAxis stroke="#64748b" fontSize={12} allowDecimals={false} /><Tooltip contentStyle={{ background: "#0f1630", border: "1px solid #2a3563", borderRadius: 8 }} />
          <Bar dataKey="approved" fill="#34d399" stackId="a" /><Bar dataKey="pending" fill="#fbbf24" stackId="a" /><Bar dataKey="blocked" fill="#f87171" stackId="a" /></BarChart></ResponsiveContainer>}</Card>
    </>
  );
}
