"use client";
import { useState } from "react";
import { Card, EmptyState, ErrorState, PageHeader, SkeletonRows } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDate } from "@/lib/utils";
import type { AuditEntry } from "@/types";

export default function Audit() {
  const [action, setAction] = useState("");
  const { data, error, loading, reload } = useApi<AuditEntry[]>(`/api/audit-logs?limit=200${action ? `&action=${encodeURIComponent(action)}` : ""}`);
  return (
    <>
      <PageHeader title="Audit Log" subtitle="Append-only at the application layer (no update/delete API or ORM path). Not cryptographically tamper-proof." />
      <Card className="mb-4 p-4"><label className="text-sm text-slate-400">Filter by event prefix <select className="ml-2 rounded-lg border border-navy-600 bg-navy-900 px-3 py-2 text-sm" value={action} onChange={(e) => setAction(e.target.value)}>
        <option value="">All events</option>{["agent", "policy", "proposal", "risk", "approval", "payment", "webhook", "transaction"].map((a) => <option key={a}>{a}</option>)}</select></label></Card>
      <Card className="p-2">
        {loading && !data ? <div className="p-3"><SkeletonRows /></div> : error ? <div className="p-3"><ErrorState message={error} onRetry={reload} /></div> : !data?.length ? <EmptyState title="No events" /> : (
          <ol className="divide-y divide-navy-700">{data.map((e) => (
            <li key={e.id} className="p-3"><div className="flex flex-wrap items-center gap-x-3 text-sm"><span className="font-mono text-violet-400">{e.action}</span><span className="text-slate-400">{e.actor}</span><span className="text-xs text-slate-500">{formatDate(e.timestamp)}</span>{e.proposal_id && <span className="font-mono text-xs text-slate-500">proposal {e.proposal_id.slice(0, 8)}</span>}</div>
              {Object.keys(e.details).length > 0 && <pre className="mt-1 overflow-x-auto text-xs text-slate-500">{JSON.stringify(e.details, null, 1)}</pre>}</li>))}</ol>)}
      </Card>
    </>
  );
}
