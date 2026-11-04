"use client";
import { Laptop, Send, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { PolicyChecks, RiskSummary } from "@/components/shared/Checks";
import { PayPalCheckout } from "@/components/shopping/PayPalCheckout";
import { Badge, Button, Card, EmptyState, ErrorState, Modal, PageHeader, SkeletonRows, StatusBadge, useToast } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/lib/api";
import { formatMoney } from "@/lib/utils";
import type { Agent, Proposal, SearchResponse, SearchResult } from "@/types";
import Link from "next/link";

const EXAMPLE = "Find a laptop for software development. My maximum budget is ₹75,000. I need 16GB RAM, 512GB SSD and good battery life.";

export default function Shop() {
  const agents = useApi<Agent[]>("/api/agents");
  const toast = useToast();
  const [q, setQ] = useState(EXAMPLE);
  const [agentId, setAgentId] = useState("");
  const [res, setRes] = useState<SearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [proposing, setProposing] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

  const active = (agents.data ?? []).filter((a) => a.status !== "revoked");
  const chosen = agentId || active.find((a) => a.status === "active")?.agent_id || active[0]?.agent_id || "";

  async function search() {
    setSearching(true); setErr(null); setRes(null);
    try { setRes(await api<SearchResponse>("/api/products/search", { method: "POST", body: { query: q } })); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Search failed"); } finally { setSearching(false); }
  }
  async function propose(r: SearchResult) {
    if (!chosen) { toast("err", "Create an agent first."); return; }
    setProposing(r.product.id);
    try {
      setProposal(await api<Proposal>("/api/proposals", { method: "POST", body: { agent_id: chosen, product_id: r.product.id, request_text: q, rationale: res?.summary ?? "" } }));
    } catch (e) { toast("err", e instanceof ApiError ? e.message : "Proposal failed"); } finally { setProposing(null); }
  }
  async function reloadProposal() {
    if (proposal) setProposal(await api<Proposal>(`/api/proposals/${proposal.id}`));
    setRefresh((n) => n + 1);
  }

  return (
    <>
      <PageHeader title="AI Shopping Assistant" subtitle="The agent researches and proposes. Only the backend can authorize and pay." />
      <Card className="p-5">
        <label className="text-sm text-slate-400" htmlFor="req">What should the agent find?</label>
        <textarea id="req" rows={3} value={q} onChange={(e) => setQ(e.target.value)} className="mt-1 w-full rounded-lg border border-navy-600 bg-navy-900 p-3 text-sm" />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <select aria-label="Agent" value={chosen} onChange={(e) => setAgentId(e.target.value)} className="rounded-lg border border-navy-600 bg-navy-900 px-3 py-2 text-sm">
            {active.length === 0 && <option value="">No agents</option>}
            {active.map((a) => <option key={a.id} value={a.agent_id}>{a.agent_name} ({a.status})</option>)}
          </select>
          <Button onClick={search} disabled={searching || q.trim().length < 2}><Send className="h-4 w-4" />{searching ? "Researching…" : "Search catalog"}</Button>
          {active.length === 0 && !agents.loading && <Link href="/agents" className="text-sm text-violet-400">Create an agent →</Link>}
        </div>
      </Card>
      {err && <div className="mt-4"><ErrorState message={err} /></div>}
      {searching && <div className="mt-4"><SkeletonRows n={3} /></div>}
      {res && (
        <div className="mt-4 space-y-4">
          <Card className="p-5"><div className="mb-1 flex gap-2"><Badge tone={res.explanation_source === "gemini" ? "violet" : "slate"}>{res.explanation_source === "gemini" ? "Gemini summary" : "Template summary"}</Badge><Badge tone="amber">Demo catalog</Badge></div>
            <p className="text-sm text-slate-200">{res.summary}</p><p className="mt-1 text-xs text-slate-500">{res.catalog_notice}</p></Card>
          {!res.results.length ? <Card><EmptyState title="No matching products" hint="Try a different description." /></Card> : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{res.results.map((r, i) => (
              <Card key={r.product.id} className="flex flex-col p-5">
                <div className="mb-3 grid h-24 place-items-center rounded-xl bg-gradient-to-br from-navy-700 to-navy-800"><Laptop className="h-8 w-8 text-violet-400" /></div>
                <div className="flex items-start justify-between gap-2"><p className="font-medium text-white">{r.product.name}</p>{i === 0 && r.meets_requirements && <Badge tone="green">Top pick</Badge>}</div>
                <p className="text-xs text-slate-500">{r.product.merchant} · {r.product.sku}</p>
                <p className="mt-2 text-lg font-semibold text-white">{formatMoney(r.product.price, r.product.currency)}</p>
                <dl className="mt-2 grid grid-cols-2 gap-1 text-xs text-slate-400">{Object.entries(r.product.specs).slice(0, 4).map(([k, v]) => <div key={k}><dt className="text-slate-600">{k.replaceAll("_", " ")}</dt><dd>{String(v)}</dd></div>)}</dl>
                {!r.meets_requirements && <p className="mt-2 text-xs text-warn">Unmet: {r.unmet.join(", ")}</p>}
                {r.suspicious_description && <p className="mt-2 flex items-start gap-1 text-xs text-bad"><ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />Description contains instruction-like text and is treated as untrusted data.</p>}
                <Button className="mt-auto" variant="outline" disabled={proposing === r.product.id} onClick={() => propose(r)}>{proposing === r.product.id ? "Submitting…" : "Create purchase proposal"}</Button>
              </Card>))}</div>)}
        </div>)}
      <Modal open={!!proposal} onClose={() => setProposal(null)} title="Proposal evaluation">
        {proposal && (
          <div className="space-y-3 text-sm" key={refresh}>
            <div className="flex items-center justify-between"><p className="text-white">{proposal.product_name} · {formatMoney(proposal.amount, proposal.currency)}</p><StatusBadge value={proposal.decision} /></div>
            <p className="text-slate-400">{proposal.decision_explanation.summary}</p>
            <PolicyChecks checks={proposal.decision_explanation.checks} />
            <RiskSummary risk={proposal.risk} />
            <div className="flex items-center gap-2"><span className="text-slate-500">State:</span><StatusBadge value={proposal.state} /></div>
            {proposal.state === "PENDING_APPROVAL" && <Link href="/approvals"><Button>Go to Approval Center</Button></Link>}
            {(proposal.state === "AUTHORIZED" || proposal.state === "PAYPAL_ORDER_CREATED") && <PayPalCheckout proposalId={proposal.id} onDone={reloadProposal} />}
            {proposal.state === "CAPTURED" && <p className="rounded-lg bg-emerald-500/10 p-3 text-ok">Payment captured and verified. See Transactions for the receipt.</p>}
            {proposal.state === "BLOCKED" && <p className="rounded-lg bg-red-500/10 p-3 text-bad">Blocked by policy. No payment can be made for this proposal.</p>}
          </div>)}
      </Modal>
    </>
  );
}
