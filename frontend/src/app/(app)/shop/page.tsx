"use client";
import { Send } from "lucide-react";
import { useState } from "react";
import { PolicyChecks, RiskSummary } from "@/components/shared/Checks";
import { PayPalCheckout } from "@/components/shopping/PayPalCheckout";
import { BudgetPanel } from "@/components/shopping/BudgetPanel";
import { ProductCard } from "@/components/shopping/ProductCard";
import { SearchSummary } from "@/components/shopping/SearchSummary";
import { Button, Card, EmptyState, ErrorState, Modal, PageHeader, SkeletonRows, StatusBadge, useToast } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/lib/api";
import { formatMoney } from "@/lib/utils";
import type { Agent, Proposal, SearchResponse, SearchResult } from "@/types";
import Link from "next/link";

const EXAMPLE = "Find a laptop for software development. My maximum budget is ₹75,000. I need 16GB RAM, 512GB SSD and good battery life.";
const IDEAS = ["perfume under ₹5000", "running shoes for men size 9", "Atomic Habits by James Clear", "iPhone 15", "mens watch", "office chair under ₹20000"];

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
  async function propose(r: SearchResult) {  // proposals go through the same policy engine for matches and alternatives
    if (!chosen) { toast("err", "Create an agent first."); return; }
    setProposing(r.product.id);
    try {
      setProposal(await api<Proposal>("/api/proposals", { method: "POST", body: { agent_id: chosen, product_id: r.product.id, request_text: q, rationale: res ? `${res.summary_source === "gemini" ? "Gemini" : "Template"} summary: ${res.summary}` : "" } }));
      setRefresh((n) => n + 1);
    } catch (e) { toast("err", e instanceof ApiError ? e.message : "Proposal failed"); } finally { setProposing(null); }
  }
  async function approveMerchant(merchant: string) {
    try {
      await api("/api/merchants", { method: "POST", body: { name: merchant } });
      setRes((cur) => cur && { ...cur, matches: cur.matches.map((r) => r.product.merchant === merchant ? { ...r, merchant_approved: true } : r), alternatives: cur.alternatives.map((r) => r.product.merchant === merchant ? { ...r, merchant_approved: true } : r) });
      toast("ok", `${merchant} added to your approved merchants.`);
    } catch (e) { toast("err", e instanceof ApiError ? e.message : "Could not add merchant"); }
  }
  async function reloadProposal() {
    if (proposal) setProposal(await api<Proposal>(`/api/proposals/${proposal.id}`));
    setRefresh((n) => n + 1);
  }

  return (
    <>
      <PageHeader title="AI Shopping Assistant" subtitle="The agent researches and proposes. Only the backend can authorize and pay." />
      <div className="mb-4"><BudgetPanel refreshKey={refresh} onChanged={() => setRefresh((n) => n + 1)} /></div>
      <Card className="p-5">
        <label className="text-sm text-slate-400" htmlFor="req">What should the agent find?</label>
        <textarea id="req" rows={3} value={q} onChange={(e) => setQ(e.target.value)} className="mt-1 w-full rounded-lg border border-navy-600 bg-navy-900 p-3 text-sm" />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <select aria-label="Agent" value={chosen} onChange={(e) => setAgentId(e.target.value)} className="rounded-lg border border-navy-600 bg-navy-900 px-3 py-2 text-sm">
            {active.length === 0 && <option value="">No agents</option>}
            {active.map((a) => <option key={a.id} value={a.agent_id}>{a.agent_name} ({a.status})</option>)}
          </select>
          <Button onClick={search} disabled={searching || q.trim().length < 2}><Send className="h-4 w-4" />{searching ? "Researching…" : "Search catalog"}</Button>
          <div className="flex flex-wrap gap-1.5">{IDEAS.map((i) => <button key={i} type="button" onClick={() => setQ(i)} className="rounded-full border border-navy-600 px-2.5 py-1 text-xs text-slate-400 hover:bg-navy-700">{i}</button>)}</div>
          {active.length === 0 && !agents.loading && <Link href="/agents" className="text-sm text-violet-400">Create an agent →</Link>}
        </div>
      </Card>
      {err && <div className="mt-4"><ErrorState message={err} /></div>}
      {searching && <div className="mt-4"><SkeletonRows n={3} /></div>}
      {res && (
        <div className="mt-4 space-y-5">
          <SearchSummary res={res} />
          {res.matches.length > 0 && (
            <section aria-label="Matches">
              <h2 className="mb-3 font-medium text-white">Matches <span className="text-sm font-normal text-slate-500">· satisfy every requirement checked</span></h2>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{res.matches.map((r, i) => <ProductCard key={r.product.id} r={r} top={i === 0} busy={proposing === r.product.id} onPropose={() => propose(r)} onApproveMerchant={approveMerchant} />)}</div>
            </section>)}
          {res.alternatives.length > 0 && (
            <section aria-label="Alternatives">
              <h2 className="mb-1 font-medium text-white">{res.matches.length ? "Other options" : "Closest alternatives"}</h2>
              <p className="mb-3 text-sm text-slate-400">These do <b>not</b> satisfy everything you asked for. What each one misses is listed on its card.</p>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{res.alternatives.map((r) => <ProductCard key={r.product.id} r={r} busy={proposing === r.product.id} onPropose={() => propose(r)} onApproveMerchant={approveMerchant} />)}</div>
            </section>)}
          {!res.matches.length && !res.alternatives.length && <Card><EmptyState title="Nothing in the catalog matches" hint="Try a product type (laptop, phone, shoes, book), a brand, or a model that exists in the demo catalog." /></Card>}
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
            {proposal.state === "BLOCKED" && proposal.decision_explanation.checks?.some((c) => c.rule === "budget_remaining" && !c.passed) && (
              <p className="rounded-lg bg-amber-500/10 p-3 text-xs text-slate-300">Part of your budget may be reserved by approved-but-unpaid proposals. Close this and open <b>What&apos;s using my budget?</b> to cancel any you no longer want, then try again.</p>)}
          </div>)}
      </Modal>
    </>
  );
}
