"use client";
import { ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { Button, Card, ErrorState, Input } from "@/components/shared/ui";
import { api, ApiError, auth } from "@/lib/api";
import type { User } from "@/types";

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [f, setF] = useState({ email: "", name: "", password: "" });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await api<{ access_token: string; user: User }>(`/api/auth/${mode}`, { method: "POST", body: mode === "login" ? { email: f.email, password: f.password } : f });
      auth.set(r.access_token);
      router.replace("/dashboard");
    } catch (x) { setErr(x instanceof ApiError ? x.message : "Something went wrong"); }
    finally { setBusy(false); }
  }

  return (
    <div className="relative grid min-h-screen place-items-center bg-navy-900 p-4">
      <ThemeToggle className="absolute right-4 top-4" />
      <Card className="w-full max-w-md p-8">
        <div className="mb-6 flex items-center gap-3"><div className="grid h-10 w-10 place-items-center rounded-md bg-strong"><ShieldCheck className="h-5 w-5 text-inverse" /></div>
          <div><h1 className="text-xl font-semibold text-strong">TrustLoop</h1><p className="text-sm text-slate-400">Sign in to your workspace</p></div></div>
        <form onSubmit={submit} className="space-y-4">
          {mode === "register" && <Input label="Name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />}
          <Input label="Email" type="email" required autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
          <Input label="Password (min 8 characters)" type="password" required minLength={8} autoComplete={mode === "login" ? "current-password" : "new-password"} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          {err && <ErrorState message={err} />}
          <Button type="submit" disabled={busy} className="w-full">{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</Button>
        </form>
        <button className="mt-4 text-sm text-violet-400 hover:underline" onClick={() => { setMode(mode === "login" ? "register" : "login"); setErr(null); }}>
          {mode === "login" ? "New here? Create an account" : "Already have an account? Sign in"}
        </button>
      </Card>
    </div>
  );
} 