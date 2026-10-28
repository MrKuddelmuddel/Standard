"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useState } from "react";

import { SeriesChart } from "@/components/charts";
import { MetricStat } from "@/components/runs";
import { Badge, Button, ErrorState, Hash, JobProgress, KV, LinkButton, LoadingBlock, Notice, PageHeader, Panel, StatusBadge, SyntheticBadge, Table, Value } from "@/components/ui";
import { post } from "@/lib/api";
import { dt, formatJson, int, money, pct, price, qty } from "@/lib/format";
import { isActive, useApi } from "@/lib/hooks";
import type { Backtest, Page, Trade } from "@/lib/types";

const PAGE = 50;
const PRIMARY = ["net_return", "max_drawdown", "trade_count", "win_rate", "profit_factor", "expectancy_r"];
const SECONDARY = ["final_equity", "gross_return", "expectancy", "expectancy_ci_low", "expectancy_ci_high", "avg_win", "avg_loss", "largest_loss", "avg_holding_hours", "exposure", "total_fees", "total_slippage"];

export default function BacktestPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <BacktestDetail />
    </Suspense>
  );
}

function BacktestDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: b, error, loading, reload, setData } = useApi<Backtest>(`/backtests/${id}`, { pollMs: 1500, shouldPoll: (x) => !x || isActive(x.status) });
  const [cancelling, setCancelling] = useState(false);

  if (loading && !b) return <LoadingBlock rows={6} />;
  if (error || !b) return <ErrorState error={error} onRetry={reload} />;
  const r = b.result;
  const running = isActive(b.status);

  return (
    <>
      <PageHeader
        title={b.strategy ? `${b.strategy.name} · v${b.strategy.version_number}` : "Backtest"}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={b.status} />
            <SyntheticBadge show={b.is_synthetic_data} />
            <span>
              {dt(b.start_time)} → {dt(b.end_time)}
            </span>
          </span>
        }
        actions={
          <>
            {running && (
              <Button
                size="sm"
                variant="danger"
                loading={cancelling}
                onClick={async () => {
                  setCancelling(true);
                  try {
                    await post(`/backtests/${id}/cancel`);
                    await reload();
                  } finally {
                    setCancelling(false);
                  }
                }}
              >
                Cancel
              </Button>
            )}
            {b.strategy && (
              <LinkButton size="sm" href={`/strategies/${b.strategy.id}?tab=backtest`}>
                Strategy
              </LinkButton>
            )}
            {b.status === "completed" && b.strategy && (
              <LinkButton size="sm" href={`/paper?strategy_version_id=${b.strategy_version_id}&source_id=${b.market_data_source_id}`}>
                Start paper session
              </LinkButton>
            )}
          </>
        }
      />

      {running && (
        <Panel className="mb-4">
          <JobProgress job={b.job} />
          <p className="mt-2 text-xs text-fg-faint">The page updates automatically.</p>
        </Panel>
      )}
      {b.status === "failed" && (
        <Notice tone="negative" title="Backtest failed">
          {b.error_message ?? "Unknown error."} {b.error_code && <code className="text-xs">({b.error_code})</code>}
        </Notice>
      )}
      {b.status === "cancelled" && <Notice tone="info">This backtest was cancelled before it finished.</Notice>}

      {r && (
        <div className="space-y-4">
          {b.is_synthetic_data && (
            <Notice tone="warning" title="Synthetic data">
              This run used generated random-walk candles. The numbers test the software, not a market edge.
            </Notice>
          )}
          {(r.warnings.length > 0 || r.metric_notes.sample_size) && (
            <Notice tone="warning" title="Warnings">
              <ul className="list-disc pl-4 text-xs">
                {r.metric_notes.sample_size && <li>{r.metric_notes.sample_size}</li>}
                {r.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </Notice>
          )}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {PRIMARY.map((k) => (
              <MetricStat key={k} k={k} metrics={r.metrics} notes={r.metric_notes} />
            ))}
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <Panel title="Equity">
              <SeriesChart label="Equity" points={r.curve.map((p) => [p[0], p[1]])} format={(v) => money(v)} baseline={b.initial_capital} />
            </Panel>
            <Panel title="Drawdown">
              <SeriesChart label="Drawdown" kind="area-negative" points={r.curve.map((p) => [p[0], p[2]])} format={(v) => pct(v, 1)} />
            </Panel>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            {SECONDARY.filter((k) => k in r.metrics).map((k) => (
              <MetricStat key={k} k={k} metrics={r.metrics} notes={r.metric_notes} />
            ))}
          </div>
          <Trades id={b.id} total={Number(r.metrics.trade_count ?? 0)} />
          <Panel title="Reproducibility">
            <div className="grid gap-4 lg:grid-cols-2">
              <KV
                items={[
                  ["Run ID", <code key="id" className="text-xs">{b.id}</code>],
                  ["Strategy version", <code key="v" className="text-xs">{b.strategy_version_id}</code>],
                  ["Data source", <code key="s" className="text-xs">{b.market_data_source_id}</code>],
                  ["Data revision", `r${b.data_revision}`],
                  ["Data fingerprint", <Hash key="f" value={b.data_fingerprint} len={16} />],
                ]}
              />
              <KV
                items={[
                  ["Engine", b.engine_version],
                  ["Execution model", b.execution_model_version],
                  ["Fee model", `${b.fee_model.fee_bps} bps per fill`],
                  ["Slippage model", `${b.slippage_model.slippage_bps} bps, adverse`],
                  ["Initial capital", money(b.initial_capital)],
                  ["Completed", dt(b.completed_at)],
                ]}
              />
            </div>
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-fg-muted">Full configuration (JSON)</summary>
              <pre className="mt-2 max-h-96 overflow-auto rounded-md bg-panel-2 p-3 text-xs">{formatJson(b.config_json)}</pre>
            </details>
          </Panel>
        </div>
      )}
      {!r && !running && b.status === "completed" && (
        <Button onClick={() => void reload().then(() => setData(b))}>Reload</Button>
      )}
    </>
  );
}

function Trades({ id, total }: { id: string; total: number }) {
  const [offset, setOffset] = useState(0);
  const { data, error, reload } = useApi<Page<Trade>>(`/backtests/${id}/trades?limit=${PAGE}&offset=${offset}`);
  return (
    <Panel
      title={`Trades (${int(total)})`}
      pad={false}
      actions={
        data && data.total > PAGE ? (
          <div className="flex items-center gap-2 text-xs text-fg-muted">
            <span className="num">
              {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
            </span>
            <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              Previous
            </Button>
            <Button size="sm" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
              Next
            </Button>
          </div>
        ) : null
      }
    >
      {error ? (
        <div className="p-4">
          <ErrorState error={error} onRetry={reload} />
        </div>
      ) : !data ? (
        <div className="p-4">
          <LoadingBlock />
        </div>
      ) : data.items.length === 0 ? (
        <p className="p-4 text-[13px] text-fg-muted">No trades. The entry rules never triggered on this data, or every signal fell inside the warm-up period.</p>
      ) : (
        <Table head={["#", "Side", "Entry", "Exit", "Entry price", "Exit price", "Qty", "Net P&L", "Return", "R", "Costs", "Exit reason"]}>
          {data.items.map((t) => (
            <tr key={t.sequence}>
              <td className="num text-fg-faint">{t.sequence}</td>
              <td>
                <Badge tone={t.side === "long" ? "positive" : "negative"}>{t.side}</Badge>
              </td>
              <td className="whitespace-nowrap text-fg-muted">{dt(t.entry_time)}</td>
              <td className="whitespace-nowrap text-fg-muted">{dt(t.exit_time)}</td>
              <td className="num">{price(t.entry_price)}</td>
              <td className="num">{price(t.exit_price)}</td>
              <td className="num">{qty(t.quantity)}</td>
              <td>
                <Value v={t.net_pnl} text={money(t.net_pnl, true)} />
              </td>
              <td>
                <Value v={t.meta.return_pct} text={pct(t.meta.return_pct, 2, true)} />
              </td>
              <td className="num">{t.meta.r_multiple !== null && t.meta.r_multiple !== undefined ? t.meta.r_multiple.toFixed(2) : "n/a"}</td>
              <td className="num text-fg-muted" title={`fees ${money(t.fees)} · slippage ${money(t.slippage_cost)}`}>
                {money(t.fees + t.slippage_cost)}
              </td>
              <td className="text-fg-muted">{t.exit_reason.replaceAll("_", " ")}</td>
            </tr>
          ))}
        </Table>
      )}
      <p className="border-t border-line px-4 py-2 text-xs text-fg-faint">
        Times are candle open times in UTC. Entries fill at the next candle&apos;s open. See <Link href="/strategies" className="underline">Strategy Lab</Link> for the rules.
      </p>
    </Panel>
  );
}
