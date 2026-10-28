"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { post } from "@/lib/api";
import { date, int, isNum, money, num, pct } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Backtest, Metrics, Source, Validation } from "@/lib/types";

import { Button, EmptyState, Field, Input, IssueList, LinkButton, LoadingBlock, Select, Stat, Value } from "./ui";

export function sourceLabel(s: Source): string {
  return `${s.symbol} ${s.timeframe} · ${s.provider}${s.is_synthetic ? " (synthetic)" : ""} · ${int(s.row_count)} candles · ${date(s.first_time)} – ${date(s.last_time)}`;
}

export function useSources() {
  return useApi<Source[]>("/market-data/sources");
}

/** Backtests need a source whose symbol and timeframe match the strategy (enforced by the API too). */
export function compatibleSources(sources: Source[], symbol?: string, timeframe?: string): Source[] {
  return sources.filter((s) => s.row_count > 0 && (!symbol || s.symbol === symbol) && (!timeframe || s.timeframe === timeframe));
}

export function NoCompatibleData({ symbol, timeframe }: { symbol?: string; timeframe?: string }) {
  return (
    <EmptyState title={`No ${symbol ?? ""} ${timeframe ?? ""} data yet`} action={<LinkButton href="/settings#market-data" variant="primary">Add market data</LinkButton>}>
      The strategy trades {symbol} on {timeframe} candles. Add a matching data source in Settings (CSV, Binance fetch or synthetic demo data), or change the strategy&apos;s symbol and timeframe.
    </EmptyState>
  );
}

function toMs(v: string): number | null {
  if (!v) return null;
  const t = Date.parse(`${v}T00:00:00Z`);
  return Number.isFinite(t) ? t : null;
}

export function NoDataNotice() {
  return (
    <EmptyState title="No market data yet" action={<LinkButton href="/settings#market-data" variant="primary">Add market data</LinkButton>}>
      Add candles in Settings first: CSV upload, Binance fetch, or synthetic demo data (clearly marked).
    </EmptyState>
  );
}

/** Starts a backtest for a strategy (current version unless `versionId` is set) and opens the result page. */
export function RunBacktestForm({ strategyId, versionId, symbol, timeframe, fee, slippage }: { strategyId: string; versionId?: string; symbol?: string; timeframe?: string; fee?: number; slippage?: number }) {
  const router = useRouter();
  const { data: sources, loading } = useSources();
  const [sourceId, setSourceId] = useState("");
  const [capital, setCapital] = useState("10000");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [feeBps, setFeeBps] = useState(fee !== undefined ? String(fee) : "");
  const [slipBps, setSlipBps] = useState(slippage !== undefined ? String(slippage) : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (loading && !sources) return <LoadingBlock rows={2} />;
  if (!sources || sources.length === 0) return <NoDataNotice />;
  const usable = compatibleSources(sources, symbol, timeframe);
  if (usable.length === 0) return <NoCompatibleData symbol={symbol} timeframe={timeframe} />;
  const selected = usable.some((s) => s.id === sourceId) ? sourceId : usable[0].id;

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const b = await post<Backtest>(`/strategies/${strategyId}/backtests`, {
        strategy_version_id: versionId ?? null,
        market_data_source_id: selected,
        initial_capital: Number(capital),
        start_time: toMs(start),
        end_time: toMs(end),
        fee_bps: feeBps === "" ? null : Number(feeBps),
        slippage_bps: slipBps === "" ? null : Number(slipBps),
      });
      router.push(`/backtests/${b.id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Field label="Data source" className="md:col-span-2 xl:col-span-3" hint={`Showing sources for ${symbol} ${timeframe}.`}>
          {(id) => <Select id={id} value={selected} onChange={(e) => setSourceId(e.target.value)} options={usable.map((s) => ({ value: s.id, label: sourceLabel(s) }))} />}
        </Field>
        <Field label="Initial capital (USDT)">{(id) => <Input id={id} type="number" min={1} value={capital} onChange={(e) => setCapital(e.target.value)} />}</Field>
        <Field label="Start (UTC, optional)">{(id) => <Input id={id} type="date" value={start} onChange={(e) => setStart(e.target.value)} />}</Field>
        <Field label="End (UTC, optional)">{(id) => <Input id={id} type="date" value={end} onChange={(e) => setEnd(e.target.value)} />}</Field>
        <Field label="Fee override (bps)" hint="Empty uses the strategy's cost model.">
          {(id) => <Input id={id} type="number" min={0} step="0.5" value={feeBps} onChange={(e) => setFeeBps(e.target.value)} />}
        </Field>
        <Field label="Slippage override (bps)">{(id) => <Input id={id} type="number" min={0} step="0.5" value={slipBps} onChange={(e) => setSlipBps(e.target.value)} />}</Field>
      </div>
      <IssueList error={error} />
      <Button variant="primary" onClick={() => void run()} loading={busy} disabled={!selected}>
        Run backtest
      </Button>
    </div>
  );
}

export function RunValidationForm({ versionId, symbol, timeframe, onCreated }: { versionId: string; symbol?: string; timeframe?: string; onCreated: (v: Validation) => void }) {
  const { data: sources, loading } = useSources();
  const [sourceId, setSourceId] = useState("");
  const [train, setTrain] = useState("0.6");
  const [val, setVal] = useState("0.2");
  const [folds, setFolds] = useState("4");
  const [mult, setMult] = useState("2");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (loading && !sources) return <LoadingBlock rows={2} />;
  if (!sources || sources.length === 0) return <NoDataNotice />;
  const usable = compatibleSources(sources, symbol, timeframe);
  if (usable.length === 0) return <NoCompatibleData symbol={symbol} timeframe={timeframe} />;
  const selected = usable.some((s) => s.id === sourceId) ? sourceId : usable[0].id;

  async function run() {
    setBusy(true);
    setError(null);
    try {
      onCreated(
        await post<Validation>("/validations", {
          strategy_version_id: versionId,
          market_data_source_id: selected,
          train_fraction: Number(train),
          validation_fraction: Number(val),
          folds: Number(folds),
          cost_multiplier: Number(mult),
        }),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <Field label="Data source" className="md:col-span-2 xl:col-span-5">
          {(id) => <Select id={id} value={selected} onChange={(e) => setSourceId(e.target.value)} options={usable.map((s) => ({ value: s.id, label: sourceLabel(s) }))} />}
        </Field>
        <Field label="Train fraction">{(id) => <Input id={id} type="number" step="0.05" min={0.25} max={0.85} value={train} onChange={(e) => setTrain(e.target.value)} />}</Field>
        <Field label="Validation fraction">{(id) => <Input id={id} type="number" step="0.05" min={0} max={0.45} value={val} onChange={(e) => setVal(e.target.value)} />}</Field>
        <Field label="Walk-forward folds">{(id) => <Input id={id} type="number" min={2} max={10} value={folds} onChange={(e) => setFolds(e.target.value)} />}</Field>
        <Field label="Cost stress multiplier">{(id) => <Input id={id} type="number" step="0.5" min={1} max={5} value={mult} onChange={(e) => setMult(e.target.value)} />}</Field>
      </div>
      <IssueList error={error} />
      <Button variant="primary" onClick={() => void run()} loading={busy} disabled={!selected}>
        Run validation
      </Button>
    </div>
  );
}

export const METRIC_LABELS: Record<string, string> = {
  net_return: "Net return",
  gross_return: "Gross return (before costs)",
  final_equity: "Final equity",
  max_drawdown: "Max drawdown",
  trade_count: "Trades",
  win_rate: "Win rate",
  profit_factor: "Profit factor",
  expectancy: "Expectancy per trade",
  expectancy_r: "Expectancy (R)",
  avg_win: "Average win",
  avg_loss: "Average loss",
  largest_loss: "Largest loss",
  avg_holding_hours: "Avg. holding time",
  avg_holding_bars: "Avg. holding (candles)",
  exposure: "Time in market",
  total_fees: "Fees paid",
  total_slippage: "Slippage cost",
  expectancy_ci_low: "Expectancy 95% CI low",
  expectancy_ci_high: "Expectancy 95% CI high",
};

export function formatMetric(key: string, v: number | null | undefined): string {
  if (!isNum(v)) return "n/a";
  switch (key) {
    case "net_return":
    case "gross_return":
    case "max_drawdown":
    case "win_rate":
    case "exposure":
      return pct(v, 2, key.endsWith("return"));
    case "trade_count":
    case "avg_holding_bars":
      return int(v);
    case "profit_factor":
    case "expectancy_r":
      return num(v, 2);
    case "avg_holding_hours":
      return v >= 48 ? `${num(v / 24, 1)} d` : `${num(v, 1)} h`;
    default:
      return money(v, key === "expectancy" || key.startsWith("expectancy_ci"));
  }
}

const SIGNED = new Set(["net_return", "gross_return", "expectancy", "expectancy_r"]);

export function MetricStat({ k, metrics, notes }: { k: string; metrics: Metrics; notes?: Record<string, string> }) {
  const v = metrics[k];
  const text = formatMetric(k, v);
  return (
    <Stat
      label={METRIC_LABELS[k] ?? k}
      title={notes?.[k]}
      value={SIGNED.has(k) ? <Value v={v} text={text} /> : k === "max_drawdown" && isNum(v) ? <span className="num text-negative">{text}</span> : <span className="num">{text}</span>}
      sub={notes?.[k]}
    />
  );
}

/** Compact metric cells for tables (train / validation / test). */
export function MetricCell({ k, m }: { k: string; m: Record<string, number | null | string | undefined> | undefined }) {
  const v = m?.[k];
  if (typeof v !== "number") return <span className="text-fg-faint">n/a</span>;
  const text = formatMetric(k, v);
  return SIGNED.has(k) ? <Value v={v} text={text} /> : <span className="num">{text}</span>;
}
