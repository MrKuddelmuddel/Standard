"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, Field, Input, Notice } from "@/components/ui";
import { errorIssues, errorMessage, post } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post(mode === "login" ? "/auth/login" : "/auth/register", { email, password });
      router.replace("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const issues = errorIssues(error);
  return (
    <main className="grid min-h-screen place-items-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center gap-2">
          <span aria-hidden className="grid size-7 place-items-center rounded-sm bg-accent text-xs font-bold text-[#06231a]">
            NQ
          </span>
          <span className="text-sm font-semibold tracking-wide">NEXUS QUANT</span>
        </div>
        <h1 className="text-lg font-semibold">{mode === "login" ? "Sign in" : "Create account"}</h1>
        <p className="mt-1 text-[13px] text-fg-muted">Backtest crypto strategies, validate them out of sample and keep a trading journal.</p>
        <form onSubmit={submit} className="mt-6 space-y-3" noValidate>
          <Field label="Email">{(id) => <Input id={id} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}</Field>
          <Field label="Password" hint={mode === "register" ? "At least 10 characters." : undefined}>
            {(id) => (
              <Input
                id={id}
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                required
                minLength={10}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}
          </Field>
          {error ? (
            <Notice tone="negative">
              {errorMessage(error)}
              {issues.length > 0 && <span className="block text-xs">{issues.map((i) => i.message).join(" ")}</span>}
            </Notice>
          ) : null}
          <Button type="submit" variant="primary" className="w-full" loading={busy}>
            {mode === "login" ? "Sign in" : "Create account"}
          </Button>
        </form>
        <button
          type="button"
          className="mt-4 text-[13px] text-fg-muted underline-offset-2 hover:text-fg hover:underline"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError(null);
          }}
        >
          {mode === "login" ? "No account yet? Create one" : "Already have an account? Sign in"}
        </button>
        <p className="mt-8 text-[11px] leading-relaxed text-fg-faint">
          NEXUS QUANT is an analysis, backtesting and simulation tool. It does not execute real trades and does not give investment advice.
          Historical results are no guarantee of future results.
        </p>
      </div>
    </main>
  );
}
