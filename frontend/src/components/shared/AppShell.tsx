"use client";
import { BarChart3, Bot, ClipboardCheck, LayoutDashboard, LogOut, Menu, ScrollText, ShieldCheck, ShoppingBag, SlidersHorizontal, WalletCards } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api, auth } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { User } from "@/types";
import { ThemeToggle } from "./ThemeToggle";
import { ToastProvider } from "./ui";

const NAV = [
  { href: "/dashboard", label: "Command Center", icon: LayoutDashboard },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/policies", label: "Policy Builder", icon: SlidersHorizontal },
  { href: "/shop", label: "AI Shopping", icon: ShoppingBag },
  { href: "/approvals", label: "Approvals", icon: ClipboardCheck },
  { href: "/transactions", label: "Transactions", icon: WalletCards },
  { href: "/trust", label: "Trust Center", icon: ShieldCheck },
  { href: "/audit", label: "Audit Log", icon: ScrollText },
];

export function AppShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!auth.get()) { router.replace("/login"); return; }
    api<User>("/api/auth/me").then(setUser).catch(() => router.replace("/login"));
  }, [router]);

  useEffect(() => setOpen(false), [path]);
  if (!user) return <div className="grid min-h-screen place-items-center text-slate-500">Loading…</div>;

  return (
    <ToastProvider>
      <div className="min-h-screen lg:grid lg:grid-cols-[250px_1fr]">
        <aside className={cn("fixed inset-y-0 left-0 z-30 w-[250px] border-r border-navy-700 bg-navy-900 p-4 transition-transform lg:static lg:translate-x-0", open ? "translate-x-0" : "-translate-x-full")}>
          <div className="mb-8 flex items-center gap-2 px-2">
            <div className="grid h-9 w-9 place-items-center rounded-md bg-strong"><BarChart3 className="h-5 w-5 text-inverse" /></div>
            <div><p className="text-sm font-semibold text-strong">TrustLoop</p><p className="text-[11px] text-slate-500">Agent payment governance</p></div>
          </div>
          <nav className="space-y-1" aria-label="Main">
            {NAV.map(({ href, label, icon: Icon }) => (
              <Link key={href} href={href} className={cn("flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors", path.startsWith(href) ? "bg-navy-800 font-medium text-strong" : "text-slate-400 hover:bg-navy-800 hover:text-slate-100")}>
                <Icon className="h-4 w-4" />{label}
              </Link>
            ))}
          </nav>
          <p className="absolute bottom-4 left-4 right-4 rounded-md border border-navy-700 p-3 text-[11px] leading-relaxed text-slate-500">PayPal Sandbox only. No real money moves.</p>
        </aside>
        <div className="min-w-0">
          <header className="sticky top-0 z-20 flex items-center justify-between border-b border-navy-700 bg-navy-900 px-4 py-3 lg:px-8">
            <button className="rounded p-2 text-slate-300 hover:bg-navy-800 lg:hidden" aria-label="Open navigation" onClick={() => setOpen((o) => !o)}><Menu className="h-5 w-5" /></button>
            <span className="hidden lg:block" />
            <div className="flex items-center gap-3">
              <div className="text-right"><p className="text-sm font-medium text-slate-100">{user.name}</p><p className="text-xs text-slate-500">{user.email}</p></div>
              <ThemeToggle />
              <button aria-label="Sign out" className="rounded-lg p-2 text-slate-400 hover:bg-navy-800" onClick={() => { auth.clear(); router.replace("/login"); }}><LogOut className="h-4 w-4" /></button>
            </div>
          </header>
          <main className="p-4 lg:p-8">{children}</main>
        </div>
      </div>
    </ToastProvider>
  );
} 