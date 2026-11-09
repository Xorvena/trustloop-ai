import { CheckCircle2, XCircle } from "lucide-react";
import type { Risk, RuleCheck } from "@/types";

export function PolicyChecks({ checks }: { checks?: RuleCheck[] }) {
  if (!checks?.length) return <p className="text-sm text-slate-500">No evaluation recorded.</p>;
  return (
    <ul className="space-y-1.5">
      {checks.map((c) => (
        <li key={c.rule} className="flex items-start gap-2 text-sm">
          {c.passed ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />}
          <span className="text-slate-300"><span className="font-mono text-xs text-slate-500">{c.rule}</span> — {c.detail}</span>
        </li>
      ))}
    </ul>
  );
}

export function RiskSummary({ risk }: { risk: Risk | null }) {
  if (!risk) return null;
  const all = [...risk.signals, ...risk.ai_signals];
  return (
    <div className="text-sm">
      <p className="text-slate-300">Risk score <span className="font-semibold text-strong">{risk.score}/100</span> ({risk.level}). <span className="text-slate-500">Heuristic, not fraud detection.</span></p>
      {all.length > 0 && <ul className="mt-1 list-disc space-y-0.5 pl-5 text-slate-400">{all.map((s, i) => <li key={i}>{s.detail || s.code} <span className="text-slate-600">[{s.source === "gemini_advisory" ? "AI advisory" : "rule"}]</span></li>)}</ul>}
    </div>
  );
}
