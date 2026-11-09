"use client";
import { AlertTriangle, Pencil, Sparkles } from "lucide-react";
import { useState } from "react";
import { SourceBadge } from "@/components/shopping/SearchSummary";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Modal, PageHeader, SkeletonRows, Textarea, useToast } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { api, ApiError } from "@/lib/api";
import { formatMoney } from "@/lib/utils";
import type { Policy, PolicyDraft, PolicyParseResponse } from "@/types";

const EXAMPLE = "Never spend above ₹75,000. Ask me before any purchase above ₹25,000. Only buy from approved merchants. Never purchase the same product twice.";

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return <label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" className="h-4 w-4 accent-violet-500" checked={checked} onChange={(e) => onChange(e.target.checked)} />{label}</label>;
}

interface Fields { max_budget: string; approval_threshold: string; approved_merchants_only: boolean; duplicate_purchase_check: boolean; auto_approve_enabled: boolean; approval_ttl_minutes: string; merchants: string }

function PolicyFields({ f, set }: { f: Fields; set: (f: Fields) => void }) {
  const bad = Number(f.approval_threshold) > Number(f.max_budget);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Input label="Maximum budget (₹)" type="number" min="1" step="0.01" value={f.max_budget} onChange={(e) => set({ ...f, max_budget: e.target.value })} />
        <Input label="Ask me above (₹)" type="number" min="0" step="0.01" value={f.approval_threshold} onChange={(e) => set({ ...f, approval_threshold: e.target.value })} />
      </div>
      {bad && <p role="alert" className="text-xs text-bad">The approval threshold cannot be higher than the maximum budget.</p>}
      <div className="space-y-2">
        <Toggle label="Only buy from approved merchants" checked={f.approved_merchants_only} onChange={(v) => set({ ...f, approved_merchants_only: v })} />
        <Toggle label="Block buying the same product twice" checked={f.duplicate_purchase_check} onChange={(v) => set({ ...f, duplicate_purchase_check: v })} />
        <Toggle label="Auto-approve purchases under the threshold" checked={f.auto_approve_enabled} onChange={(v) => set({ ...f, auto_approve_enabled: v })} />
      </div>
      <Input label="Approvals expire after (minutes)" type="number" min="1" max="1440" value={f.approval_ttl_minutes} onChange={(e) => set({ ...f, approval_ttl_minutes: e.target.value })} />
      <Input label="Approved merchants (comma separated; replaces your list)" value={f.merchants} onChange={(e) => set({ ...f, merchants: e.target.value })} />
    </div>
  );
}
const fieldsOf = (p: Policy, merchants: string[]): Fields => ({ max_budget: String(Number(p.max_budget)), approval_threshold: String(Number(p.approval_threshold)), approved_merchants_only: p.approved_merchants_only,
  duplicate_purchase_check: p.duplicate_purchase_check, auto_approve_enabled: p.auto_approve_enabled, approval_ttl_minutes: String(p.approval_ttl_minutes), merchants: merchants.join(", ") });
const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function Policies() {
  const { data, error, loading, reload } = useApi<Policy[]>("/api/policies");
  const merchants = useApi<{ approved_merchants: string[] }>("/api/merchants");
  const toast = useToast();
  const [text, setText] = useState(EXAMPLE);
  const [parsed, setParsed] = useState<PolicyParseResponse | null>(null);
  const [fields, setFields] = useState<Fields | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [parsing, setParsing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<{ p: Policy; f: Fields } | null>(null);

  async function parse() {
    setParsing(true); setParsed(null); setFields(null); setParseError(null);
    try {
      const r = await api<PolicyParseResponse>("/api/policies/parse", { method: "POST", body: { text } });
      const d: PolicyDraft = r.draft;
      setParsed(r);
      setFields({ max_budget: String(Number(d.max_budget)), approval_threshold: String(Number(d.approval_threshold)), approved_merchants_only: d.approved_merchants_only,
        duplicate_purchase_check: d.duplicate_purchase_check, auto_approve_enabled: true, approval_ttl_minutes: "30", merchants: (merchants.data?.approved_merchants ?? d.approved_merchants).join(", ") });
    } catch (e) { setParseError(e instanceof ApiError ? e.message : "Interpretation failed"); } finally { setParsing(false); }
  }
  async function save() {
    if (!fields || !parsed) return; setSaving(true);
    try {
      await api("/api/policies", { method: "POST", body: { raw_text: text, name: "My policy", currency: parsed.draft.currency, max_budget: fields.max_budget, approval_threshold: fields.approval_threshold,
        approved_merchants_only: fields.approved_merchants_only, duplicate_purchase_check: fields.duplicate_purchase_check, auto_approve_enabled: fields.auto_approve_enabled,
        approval_ttl_minutes: Number(fields.approval_ttl_minutes), approved_merchants: list(fields.merchants) } });
      toast("ok", "Policy saved and activated (the previous active policy was deactivated)."); setParsed(null); setFields(null); reload(); merchants.reload();
    } catch (e) { toast("err", e instanceof ApiError ? e.message : "Save failed"); } finally { setSaving(false); }
  }
  async function saveEdit() {
    if (!editing) return; setSaving(true);
    const { p, f } = editing;
    try {
      await api(`/api/policies/${p.id}`, { method: "PATCH", body: { max_budget: f.max_budget, approval_threshold: f.approval_threshold, approved_merchants_only: f.approved_merchants_only,
        duplicate_purchase_check: f.duplicate_purchase_check, auto_approve_enabled: f.auto_approve_enabled, approval_ttl_minutes: Number(f.approval_ttl_minutes), approved_merchants: list(f.merchants) } });
      toast("ok", "Policy updated."); setEditing(null); reload(); merchants.reload();
    } catch (e) { toast("err", e instanceof ApiError ? e.message : "Update failed"); } finally { setSaving(false); }
  }
  async function toggle(p: Policy) {
    try { await api(`/api/policies/${p.id}`, { method: "PATCH", body: { is_active: !p.is_active } }); toast("ok", p.is_active ? "Policy deactivated: agents are blocked until a policy is active." : "Policy activated"); reload(); }
    catch (e) { toast("err", e instanceof ApiError ? e.message : "Failed"); }
  }
  const invalid = fields ? Number(fields.approval_threshold) > Number(fields.max_budget) || !(Number(fields.max_budget) > 0) : true;

  return (
    <>
      <PageHeader title="Policy Builder" subtitle="Describe your rules in plain language, or edit the values directly. AI proposes; you confirm; the backend enforces." />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="p-5">
          <Textarea label="Your spending rules" rows={6} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button onClick={parse} disabled={parsing || text.trim().length < 3}><Sparkles className="h-4 w-4" />{parsing ? "Interpreting…" : "Interpret policy"}</Button>
          </div>
          {parseError && <div className="mt-3"><ErrorState message={parseError} /></div>}
          <p className="mt-3 text-xs text-slate-500">Interpretation is a draft only. Nothing changes until you confirm, and AI can never edit a saved policy.</p>
        </Card>
        <Card className="p-5">
          <h2 className="mb-3 font-medium text-strong">Interpreted policy <span className="text-sm font-normal text-slate-500">· editable before saving</span></h2>
          {parsing ? <SkeletonRows n={4} /> : !parsed || !fields ? <EmptyState title="Nothing to review yet" hint="Interpret your rules to preview the structured policy here." /> : (
            <div className="space-y-3">
              <SourceBadge source={parsed.source === "gemini" ? "gemini" : "heuristic"} model={parsed.model} reason={parsed.fallback_reason} fallbackModel={parsed.used_fallback_model} />
              {parsed.fallback_reason && parsed.fallback_reason !== "not_configured" && <p className="flex items-start gap-1 text-xs text-warn"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{parsed.fallback_message}</p>}
              <PolicyFields f={fields} set={setFields} />
              <p className="text-xs text-slate-500">Currency {parsed.draft.currency}. Check the values above: this is what will be enforced.</p>
              <div className="flex gap-2"><Button variant="success" onClick={save} disabled={saving || invalid}>{saving ? "Saving…" : "Confirm and save"}</Button><Button variant="ghost" onClick={() => { setParsed(null); setFields(null); }}>Discard</Button></div>
            </div>)}
        </Card>
      </div>
      <h2 className="mb-3 mt-8 font-medium text-strong">Saved policies</h2>
      {loading && !data ? <SkeletonRows n={2} /> : error ? <ErrorState message={error} onRetry={reload} /> : !data?.length ? <Card><EmptyState title="No policy saved" hint="Without an active policy every purchase is blocked (fail closed)." /></Card> : (
        <div className="space-y-3">{data.map((p) => (
          <Card key={p.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div><p className="text-sm text-strong">Budget {formatMoney(p.max_budget, p.currency)} · approval above {formatMoney(p.approval_threshold, p.currency)}</p>
              <p className="text-xs text-slate-500">{p.approved_merchants_only ? "Approved merchants only" : "Any merchant"} · {p.duplicate_purchase_check ? "duplicates blocked" : "duplicates allowed"} · approvals expire after {p.approval_ttl_minutes} min</p></div>
            <div className="flex items-center gap-2"><Badge tone={p.is_active ? "green" : "slate"}>{p.is_active ? "Active" : "Inactive"}</Badge>
              <Button variant="outline" onClick={() => setEditing({ p, f: fieldsOf(p, merchants.data?.approved_merchants ?? []) })}><Pencil className="h-3.5 w-3.5" />Edit</Button>
              <Button variant="outline" onClick={() => toggle(p)}>{p.is_active ? "Deactivate" : "Activate"}</Button></div>
          </Card>))}
          <p className="text-xs text-slate-500">Approved merchants: {merchants.data?.approved_merchants.join(", ") || "none"}</p></div>)}
      <Modal open={!!editing} onClose={() => setEditing(null)} title="Edit policy">
        {editing && <div className="space-y-4"><PolicyFields f={editing.f} set={(f) => setEditing({ ...editing, f })} />
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
            <Button onClick={saveEdit} disabled={saving || Number(editing.f.approval_threshold) > Number(editing.f.max_budget)}>{saving ? "Saving…" : "Save changes"}</Button></div></div>}
      </Modal>
    </>
  );
}
