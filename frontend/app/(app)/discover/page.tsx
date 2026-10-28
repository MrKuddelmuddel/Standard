"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { NoDataNotice, sourceLabel, useSources } from "@/components/runs";
import { Button, Checkbox, ErrorState, Field, Input, IssueList, LoadingBlock, Notice, PageHeader, Panel, Select, StatusBadge, SyntheticBadge, Table } from "@/components/ui";
import { post } from "@/lib/api";
import { ago, int } from "@/lib/format";
import { isActive, useApi } from "@/lib/hooks";
import type { Discovery, Page } from "@/lib/types";

const TEMPLATES = [
  { id: "ema_cross", label: "EMA crossover", params: ["ema_fast", "ema_slow"] },
  { id: "rsi_reversion", label: "RSI mean reversion", params: ["rsi_period", "rsi_entry", "rsi_exit"] },
  { id: "breakout", label: "Range breakout", params: ["breakout_lookback"] },
] as const;

const DEFAULT_GRID: Record<string, string> = {
  ema_fast: "10, 20, 30",
  ema_slow: "50, 100, 200",
  rsi_period: "14",
  rsi_entry: "25, 30, 35",
  rsi_exit: "55, 65",
  breakout_lookback: "20, 40, 60",
  stop_atr: "1.5, 2.5",
  take_profit_r: "2, 3",
};

const PARAM_LABEL: Record<string, string> = {
  ema_fast: "Fast EMA periods",
  ema_slow: "Slow EMA periods",
  rsi_period: "RSI periods",
  rsi_entry: "RSI entry levels",
  rsi_exit: "RSI exit levels",
  breakout_lookback: "Breakout lookbacks",
  stop_atr: "Stop (ATR multiples)",
  take_profit_r: "Target (R multiples)",
};

const parseList = (s: string) =>
  s
    .split(/[,\s]+/)
    .filter(Boolean)
    .map(Number)
    .filter((n) => Number.isFinite(n));

export default function DiscoverPage() {
  const router = useRouter();
  const { data: sources, loading: sourcesLoading } = useSources();
  const jobs = useApi<Page<Discovery>>("/discoveries?limit=20", { pollMs: 3000, shouldPoll: (d) => !!d?.items.some((x) => isActive(x.status)) });
  const [sourceId, setSourceId] = useState("");
  const [templates, setTemplates] = useState<string[]>(["ema_cross", "rsi_reversion", "breakout"]);
  const [direction, setDirection] = useState("long");
  const [grid, setGrid] = useState(DEFAULT_GRID);
  const [cfg, setCfg] = useState({ fee_bps: "10", slippage_bps: "5", max_candidates: "60", min_trades: "30", max_drawdown: "0.5", shortlist: "8", train_fraction: "0.6", validation_fraction: "0.2", max_seconds: "120" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const src = sources?.find((s) => s.id === sourceId) ?? sources?.find((s) => s.row_count > 0);
  const usedParams = new Set<string>(["stop_atr", "take_profit_r", ...TEMPLATES.filter((t) => templates.includes(t.id)).flatMap((t) => t.params)]);
  const combos = TEMPLATES.filter((t) => templates.includes(t.id)).reduce((acc, t) => {
    const p = [...t.params, "stop_atr", "take_profit_r"].reduce((x, k) => x * Math.max(parseList(grid[k]).length, 1), 1);
    return acc + p;
  }, 0);

  async function start() {
    if (!src) return;
    setBusy(true);
    setError(null);
    try {
      const params = Object.fromEntries([...usedParams].map((k) => [k, parseList(grid[k])]));
      const d = await post<Discovery>("/discoveries", {
        market_data_source_id: src.id,
        config: {
          symbol: src.symbol,
          timeframe: src.timeframe,
          direction,
          templates,
          params,
          fee_bps: Number(cfg.fee_bps),
          slippage_bps: Number(cfg.slippage_bps),
          max_candidates: Number(cfg.max_candidates),
          min_trades: Number(cfg.min_trades),
          max_drawdown: Number(cfg.max_drawdown),
          shortlist: Number(cfg.shortlist),
          train_fraction: Number(cfg.train_fraction),
          validation_fraction: Number(cfg.validation_fraction),
          max_seconds: Number(cfg.max_seconds),
        },
      });
      router.push(`/discover/${d.id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  const numField = (key: keyof typeof cfg, label: string, hint?: string, step = "1") => (
    <Field label={label} hint={hint}>
      {(id) => <Input id={id} type="number" step={step} value={cfg[key]} onChange={(e) => setCfg({ ...cfg, [key]: e.target.value })} />}
    </Field>
  );

  return (
    <>
      <PageHeader title="Discover" subtitle="Search a bounded grid of rule templates. Candidates are ranked on the validation segment only; the test segment is evaluated once for shortlisted ones." />
      <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
        <Panel title="New discovery job">
          {sourcesLoading && !sources ? (
            <LoadingBlock />
          ) : !sources || sources.length === 0 ? (
            <NoDataNotice />
          ) : (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Field label="Data source" className="md:col-span-2" hint="Symbol and timeframe come from the data source.">
                  {(id) => <Select id={id} value={src?.id ?? ""} onChange={(e) => setSourceId(e.target.value)} options={sources.map((s) => ({ value: s.id, label: sourceLabel(s) }))} />}
                </Field>
                <fieldset className="md:col-span-2">
                  <legend className="mb-1 text-xs font-medium text-fg-muted">Templates</legend>
                  <div className="flex flex-wrap gap-4">
                    {TEMPLATES.map((t) => (
                      <Checkbox key={t.id} label={t.label} checked={templates.includes(t.id)} onChange={(on) => setTemplates(on ? [...templates, t.id] : templates.filter((x) => x !== t.id))} />
                    ))}
                  </div>
                </fieldset>
                <Field label="Direction" hint={direction === "short" ? "Shorts run as simulated futures without funding costs." : undefined}>
                  {(id) => (
                    <Select
                      id={id}
                      value={direction}
                      onChange={(e) => setDirection(e.target.value)}
                      options={[
                        { value: "long", label: "Long" },
                        { value: "short", label: "Short (futures sim)" },
                      ]}
                    />
                  )}
                </Field>
              </div>
              <div>
                <div className="mb-2 text-xs font-medium text-fg-muted">Parameter grid (comma separated)</div>
                <div className="grid gap-3 md:grid-cols-2">
                  {Object.keys(DEFAULT_GRID)
                    .filter((k) => usedParams.has(k))
                    .map((k) => (
                      <Field key={k} label={PARAM_LABEL[k]}>
                        {(id) => <Input id={id} value={grid[k]} onChange={(e) => setGrid({ ...grid, [k]: e.target.value })} />}
                      </Field>
                    ))}
                </div>
                <p className="mt-2 text-xs text-fg-faint">
                  About {int(combos)} combinations before de-duplication; at most {cfg.max_candidates} are tested.
                </p>
              </div>
              <details>
                <summary className="cursor-pointer text-xs text-fg-muted">Costs, filters and limits</summary>
                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  {numField("fee_bps", "Fee (bps)", undefined, "0.5")}
                  {numField("slippage_bps", "Slippage (bps)", undefined, "0.5")}
                  {numField("max_candidates", "Max candidates")}
                  {numField("min_trades", "Min trades (validation)")}
                  {numField("max_drawdown", "Max drawdown (0–1)", undefined, "0.05")}
                  {numField("shortlist", "Shortlist size")}
                  {numField("train_fraction", "Train fraction", undefined, "0.05")}
                  {numField("validation_fraction", "Validation fraction", undefined, "0.05")}
                  {numField("max_seconds", "Time limit (s)")}
                </div>
              </details>
              <Notice tone="info">
                Testing many variants on the same history finds lucky fits. Treat the top candidate as a hypothesis and confirm it with validation and paper trading.
              </Notice>
              <IssueList error={error} />
              <Button variant="primary" onClick={() => void start()} loading={busy} disabled={!src || templates.length === 0}>
                Start discovery
              </Button>
            </div>
          )}
        </Panel>
        <Panel title="Recent jobs" pad={false}>
          {jobs.error ? (
            <div className="p-4">
              <ErrorState error={jobs.error} onRetry={jobs.reload} />
            </div>
          ) : !jobs.data ? (
            <div className="p-4">
              <LoadingBlock />
            </div>
          ) : jobs.data.items.length === 0 ? (
            <p className="p-4 text-[13px] text-fg-muted">No discovery jobs yet.</p>
          ) : (
            <Table head={["Job", "Market", "Status", "Candidates", "Created"]}>
              {jobs.data.items.map((d) => (
                <tr key={d.id}>
                  <td>
                    <Link href={`/discover/${d.id}`} className="num text-fg hover:text-accent">
                      {d.id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="text-fg-muted">
                    {String(d.search_config.symbol ?? "")} {String(d.search_config.timeframe ?? "")} <SyntheticBadge show={d.is_synthetic_data} />
                  </td>
                  <td>
                    <StatusBadge status={d.status} />
                  </td>
                  <td className="num">{int(d.candidate_count)}</td>
                  <td className="text-fg-muted">{ago(d.created_at)}</td>
                </tr>
              ))}
            </Table>
          )}
        </Panel>
      </div>
    </>
  );
}
