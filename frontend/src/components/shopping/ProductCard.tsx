import { CheckCircle2, ShieldAlert, XCircle } from "lucide-react";
import { Badge, Button, Card } from "@/components/shared/ui";
import { formatMoney } from "@/lib/utils";
import type { SearchResult } from "@/types";
import { ProductImage } from "./ProductImage";

const SKIP_SPECS = new Set(["anc"]);
const fmt = (v: unknown) => (Array.isArray(v) ? v.join(", ") : typeof v === "boolean" ? (v ? "yes" : "no") : String(v));

export function ProductCard({ r, top, busy, onPropose, onApproveMerchant }: { r: SearchResult; top?: boolean; busy: boolean; onPropose: () => void; onApproveMerchant?: (merchant: string) => void }) {
  const p = r.product;
  const out = p.availability === "out_of_stock";
  return (
    <Card className="flex flex-col p-5">
      <ProductImage src={p.image_url} source={p.image_source} name={p.name} className="mb-3 h-32" />
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium text-strong">{p.name}</p>
        {r.kind === "match" ? (top ? <Badge tone="green">Top match</Badge> : <Badge tone="green">Match</Badge>) : <Badge tone="amber">Alternative</Badge>}
      </div>
      <p className="text-xs text-slate-500">{p.brand} · {p.model} · {p.merchant}</p>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <p className="text-lg font-semibold text-strong">{formatMoney(p.price, p.currency)}</p>
        <Badge tone={out ? "red" : p.availability === "limited_stock" ? "amber" : "green"}>{p.availability.replaceAll("_", " ")}</Badge>
        {p.source.includes("fictional") && <Badge tone="slate">Fictional demo brand</Badge>}
        {p.source.startsWith("provider:") && <Badge tone="violet">Demo provider</Badge>}
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-1 text-xs text-slate-400">
        {Object.entries(p.specs).filter(([k]) => !SKIP_SPECS.has(k)).slice(0, 6).map(([k, v]) => <div key={k}><dt className="text-slate-600">{k.replaceAll("_", " ")}</dt><dd className="truncate">{fmt(v)}</dd></div>)}
      </dl>
      {r.kind === "alternative" && r.unmet.length > 0 && (
        <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-2 text-xs">
          <p className="mb-1 font-medium text-warn">Does not satisfy:</p>
          <ul className="space-y-0.5 text-slate-300">{r.unmet.map((u) => <li key={u} className="flex gap-1"><XCircle className="mt-0.5 h-3 w-3 shrink-0 text-bad" />{u}</li>)}</ul>
        </div>
      )}
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer text-violet-400">Requirement checks</summary>
        <ul className="mt-1 space-y-0.5">{r.checks.map((c) => <li key={c.key} className="flex gap-1 text-slate-400">{c.met ? <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-ok" /> : <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-bad" />}<span>{c.label} <span className="text-slate-600">({c.detail})</span></span></li>)}</ul>
      </details>
      {r.unconfirmed_terms.length > 0 && <p className="mt-2 text-xs text-slate-500">Not confirmed in product details: {r.unconfirmed_terms.slice(0, 4).join(", ")}</p>}
      {!r.merchant_approved && (
        <div className="mt-2 rounded-lg border border-amber-500/20 bg-amber-500/5 p-2 text-xs text-slate-300">
          <p>Merchant <b>{p.merchant}</b> is not on your approved list, so a purchase will need your review.</p>
          {onApproveMerchant && <button className="mt-1 text-violet-400 hover:underline" onClick={() => onApproveMerchant(p.merchant)}>Add {p.merchant} to approved merchants</button>}
        </div>
      )}
      {r.suspicious_description && <p className="mt-2 flex items-start gap-1 text-xs text-bad"><ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />Description contains instruction-like text and is treated as untrusted data.</p>}
      <Button className="mt-3" variant={r.kind === "match" ? "primary" : "outline"} disabled={busy || out} onClick={onPropose}>
        {out ? "Out of stock" : busy ? "Submitting…" : r.kind === "alternative" ? "Propose this alternative" : "Create purchase proposal"}
      </Button>
    </Card>
  );
}
