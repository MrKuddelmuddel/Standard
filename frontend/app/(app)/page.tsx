"use client";

import Link from "next/link";

import { Badge, EmptyState, ErrorState, LinkButton, LoadingBlock, PageHeader, Panel, Stat, StatusBadge, SyntheticBadge, Table, Value } from "@/components/ui";
import { ago, date, int, pct } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Overview } from "@/lib/types";

export default function OverviewPage() {
  const { data, error, loading, reload } = useApi<Overview>("/overview", {
    pollMs: 5000,
    shouldPoll: (d) => !!d?.recent_discoveries.some((x) => x.status === "queued" || x.status === "running") || !!d?.recent_backtests.some((x) => x.status === "queued" || x.status === "running"),
  });

  return (
    <>
      <PageHeader
        title="Overview"
        subtitle="Your strategies, tests and data at a glance."
        actions={
          <>
            <LinkButton href="/strategies/new" variant="primary">
              New strategy
            </LinkButton>
            <LinkButton href="/discover">Run discovery</LinkButton>
          </>
        }
      />
      {loading && !data ? (
        <LoadingBlock rows={5} />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : data ? (
        <div className="space-y-5">
          {data.counts.data_sources === 0 && (
            <EmptyState title="Start with market data" action={<LinkButton href="/settings#market-data" variant="primary">Add market data</LinkButton>}>
              Backtests need candles. Upload a CSV, fetch from Binance if your server has network access, or generate clearly marked synthetic demo data.
            </EmptyState>
          )}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="Strategies" value={int(data.counts.strategies)} />
            <Stat label="Backtests" value={int(data.counts.backtests)} />
            <Stat label="Discovery jobs" value={int(data.counts.discoveries)} />
            <Stat label="Active paper sessions" value={int(data.counts.active_paper_sessions)} />
            <Stat label="Journal trades" value={int(data.counts.journal_trades)} sub={data.last_journal_activity ? `last ${ago(data.last_journal_activity)}` : "no entries yet"} />
            <Stat label="Data sources" value={int(data.counts.data_sources)} />
          </div>

          <div className="grid gap-5 xl:grid-cols-[1.4fr_1fr]">
            <Panel title="Recent backtests" actions={<LinkButton href="/strategies" size="sm" variant="ghost">All strategies</LinkButton>} pad={false}>
              {data.recent_backtests.length === 0 ? (
                <div className="p-4">
                  <EmptyState title="No backtests yet" action={<LinkButton href="/strategies/new" variant="primary">Create a strategy</LinkButton>}>
                    Create a strategy in Strategy Lab and run it against a data source.
                  </EmptyState>
                </div>
              ) : (
                <Table head={["Strategy", "Status", "Net return", "Trades", "Data", "Created"]}>
                  {data.recent_backtests.map((b) => (
                    <tr key={b.id}>
                      <td>
                        <Link href={`/backtests/${b.id}`} className="text-fg hover:text-accent">
                          {b.strategy ?? "Unknown"}
                        </Link>
                      </td>
                      <td>
                        <StatusBadge status={b.status} />
                      </td>
                      <td>
                        <Value v={b.net_return} text={pct(b.net_return, 2, true)} />
                      </td>
                      <td className="num">{int(b.trade_count)}</td>
                      <td>{b.is_synthetic_data ? <SyntheticBadge /> : <Badge>real</Badge>}</td>
                      <td className="text-fg-muted">{ago(b.created_at)}</td>
                    </tr>
                  ))}
                </Table>
              )}
            </Panel>

            <Panel title="Discovery jobs" actions={<LinkButton href="/discover" size="sm" variant="ghost">Open Discover</LinkButton>} pad={false}>
              {data.recent_discoveries.length === 0 ? (
                <p className="p-4 text-[13px] text-fg-muted">No discovery jobs yet.</p>
              ) : (
                <Table head={["Job", "Status", "Candidates", "Created"]}>
                  {data.recent_discoveries.map((d) => (
                    <tr key={d.id}>
                      <td>
                        <Link href={`/discover/${d.id}`} className="num text-fg hover:text-accent">
                          {d.id.slice(0, 8)}
                        </Link>
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

          <Panel title="System and data status" pad={false}>
            {data.data_status.length === 0 ? (
              <p className="p-4 text-[13px] text-fg-muted">No market data yet.</p>
            ) : (
              <Table head={["Symbol", "Timeframe", "Provider", "Candles", "Range", "Gaps", "Type"]}>
                {data.data_status.map((s) => (
                  <tr key={s.id}>
                    <td className="font-medium">{s.symbol}</td>
                    <td>{s.timeframe}</td>
                    <td className="text-fg-muted">{s.provider}</td>
                    <td className="num">{int(s.rows)}</td>
                    <td className="text-fg-muted">
                      {date(s.first_time)} – {date(s.last_time)}
                    </td>
                    <td>{s.gap_count > 0 ? <Badge tone="warning">{s.gap_count} gaps</Badge> : <span className="text-fg-faint">none</span>}</td>
                    <td>{s.is_synthetic ? <SyntheticBadge /> : <Badge>real</Badge>}</td>
                  </tr>
                ))}
              </Table>
            )}
            <div className="flex flex-wrap gap-3 border-t border-line px-4 py-2.5 text-xs text-fg-faint">
              <span>Live trading: disabled</span>
              <span>AI provider: {data.ai_configured ? "configured" : "not configured"}</span>
            </div>
          </Panel>
        </div>
      ) : null}
    </>
  );
}
