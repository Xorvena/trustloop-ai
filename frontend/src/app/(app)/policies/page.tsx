"use client";
import { Sparkles } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, EmptyState, ErrorState, Input, PageHeader, SkeletonRows, Textarea, useToast } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/lib/api";
import { formatMoney } from "@/lib/utils";
import type { Policy, PolicyDraft } from "@/types";

const EXAMPLE = "Never spend above ₹75,000. Ask me before any purchase above ₹25,000. Only buy from approved merchants. Never purchase the same product twice.";

export default function Policies() {
  const { data, error, loading, reload } = useApi<Policy[]>("/api/policies");
  const merchants = useApi<{ approved_merchants: string[] }>("/api/merchants");
  const toast = useToast();
  const [text, setText] = useState(EXAMPLE);
  const [draft, setDraft] = useState<PolicyDraft | null>(null);
  const [merchantText, setMerchantText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [saving, setSaving] = useState(false);

  async function parse() {
    setParsing(true); setDraft(null);
    try {
      const r = await api<{ draft: PolicyDraft }>("/api/policies/parse", { method: "POST", body: { text } });
      setDraft(r.draft); setMerchantText((merchants.data?.approved_merchants ?? r.draft.approved_merchants).join(", "));
    } catch (e) { toast("err", e instanceof ApiError ? e.message : "Parse failed"); } finally { setParsing(false); }
  }
  async function save() {
    if (!draft) return; setSaving(true);
    try {
      await api("/api/policies", { method: "POST", body: { raw_text: text, ...draft, name: "My policy", approved_merchants: merchantText.split(",").map((s) => s.trim()).filter(Boolean) } });
      toast("ok", "Policy saved and activated"); setDraft(null); reload(); merchants.reload();
    } catch (e) { toast("err", e instanceof ApiError ? e.message : "Save failed"); } finally { setSaving(false); }
  }
  async function toggle(p: Policy) {
    try { await api(`/api/policies/${p.id}`, { method: "PATCH", body: { is_active: !p.is_active } }); toast("ok", p.is_active ? "Policy deactivated: agents are blocked until a policy is active." : "Policy activated"); reload(); }
    catch (e) { toast("err", e instanceof ApiError ? e.message : "Failed"); }
  }

  return (
    <>
      <PageHeader title="Policy Builder" subtitle="Describe your rules in plain language. AI proposes; you confirm; the backend enforces." />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="p-5">
          <Textarea label="Your spending rules" rows={6} value={text} onChange={(e) => setText(e.target.value)} />
          <Button className="mt-3" onClick={parse} disabled={parsing || text.trim().length < 3}><Sparkles className="h-4 w-4" />{parsing ? "Interpreting…" : "Interpret policy"}</Button>
          <p className="mt-3 text-xs text-slate-500">Interpretation is a draft only. Nothing changes until you confirm, and AI can never edit a saved policy.</p>
        </Card>
        <Card className="p-5">
          <h2 className="mb-3 font-medium text-white">Interpreted policy</h2>
          {parsing ? <SkeletonRows n={4} /> : !draft ? <EmptyState title="Nothing to review yet" hint="Interpret your rules to preview the structured policy here." /> : (
            <div className="space-y-3 text-sm">
              <Badge tone={draft.source === "gemini" ? "violet" : "amber"}>{draft.source === "gemini" ? "Interpreted by Gemini" : "Basic parser (Gemini not configured)"}</Badge>
              <dl className="grid grid-cols-2 gap-3"><div><dt className="text-xs text-slate-500">Maximum budget</dt><dd className="text-white">{formatMoney(draft.max_budget, draft.currency)}</dd></div>
                <div><dt className="text-xs text-slate-500">Approval threshold</dt><dd className="text-white">{formatMoney(draft.approval_threshold, draft.currency)}</dd></div>
                <div><dt className="text-xs text-slate-500">Approved merchants only</dt><dd className="text-white">{draft.approved_merchants_only ? "Yes" : "No"}</dd></div>
                <div><dt className="text-xs text-slate-500">Block duplicate purchases</dt><dd className="text-white">{draft.duplicate_purchase_check ? "Yes" : "No"}</dd></div></dl>
              <Input label="Approved merchants (comma separated, replaces your current list)" value={merchantText} onChange={(e) => setMerchantText(e.target.value)} />
              <div className="flex gap-2"><Button variant="success" onClick={save} disabled={saving}>{saving ? "Saving…" : "Confirm and save"}</Button><Button variant="ghost" onClick={() => setDraft(null)}>Discard</Button></div>
            </div>)}
        </Card>
      </div>
      <h2 className="mb-3 mt-8 font-medium text-white">Saved policies</h2>
      {loading && !data ? <SkeletonRows n={2} /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.length ? <Card><EmptyState title="No policy saved" hint="Without an active policy every purchase is blocked (fail closed)." /></Card> : (
        <div className="space-y-3">{data.map((p) => (
          <Card key={p.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div><p className="text-sm text-white">Budget {formatMoney(p.max_budget, p.currency)} · approval above {formatMoney(p.approval_threshold, p.currency)}</p>
              <p className="text-xs text-slate-500">{p.approved_merchants_only ? "Approved merchants only" : "Any merchant"} · {p.duplicate_purchase_check ? "duplicates blocked" : "duplicates allowed"} · approvals expire after {p.approval_ttl_minutes} min</p></div>
            <div className="flex items-center gap-2"><Badge tone={p.is_active ? "green" : "slate"}>{p.is_active ? "Active" : "Inactive"}</Badge><Button variant="outline" onClick={() => toggle(p)}>{p.is_active ? "Deactivate" : "Activate"}</Button></div>
          </Card>))}
          <p className="text-xs text-slate-500">Approved merchants: {merchants.data?.approved_merchants.join(", ") || "none"}</p></div>)}
    </>
  );
}
