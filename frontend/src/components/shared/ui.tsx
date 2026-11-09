"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { AlertTriangle, CheckCircle2, Inbox, X } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Button({ variant = "primary", className, ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "success" | "outline" }) {
  const v = {
    primary: "bg-strong text-inverse hover:opacity-90",
    ghost: "hover:bg-navy-700 text-slate-300",
    outline: "border border-navy-600 hover:bg-navy-700 text-slate-200",
    danger: "bg-red-500/15 text-bad hover:bg-red-500/25 border border-red-500/30",
    success: "bg-emerald-500/15 text-ok hover:bg-emerald-500/25 border border-emerald-500/30",
  }[variant];
  return <button {...p} className={cn("inline-flex items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50", v, className)} />;
}

export const Card = ({ className, children }: { className?: string; children: ReactNode }) => (
  <div className={cn("rounded-lg border border-navy-700 bg-navy-850 shadow-card", className)}>{children}</div>
);

const tones: Record<string, string> = {
  green: "bg-emerald-500/10 text-ok border-emerald-500/30", amber: "bg-amber-500/10 text-warn border-amber-500/30",
  red: "bg-red-500/10 text-bad border-red-500/30", violet: "bg-violet-500/10 text-violet-400 border-violet-500/30", slate: "bg-slate-500/10 text-slate-300 border-slate-500/30",
};
export const Badge = ({ tone = "slate", children }: { tone?: keyof typeof tones; children: ReactNode }) => (
  <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium", tones[tone])}>{children}</span>
);

const STATUS_TONE: Record<string, keyof typeof tones> = {
  APPROVED: "green", AUTHORIZED: "green", CAPTURED: "green", COMPLETED: "green", active: "green", low: "green",
  REQUIRES_APPROVAL: "amber", REVIEW: "amber", PENDING_APPROVAL: "amber", PAYPAL_ORDER_CREATED: "violet", medium: "amber", inactive: "amber",
  BLOCKED: "red", REJECTED: "red", FAILED: "red", EXPIRED: "red", REFUNDED: "red", revoked: "red", high: "red", critical: "red",
};
export const StatusBadge = ({ value }: { value: string | null }) =>
  value ? <Badge tone={STATUS_TONE[value] ?? "slate"}>{value.replaceAll("_", " ")}</Badge> : <span className="text-slate-500">—</span>;

const field = "w-full rounded-md border border-navy-600 bg-navy-850 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500";
export const Input = ({ label, className, ...p }: InputHTMLAttributes<HTMLInputElement> & { label?: string }) => (
  <label className="block text-sm text-slate-400">{label}<input {...p} className={cn(field, label && "mt-1", className)} /></label>
);
export const Textarea = ({ label, className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string }) => (
  <label className="block text-sm text-slate-400">{label}<textarea {...p} className={cn(field, label && "mt-1", className)} /></label>
);

export const Skeleton = ({ className }: { className?: string }) => <div className={cn("skeleton rounded-lg", className)} aria-hidden />;
export const SkeletonRows = ({ n = 4 }: { n?: number }) => <div className="space-y-3" role="status" aria-label="Loading">{Array.from({ length: n }, (_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>;

export const EmptyState = ({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) => (
  <div className="flex flex-col items-center justify-center py-14 text-center">
    <Inbox className="mb-3 h-9 w-9 text-slate-600" />
    <p className="font-medium text-slate-200">{title}</p>
    {hint && <p className="mt-1 max-w-sm text-sm text-slate-500">{hint}</p>}
    {action && <div className="mt-4">{action}</div>}
  </div>
);

export const ErrorState = ({ message, onRetry }: { message: string; onRetry?: () => void }) => (
  <div role="alert" className="flex items-start gap-3 rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm">
    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
    <div className="flex-1 text-slate-300">{message}</div>
    {onRetry && <Button variant="outline" onClick={onRetry} className="py-1">Retry</Button>}
  </div>
);

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[94vw] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-navy-600 bg-navy-850 p-6 shadow-lg">
          <div className="mb-4 flex items-start justify-between gap-4">
            <Dialog.Title className="text-lg font-semibold text-strong">{title}</Dialog.Title>
            <Dialog.Close aria-label="Close" className="rounded p-1 text-slate-400 hover:bg-navy-700"><X className="h-4 w-4" /></Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">{title}</Dialog.Description>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  ); 
}

export function ConfirmDialog({ open, title, body, confirmLabel, danger, busy, onConfirm, onClose }: { open: boolean; title: string; body: ReactNode; confirmLabel: string; danger?: boolean; busy?: boolean; onConfirm: () => void; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div className="text-sm text-slate-300">{body}</div>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant={danger ? "danger" : "primary"} disabled={busy} onClick={onConfirm}>{busy ? "Working…" : confirmLabel}</Button>
      </div>
    </Modal>
  );
}

type Toast = { id: number; kind: "ok" | "err"; text: string };
const ToastCtx = createContext<(kind: Toast["kind"], text: string) => void>(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setItems((x) => [...x, { id, kind, text }]);
    setTimeout(() => setItems((x) => x.filter((t) => t.id !== id)), 5000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] space-y-2" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={cn("flex max-w-sm items-start gap-2 rounded-md border px-4 py-3 text-sm shadow-lg", t.kind === "ok" ? "border-emerald-500/30 bg-navy-800 text-slate-100" : "border-red-500/40 bg-navy-800 text-slate-100")}>
            {t.kind === "ok" ? <CheckCircle2 className="mt-0.5 h-4 w-4 text-ok" /> : <AlertTriangle className="mt-0.5 h-4 w-4 text-bad" />}
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const PageHeader = ({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) => (
  <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
    <div><h1 className="text-2xl font-semibold tracking-tight text-strong">{title}</h1>{subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}</div>
    {actions}
  </div>
);
