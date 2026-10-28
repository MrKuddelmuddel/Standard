"use client";

import { useParams } from "next/navigation";
import { Suspense, useState } from "react";

import { SeriesChart } from "@/components/charts";
import { Badge, Button, ErrorState, Input, IssueList, KV, LoadingBlock, Notice, PageHeader, Panel, Stat, StatusBadge, SyntheticBadge, Table, Value } from "@/components/ui";
import { post } from "@/lib/api";
import { dt, int, money, pct, price, qty } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { PaperDetail } from "@/lib/types";

export default function PaperSessionPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <SessionDetail />
    </Suspense>
  );
}

function SessionDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: s, error, loading, reload, setData } = useApi<PaperDetail>(`/paper/sessions/${id}`, { pollMs: 3000, shouldPoll: (x) => x?.status === "running" && !!x.config_json.auto_advance });
  const [bars, setBars] = useState("24");
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [lastStep, setLastStep] = useState<string | null>(null);

  if (loading && !s) return <LoadingBlock rows={6} />;
  if (error || !s) return <ErrorState error={error} onRetry={reload} />;

  async function act(name: string, fn: () => Promise<void>) {
    setBusy(name);
    setActionError(null);
    try {
      await fn();
      await reload();
    } catch (e) {
      setActionError(e);
      await reload();
    } finally {
      setBusy(null);
    }
  }
  const transition = (action: string) => act(action, async () => void (await post(`/paper/sessions/${id}/${action}`)));
  const ret = s.equity / s.initial_capital - 1;
  const done = s.status === "stopped" || s.status === "completed";

  return (
    <>
      <PageHeader
        title={s.name}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={s.status} />
            <Badge tone="info">historical replay</Badge>
            <SyntheticBadge show={s.is_synthetic_data} />
            <span>Simulation only. No real orders.</span>
          </span>
        }
        actions={
          <>
            {(s.status === "created" || s.status === "paused") && (
              <Button size="sm" variant="primary" loading={busy === "start" || busy === "resume"} onClick={() => void transition(s.status === "created" ? "start" : "resume")}>
                {s.status === "created" ? "Start" : "Resume"}
              </Button>
            )}
            {s.status === "running" && (
              <Button size="sm" loading={busy === "pause"} onClick={() => void transition("pause")}>
                Pause
              </Button>
            )}
            {!done && (
              <Button
                size="sm"
                variant="danger"
                loading={busy === "stop"}
                onClick={() => {
                  if (window.confirm("Stop this session? It cannot be restarted.")) void transition("stop");
                }}
              >
                Stop
              </Button>
            )}
          </>
        }
      />
      <IssueList error={actionError} />
      {s.status === "running" && (
        <Panel className="mb-4">
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs text-fg-muted">
              Candles to process
              <Input type="number" min={1} max={2000} className="w-28" value={bars} onChange={(e) => setBars(e.target.value)} />
            </label>
            <Button
              variant="primary"
              loading={busy === "advance"}
              onClick={() =>
                void act("advance", async () => {
                  const r = await post<{ processed: number; new_orders: number; new_fills: number; session: PaperDetail }>(`/paper/sessions/${id}/advance`, { bars: Number(bars) });
                  setLastStep(`Processed ${r.processed} candles · ${r.new_orders} new orders · ${r.new_fills} new fills.`);
                  setData({ ...s, ...r.session });
                })
              }
            >
              Advance
            </Button>
            {s.config_json.auto_advance && <span className="text-xs text-fg-faint">Auto-advance is on: the worker also steps this session in the background.</span>}
          </div>
          {lastStep && <p className="mt-2 text-xs text-fg-muted">{lastStep}</p>}
        </Panel>
      )}
      {s.status === "completed" && <Notice tone="positive">Replay reached the end of the stored data.</Notice>}

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Equity" value={<span className="num">{money(s.equity)}</span>} />
        <Stat label="Return" value={<Value v={ret} text={pct(ret, 2, true)} />} />
        <Stat label="Progress" value={<span className="num">{s.progress ? `${int(s.progress.processed)} / ${int(s.progress.total)}` : "n/a"}</span>} />
        <Stat label="Replay time" value={<span className="text-[13px]">{dt(s.current_time)}</span>} />
        <Stat label="Position" value={s.position ? <Badge tone={s.position.side === "long" ? "positive" : "negative"}>{s.position.side}</Badge> : <span className="text-fg-faint">flat</span>} />
        <Stat label="Unrealized P&L" value={s.position ? <Value v={s.position.unrealized_pnl} text={money(s.position.unrealized_pnl, true)} /> : <span className="text-fg-faint">n/a</span>} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.5fr_1fr]">
        <Panel title="Equity">
          <SeriesChart label="Equity" points={s.equity_curve} format={(v) => money(v)} baseline={s.initial_capital} />
        </Panel>
        <Panel title="Session">
          <KV
            items={[
              ["Initial capital", money(s.initial_capital)],
              ["Costs", `${s.config_json.fee_bps} bps fee + ${s.config_json.slippage_bps} bps slippage`],
              ["Position size", s.position ? qty(s.position.quantity) : "flat"],
              ["Entry price", s.position ? price(s.position.entry_price) : "n/a"],
              ["Stop / target", s.position ? `${price(s.position.stop)} / ${price(s.position.target)}` : "n/a"],
              ["Data fingerprint", <code key="f" className="text-xs">{s.data_fingerprint.slice(0, 16)}</code>],
              ["Created", dt(s.created_at)],
            ]}
          />
          {s.config_json.mode_note && <p className="mt-3 text-xs text-fg-faint">{s.config_json.mode_note}</p>}
        </Panel>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Panel title={`Orders (${s.orders.length})`} pad={false}>
          {s.orders.length === 0 ? (
            <p className="p-4 text-[13px] text-fg-muted">No orders yet.</p>
          ) : (
            <Table head={["Candle", "Side", "Intent", "Qty", "Status", "Reason"]}>
              {s.orders.map((o) => (
                <tr key={o.id}>
                  <td className="whitespace-nowrap text-fg-muted">{dt(o.bar_time)}</td>
                  <td>{o.side}</td>
                  <td>{o.intent}</td>
                  <td className="num">{qty(o.quantity)}</td>
                  <td>
                    <StatusBadge status={o.status} />
                  </td>
                  <td className="text-fg-muted">{o.reason?.replaceAll("_", " ") ?? ""}</td>
                </tr>
              ))}
            </Table>
          )}
        </Panel>
        <Panel title={`Fills (${s.fills.length})`} pad={false}>
          {s.fills.length === 0 ? (
            <p className="p-4 text-[13px] text-fg-muted">No fills yet.</p>
          ) : (
            <Table head={["Candle", "Price", "Reference", "Qty", "Fee"]}>
              {s.fills.map((f) => (
                <tr key={f.id}>
                  <td className="whitespace-nowrap text-fg-muted">{dt(f.bar_time)}</td>
                  <td className="num">{price(f.price)}</td>
                  <td className="num text-fg-muted">{price(f.ref_price)}</td>
                  <td className="num">{qty(f.quantity)}</td>
                  <td className="num">{money(f.fee)}</td>
                </tr>
              ))}
            </Table>
          )}
        </Panel>
      </div>
      {s.audit.length > 0 && (
        <Panel title="Audit log" className="mt-4" pad={false}>
          <Table head={["Event", "Time"]}>
            {s.audit.map((a, i) => (
              <tr key={i}>
                <td>{a.action}</td>
                <td className="text-fg-muted">{dt(a.created_at)}</td>
              </tr>
            ))}
          </Table>
        </Panel>
      )}
    </>
  );
}
