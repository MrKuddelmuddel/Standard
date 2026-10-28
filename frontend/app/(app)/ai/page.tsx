"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, EmptyState, ErrorState, Field, IssueList, KV, LoadingBlock, Notice, PageHeader, Panel, Select, StatusBadge, Table, Textarea } from "@/components/ui";
import { post } from "@/lib/api";
import { ago } from "@/lib/format";
import { isActive, useApi } from "@/lib/hooks";
import type { AgentRun, Page } from "@/lib/types";

export type AiStatus = { configured: boolean; provider: string | null; model: string | null; limits: Record<string, number>; message: string | null };

const EXAMPLES = [
  "Test whether buying BTC after a pullback to the 50 EMA in an uptrend (price above the 200 EMA) works on 4h candles, with an ATR stop.",
  "Build a breakout strategy for ETH on 1h: enter when the close breaks the 30-candle high with volume above average, exit at 2R.",
  "Mean reversion on BTC 1h: buy when RSI(14) is below 30 and close is above the 200 EMA, exit when RSI recovers above 55.",
];

export default function AiPage() {
  const router = useRouter();
  const status = useApi<AiStatus>("/ai/status");
  const runs = useApi<Page<AgentRun>>("/ai/runs?limit=30", { pollMs: 3000, shouldPoll: (d) => !!d?.items.some((r) => isActive(r.status)) });
  const [task, setTask] = useState("");
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const r = await post<AgentRun>("/ai/research", { task, symbol, timeframe });
      router.push(`/ai/${r.id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  const st = status.data;
  return (
    <>
      <PageHeader title="AI Research" subtitle="Describe a trading idea in plain language. The assistant turns it into a validated strategy draft; you confirm before anything is created or tested." />
      <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
        <Panel title="New research task">
          {status.loading && !st ? (
            <LoadingBlock />
          ) : status.error ? (
            <ErrorState error={status.error} onRetry={status.reload} />
          ) : st && !st.configured ? (
            <EmptyState title="No AI provider configured" action={<Link href="/strategies/new" className="text-accent hover:underline">Build a strategy manually instead</Link>}>
              {st.message}
            </EmptyState>
          ) : (
            <div className="space-y-3">
              <Field label="Idea" hint="10 to 4000 characters. Only supported indicators and rules can be used; anything else is reported back as unsupported.">
                {(id) => <Textarea id={id} className="min-h-32" value={task} maxLength={4000} onChange={(e) => setTask(e.target.value)} placeholder="What do you want to test?" />}
              </Field>
              <div className="flex flex-wrap gap-1.5">
                {EXAMPLES.map((e, i) => (
                  <button key={i} type="button" onClick={() => setTask(e)} className="rounded-md border border-line px-2 py-1 text-left text-xs text-fg-muted hover:border-line-strong hover:text-fg">
                    Example {i + 1}
                  </button>
                ))}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Symbol">
                  {(id) => (
                    <Select
                      id={id}
                      value={symbol}
                      onChange={(e) => setSymbol(e.target.value)}
                      options={["BTCUSDT", "ETHUSDT"].map((v) => ({ value: v, label: v }))}
                    />
                  )}
                </Field>
                <Field label="Timeframe">
                  {(id) => (
                    <Select
                      id={id}
                      value={timeframe}
                      onChange={(e) => setTimeframe(e.target.value)}
                      options={["15m", "1h", "4h", "1d"].map((v) => ({ value: v, label: v }))}
                    />
                  )}
                </Field>
              </div>
              <IssueList error={error} />
              <Button variant="primary" onClick={() => void start()} loading={busy} disabled={task.trim().length < 10}>
                Draft strategy
              </Button>
            </div>
          )}
        </Panel>
        <Panel title="How it works">
          <ol className="list-decimal space-y-1.5 pl-4 text-[13px] text-fg-muted">
            <li>The assistant can only list supported indicators, validate a draft and submit a proposal. It cannot place orders or reach the internet.</li>
            <li>You review the hypothesis, rules, assumptions and unsupported parts.</li>
            <li>On confirm, the strategy is saved and a backtest plus out-of-sample validation run on the data you choose.</li>
            <li>Optionally ask for an explanation of the results. The explanation reads stored metrics only.</li>
          </ol>
          {st?.configured && (
            <div className="mt-4">
              <KV
                items={[
                  ["Provider", st.provider],
                  ["Model", st.model],
                  ["Tool calls per run", String(st.limits.max_tool_calls)],
                  ["Time limit", `${st.limits.max_seconds} s`],
                  ["Runs per day", String(st.limits.max_runs_per_day)],
                ]}
              />
            </div>
          )}
          <Notice tone="warning">
            <span className="text-xs">AI output can be wrong. Every number shown comes from the backtest engine, not from the model.</span>
          </Notice>
        </Panel>
      </div>
      <Panel title="Runs" className="mt-4" pad={false}>
        {runs.error ? (
          <div className="p-4">
            <ErrorState error={runs.error} onRetry={runs.reload} />
          </div>
        ) : !runs.data ? (
          <div className="p-4">
            <LoadingBlock />
          </div>
        ) : runs.data.items.length === 0 ? (
          <p className="p-4 text-[13px] text-fg-muted">No AI runs yet.</p>
        ) : (
          <Table head={["Task", "Kind", "Status", "Model", "Created"]}>
            {runs.data.items.map((r) => (
              <tr key={r.id}>
                <td className="max-w-md truncate">
                  <Link href={`/ai/${r.id}`} className="text-fg hover:text-accent">
                    {r.task}
                  </Link>
                </td>
                <td className="text-fg-muted">{r.kind}</td>
                <td>
                  <StatusBadge status={r.status} />
                </td>
                <td className="text-fg-muted">{r.model ?? r.provider}</td>
                <td className="text-fg-muted">{ago(r.created_at)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>
    </>
  );
}
