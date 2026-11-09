"use client";
import { Bot, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Input, Modal, PageHeader, Skeleton, StatusBadge, useToast } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/lib/api";
import { formatMoney } from "@/lib/utils";
import type { Agent } from "@/types";

export default function Agents() {
  const { data, error, loading, reload } = useApi<Agent[]>("/api/agents");
  const toast = useToast();
  const cats = useApi<{ categories: Record<string, string[]> }>("/api/products/categories");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ agent_name: "", description: "", max_transaction: "75000" });
  const [chosen, setChosen] = useState<string[]>(["electronics"]);
  const [confirm, setConfirm] = useState<{ agent: Agent; status: "inactive" | "revoked" } | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(e: React.FormEvent) {
    e.preventDefault(); setBusy(true);
    try {
      await api("/api/agents", { method: "POST", body: { ...form, allowed_categories: chosen } });
      toast("ok", "Agent created"); setCreating(false); reload();
    } catch (x) { toast("err", x instanceof ApiError ? x.message : "Failed"); } finally { setBusy(false); }
  }
  async function addDemoAgents() {
    try { const r = await api<{ created: string[] }>("/api/demo/agents", { method: "POST" }); toast("ok", r.created.length ? `Created: ${r.created.join(", ")}` : "All demo agents already exist."); reload(); }
    catch (x) { toast("err", x instanceof ApiError ? x.message : "Failed"); }
  }
  async function setStatus(a: Agent, status: string) {
    setBusy(true);
    try { await api(`/api/agents/${a.agent_id}`, { method: "PATCH", body: { status } }); toast("ok", `${a.agent_name} is now ${status}`); setConfirm(null); reload(); }
    catch (x) { toast("err", x instanceof ApiError ? x.message : "Failed"); } finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader title="AI Agents" subtitle="Each agent can only buy in the categories you grant. Create one with every category for general shopping. Permissions are enforced by the backend." actions={<div className="flex gap-2"><Button variant="outline" onClick={addDemoAgents}>Add demo agents</Button><Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" />New agent</Button></div>} />
      {loading && !data ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-52" />)}</div>
        : error ? <ErrorState message={error} onRetry={reload} />
        : !data?.length ? <Card><EmptyState title="No agents yet" hint="Create an agent and give it limited spending permissions." action={<Button onClick={() => setCreating(true)}>Create agent</Button>} /></Card>
        : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.map((a) => (
          <Card key={a.id} className="p-5">
            <div className="flex items-start justify-between"><div className="flex items-center gap-3"><div className="grid h-10 w-10 place-items-center rounded-md bg-navy-800"><Bot className="h-5 w-5 text-slate-300" /></div>
              <div><p className="font-medium text-strong">{a.agent_name}</p><p className="font-mono text-xs text-slate-500">{a.agent_id}</p></div></div><StatusBadge value={a.status} /></div>
            <p className="mt-3 min-h-[2.5rem] text-sm text-slate-400">{a.description || "No description."}</p>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-sm"><div><dt className="text-xs text-slate-500">Max per transaction</dt><dd className="text-slate-200">{formatMoney(a.max_transaction, a.currency)}</dd></div>
              <div><dt className="text-xs text-slate-500">Trust score</dt><dd className="text-slate-200">{a.trust_score ?? "—"}/100</dd></div></dl>
            <div className="mt-3 flex flex-wrap gap-1">{a.allowed_categories.length ? a.allowed_categories.map((c) => <Badge key={c} tone="violet">{c}</Badge>) : <Badge tone="red">no categories (all blocked)</Badge>}</div>
            <div className="mt-4 flex flex-wrap gap-2">
              {a.status === "active" && <Button variant="outline" onClick={() => setConfirm({ agent: a, status: "inactive" })}>Deactivate</Button>}
              {a.status === "inactive" && <Button variant="success" onClick={() => setStatus(a, "active")}>Activate</Button>}
              {a.status !== "revoked" && <Button variant="danger" onClick={() => setConfirm({ agent: a, status: "revoked" })}>Revoke</Button>}
              <Link href="/trust"><Button variant="ghost">Trust details</Button></Link>
            </div>
          </Card>))}</div>}
      <Modal open={creating} onClose={() => setCreating(false)} title="Create AI agent">
        <form onSubmit={create} className="space-y-3">
          <Input label="Agent name" required value={form.agent_name} onChange={(e) => setForm({ ...form, agent_name: e.target.value })} placeholder="LaptopShoppingAgent" />
          <Input label="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <Input label="Max transaction (INR)" type="number" min="1" step="0.01" required value={form.max_transaction} onChange={(e) => setForm({ ...form, max_transaction: e.target.value })} />
          <fieldset>
            <legend className="mb-1 flex items-center justify-between text-sm text-slate-400"><span>Allowed categories</span>
              <span className="flex gap-3 text-xs"><button type="button" className="text-violet-400 hover:underline" onClick={() => setChosen(Object.keys(cats.data?.categories ?? {}))}>Select all</button><button type="button" className="text-slate-500 hover:underline" onClick={() => setChosen([])}>Clear</button></span></legend>
            <div className="flex flex-wrap gap-1.5">{Object.entries(cats.data?.categories ?? {}).map(([c, types]) => {
              const on = chosen.includes(c);
              return <button key={c} type="button" aria-pressed={on} title={types.join(", ")} onClick={() => setChosen(on ? chosen.filter((x) => x !== c) : [...chosen, c])}
                className={`rounded-full border px-3 py-1 text-xs ${on ? "border-strong bg-navy-800 text-strong" : "border-navy-600 text-slate-400 hover:bg-navy-700"}`}>{c}</button>;
            })}</div>
            {chosen.length === 0 && <p className="mt-1 text-xs text-warn">With no categories the agent can't buy anything.</p>}
          </fieldset>
          <p className="text-xs text-slate-500">A unique agent ID is generated by the server.</p>
          <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={() => setCreating(false)}>Cancel</Button><Button type="submit" disabled={busy}>{busy ? "Creating…" : "Create"}</Button></div>
        </form>
      </Modal>
      <ConfirmDialog open={!!confirm} danger title={confirm?.status === "revoked" ? "Revoke agent?" : "Deactivate agent?"} confirmLabel={confirm?.status === "revoked" ? "Revoke permanently" : "Deactivate"} busy={busy}
        body={confirm?.status === "revoked" ? "A revoked agent can never spend again and cannot be reactivated." : "Any pending or authorized purchase by this agent will be blocked on revalidation."}
        onConfirm={() => confirm && setStatus(confirm.agent, confirm.status)} onClose={() => setConfirm(null)} />
    </>
  );
} 