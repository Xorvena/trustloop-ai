"use client";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, EmptyState, ErrorState, PageHeader, SkeletonRows } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDate } from "@/lib/utils";
import type { Agent, TrustDetail } from "@/types";

function Detail({ id }: { id: string }) {
  const { data, error, loading, reload } = useApi<TrustDetail>(`/api/agents/${id}/trust`);
  if (loading && !data) return <SkeletonRows />;
  if (error || !data) return <ErrorState message={error ?? "No data"} onRetry={reload} />;
  const chart = data.history.map((h) => ({ t: formatDate(h.created_at), score: h.score }));
  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <Card className="p-6 text-center"><p className="text-sm text-slate-400">Agent Trust Score</p><p className="my-2 text-6xl font-semibold text-strong">{data.score}</p><p className="text-xs text-slate-500">out of 100 · {data.history.length} snapshots</p>
        <p className="mt-4 rounded-md bg-navy-800 p-3 text-xs text-slate-300">{data.note}</p></Card>
      <Card className="p-5 xl:col-span-2"><h2 className="mb-3 font-medium text-strong">Components</h2><ul className="space-y-4">{Object.entries(data.components).map(([k, c]) => (
        <li key={k}><div className="flex justify-between text-sm"><span className="capitalize text-slate-200">{k.replaceAll("_", " ")} <span className="text-slate-500">({c.weight}%)</span></span><span className="text-strong">{c.points}/{c.weight}</span></div>
          <div className="mt-1 h-1.5 rounded bg-navy-700"><div className="h-1.5 rounded bg-slate-300" style={{ width: `${(c.points / c.weight) * 100}%` }} /></div>
          <p className="mt-1 text-xs text-slate-500">{c.description}. {c.good}/{c.observations} clean observations; new agents start from a neutral prior.</p></li>))}</ul></Card>
      <Card className="p-5 xl:col-span-2"><h2 className="mb-3 font-medium text-strong">Score timeline</h2>
        {chart.length < 2 ? <p className="text-sm text-slate-500">Timeline appears after more agent activity.</p> : <ResponsiveContainer width="100%" height={200}><LineChart data={chart}><CartesianGrid stroke="rgb(var(--navy-700))" vertical={false} /><XAxis dataKey="t" hide /><YAxis domain={[0, 100]} stroke="rgb(var(--slate-500))" fontSize={12} /><Tooltip contentStyle={{ background: "rgb(var(--navy-850))", border: "1px solid rgb(var(--navy-600))", borderRadius: 6, color: "rgb(var(--slate-200))" }} /><Line dataKey="score" stroke="rgb(var(--slate-300))" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer>}</Card>
      <Card className="p-5"><h2 className="mb-3 font-medium text-strong">Why it changed</h2><ul className="max-h-64 space-y-2 overflow-y-auto text-xs text-slate-400">{[...data.history].reverse().map((h, i) => <li key={i}>{h.reason}</li>)}</ul></Card>
    </div>
  );
}

export default function Trust() {
  const agents = useApi<Agent[]>("/api/agents");
  const [sel, setSel] = useState("");
  const list = agents.data ?? [];
  const id = sel || list[0]?.agent_id || "";
  return (
    <>
      <PageHeader title="Agent Trust Center" subtitle="Computed from measurable history. It never loosens limits, permissions or approvals." />
      {agents.loading && !agents.data ? <SkeletonRows n={2} /> : agents.error ? <ErrorState message={agents.error} onRetry={agents.reload} /> : !list.length ? <Card><EmptyState title="No agents" /></Card> : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">{list.map((a) => <button key={a.id} onClick={() => setSel(a.agent_id)} aria-pressed={a.agent_id === id} className={`rounded-lg border px-3 py-1.5 text-sm ${a.agent_id === id ? "border-strong bg-navy-800 text-strong" : "border-navy-600 text-slate-400 hover:bg-navy-800"}`}>{a.agent_name}</button>)}</div>
          <Detail id={id} key={id} />
        </>)}
    </>
  );
} 