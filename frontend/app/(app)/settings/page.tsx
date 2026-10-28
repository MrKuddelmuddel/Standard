"use client";

import { useState } from "react";

import { useAuth } from "@/components/auth";
import { Candles } from "@/components/charts";
import { Badge, Button, ErrorState, Field, Input, IssueList, KV, LoadingBlock, Notice, PageHeader, Panel, Select, SyntheticBadge, Table } from "@/components/ui";
import { api, patch, post } from "@/lib/api";
import { date, dt, formatJson, int } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Page, Source } from "@/lib/types";

const SYMBOLS = ["BTCUSDT", "ETHUSDT"].map((v) => ({ value: v, label: v }));
const TIMEFRAMES = ["15m", "1h", "4h", "1d"].map((v) => ({ value: v, label: v }));

export default function SettingsPage() {
  return (
    <>
      <PageHeader title="Settings" subtitle="Market data, defaults, TradingView alerts and your account." />
      <div className="space-y-4">
        <MarketData />
        <TradingView />
        <div className="grid gap-4 xl:grid-cols-2">
          <Preferences />
          <Account />
        </div>
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- market data */
function MarketData() {
  const { data: sources, error, loading, reload } = useApi<Source[]>("/market-data/sources");
  const [mode, setMode] = useState<"demo" | "csv" | "fetch">("demo");
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [bars, setBars] = useState("8000");
  const [seed, setSeed] = useState("7");
  const [file, setFile] = useState<File | null>(null);
  const [start, setStart] = useState("2024-01-01");
  const [end, setEnd] = useState("2024-12-31");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      if (mode === "demo") {
        const s = await post<Source>("/market-data/demo", { symbol, timeframe, bars: Number(bars), seed: Number(seed) });
        setMsg(`Created synthetic ${s.symbol} ${s.timeframe} data: ${int(s.row_count)} candles.`);
      } else if (mode === "csv") {
        if (!file) throw new Error("Choose a CSV file first.");
        const fd = new FormData();
        fd.set("symbol", symbol);
        fd.set("timeframe", timeframe);
        fd.set("file", file);
        const r = await api<{ source: Source; import: Record<string, unknown> }>("/market-data/import-csv", { method: "POST", body: fd });
        setMsg(`Imported into ${r.source.symbol} ${r.source.timeframe} (revision ${r.source.revision}): ${formatSummary(r.import)}`);
      } else {
        const r = await post<{ source: Source; import: Record<string, unknown> }>("/market-data/fetch", { symbol, timeframe, start: `${start}T00:00:00Z`, end: `${end}T00:00:00Z` });
        setMsg(`Fetched ${r.source.symbol} ${r.source.timeframe}: ${formatSummary(r.import)}`);
      }
      await reload();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section id="market-data" className="scroll-mt-16">
      <Panel title="Market data">
        <div className="grid gap-5 xl:grid-cols-[1fr_1.4fr]">
          <div className="space-y-3">
            <div role="radiogroup" aria-label="Data source type" className="flex flex-wrap gap-1.5">
              {(
                [
                  ["demo", "Synthetic demo"],
                  ["csv", "CSV upload"],
                  ["fetch", "Binance public API"],
                ] as const
              ).map(([v, l]) => (
                <Button key={v} size="sm" variant={mode === v ? "primary" : "secondary"} role="radio" aria-checked={mode === v} onClick={() => setMode(v)}>
                  {l}
                </Button>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Symbol">{(id) => <Select id={id} value={symbol} options={SYMBOLS} onChange={(e) => setSymbol(e.target.value)} />}</Field>
              <Field label="Timeframe">{(id) => <Select id={id} value={timeframe} options={TIMEFRAMES} onChange={(e) => setTimeframe(e.target.value)} />}</Field>
              {mode === "demo" && (
                <>
                  <Field label="Candles" hint="500 – 50,000">
                    {(id) => <Input id={id} type="number" min={500} max={50000} value={bars} onChange={(e) => setBars(e.target.value)} />}
                  </Field>
                  <Field label="Seed" hint="Same seed, same data.">
                    {(id) => <Input id={id} type="number" value={seed} onChange={(e) => setSeed(e.target.value)} />}
                  </Field>
                </>
              )}
              {mode === "csv" && (
                <Field label="CSV file" className="sm:col-span-2" hint="Columns: timestamp or open_time (UTC, ms/s/ISO), open, high, low, close, volume. Re-importing merges and bumps the revision.">
                  {(id) => (
                    <input
                      id={id}
                      type="file"
                      accept=".csv,text/csv"
                      className="block text-xs text-fg-muted file:mr-3 file:rounded-md file:border file:border-line-strong file:bg-raised file:px-3 file:py-1.5 file:text-fg"
                      onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    />
                  )}
                </Field>
              )}
              {mode === "fetch" && (
                <>
                  <Field label="Start (UTC)">{(id) => <Input id={id} type="date" value={start} onChange={(e) => setStart(e.target.value)} />}</Field>
                  <Field label="End (UTC)">{(id) => <Input id={id} type="date" value={end} onChange={(e) => setEnd(e.target.value)} />}</Field>
                </>
              )}
            </div>
            {mode === "demo" && <Notice tone="warning">Synthetic data is a random walk. It is labelled everywhere and is only good for trying the software, not for judging a strategy.</Notice>}
            {mode === "fetch" && <Notice tone="info">Needs outbound network access from the server to api.binance.com, which may be blocked or geo-restricted. No API key is used.</Notice>}
            <IssueList error={err} />
            {msg && <Notice tone="positive">{msg}</Notice>}
            <Button variant="primary" onClick={() => void submit()} loading={busy}>
              {mode === "demo" ? "Generate demo data" : mode === "csv" ? "Import CSV" : "Fetch candles"}
            </Button>
          </div>
          <div>
            {loading && !sources ? (
              <LoadingBlock />
            ) : error ? (
              <ErrorState error={error} onRetry={reload} />
            ) : !sources || sources.length === 0 ? (
              <p className="text-[13px] text-fg-muted">No data sources yet.</p>
            ) : (
              <Table head={["Market", "Provider", "Candles", "Range", "Rev.", "Gaps", ""]}>
                {sources.map((s) => (
                  <tr key={s.id}>
                    <td className="font-medium">
                      {s.symbol} {s.timeframe} <SyntheticBadge show={s.is_synthetic} />
                    </td>
                    <td className="text-fg-muted">{s.provider}</td>
                    <td className="num">{int(s.row_count)}</td>
                    <td className="whitespace-nowrap text-fg-muted">
                      {date(s.first_time)} – {date(s.last_time)}
                    </td>
                    <td className="num">r{s.revision}</td>
                    <td>{(s.meta.gap_count ?? 0) > 0 ? <Badge tone="warning">{s.meta.gap_count}</Badge> : <span className="text-fg-faint">0</span>}</td>
                    <td>
                      <Button size="sm" variant="ghost" onClick={() => setPreview(preview === s.id ? null : s.id)}>
                        {preview === s.id ? "Hide" : "Preview"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </Table>
            )}
            {preview && <CandlePreview id={preview} />}
          </div>
        </div>
      </Panel>
    </section>
  );
}

function formatSummary(s: Record<string, unknown>): string {
  return Object.entries(s)
    .filter(([, v]) => typeof v === "number" || typeof v === "string")
    .map(([k, v]) => `${k.replaceAll("_", " ")} ${typeof v === "number" ? int(v) : v}`)
    .join(" · ");
}

function CandlePreview({ id }: { id: string }) {
  const { data, error } = useApi<{ rows: number[][]; is_synthetic: boolean }>(`/market-data/sources/${id}/candles?limit=200`);
  if (error) return <ErrorState error={error} />;
  if (!data) return <LoadingBlock rows={2} />;
  return (
    <div className="mt-3 rounded-md border border-line bg-panel-2 p-2">
      <div className="mb-1 flex items-center justify-between text-xs text-fg-faint">
        <span>Last {data.rows.length} candles</span>
        <SyntheticBadge show={data.is_synthetic} />
      </div>
      <Candles rows={data.rows} />
    </div>
  );
}

/* ---------------------------------------------------------------- TradingView */
type Alert = { id: string; event_id: string; symbol: string; action: string; price: number | null; alert_time: string | null; status: string; journal_trade_id: string | null; received_at: string };
type AlertsResponse = Page<Alert> & { token: { active: boolean; hint: string | null; last_used_at: string | null }; example_payload: Record<string, string> };

function TradingView() {
  const { data, error, loading, reload } = useApi<AlertsResponse>("/tradingview/alerts?limit=25");
  const [secret, setSecret] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [qtyFor, setQtyFor] = useState<Record<string, string>>({});
  const webhookUrl = typeof window !== "undefined" ? `${window.location.origin}/api/v1/tradingview/webhook` : "/api/v1/tradingview/webhook";

  async function rotate() {
    if (data?.token.active && !window.confirm("Create a new secret? The old one stops working immediately.")) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await post<{ secret: string }>("/tradingview/token");
      setSecret(r.secret);
      await reload();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  async function toJournal(a: Alert) {
    setErr(null);
    try {
      await post(`/tradingview/alerts/${a.id}/journal`, { quantity: Number(qtyFor[a.id] || 0) });
      await reload();
    } catch (e) {
      setErr(e);
    }
  }

  return (
    <Panel title="TradingView alerts">
      {loading && !data ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : data ? (
        <div className="grid gap-5 xl:grid-cols-[1fr_1.4fr]">
          <div className="space-y-3 text-[13px]">
            <p className="text-fg-muted">Alerts are stored and can be turned into journal entries. They never trigger orders.</p>
            <KV
              items={[
                ["Webhook URL", <code key="u" className="text-xs">{webhookUrl}</code>],
                ["Secret", data.token.active ? `active (…${data.token.hint})` : "not created"],
                ["Last used", data.token.last_used_at ? dt(data.token.last_used_at) : "never"],
              ]}
            />
            {secret && (
              <Notice tone="warning" title="Copy this secret now. It is shown once.">
                <code className="break-all text-xs text-fg">{secret}</code>
              </Notice>
            )}
            <IssueList error={err} />
            <Button onClick={() => void rotate()} loading={busy}>
              {data.token.active ? "Rotate secret" : "Create secret"}
            </Button>
            <div>
              <div className="mb-1 text-xs font-medium text-fg-muted">Alert message (JSON)</div>
              <pre className="overflow-auto rounded-md bg-panel-2 p-3 text-xs">{formatJson(data.example_payload)}</pre>
              <p className="mt-1 text-xs text-fg-faint">TradingView needs a publicly reachable HTTPS URL. event_id must be unique; repeats are ignored. Alerts older than 10 minutes are rejected.</p>
            </div>
          </div>
          <div>
            {data.items.length === 0 ? (
              <p className="text-[13px] text-fg-muted">No alerts received yet.</p>
            ) : (
              <Table head={["Received", "Symbol", "Action", "Price", "Status", "Journal"]}>
                {data.items.map((a) => (
                  <tr key={a.id}>
                    <td className="whitespace-nowrap text-fg-muted">{dt(a.received_at)}</td>
                    <td>{a.symbol}</td>
                    <td>{a.action}</td>
                    <td className="num">{a.price ?? "n/a"}</td>
                    <td>
                      <Badge tone={a.status === "accepted" || a.status === "linked" ? "positive" : "neutral"}>{a.status}</Badge>
                    </td>
                    <td>
                      {a.journal_trade_id ? (
                        <Badge tone="positive">linked</Badge>
                      ) : a.price ? (
                        <div className="flex items-center gap-1">
                          <Input aria-label="Quantity" type="number" step="any" min={0} placeholder="Qty" className="h-7 w-20 text-xs" value={qtyFor[a.id] ?? ""} onChange={(e) => setQtyFor({ ...qtyFor, [a.id]: e.target.value })} />
                          <Button size="sm" disabled={!Number(qtyFor[a.id])} onClick={() => void toJournal(a)}>
                            Add
                          </Button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </Table>
            )}
          </div>
        </div>
      ) : null}
    </Panel>
  );
}

/* ---------------------------------------------------------------- preferences and account */
function Preferences() {
  const { user, refresh } = useAuth();
  const p = (user?.preferences ?? {}) as Record<string, number | string | undefined>;
  const [capital, setCapital] = useState(String(p.default_capital ?? 10000));
  const [fee, setFee] = useState(String(p.default_fee_bps ?? 10));
  const [slip, setSlip] = useState(String(p.default_slippage_bps ?? 5));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  async function save() {
    setBusy(true);
    setErr(null);
    setSaved(false);
    try {
      await patch("/auth/me/preferences", { default_capital: Number(capital), default_fee_bps: Number(fee), default_slippage_bps: Number(slip) });
      await refresh();
      setSaved(true);
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Defaults">
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Initial capital">{(id) => <Input id={id} type="number" min={1} value={capital} onChange={(e) => setCapital(e.target.value)} />}</Field>
        <Field label="Fee (bps)">{(id) => <Input id={id} type="number" min={0} step="0.5" value={fee} onChange={(e) => setFee(e.target.value)} />}</Field>
        <Field label="Slippage (bps)">{(id) => <Input id={id} type="number" min={0} step="0.5" value={slip} onChange={(e) => setSlip(e.target.value)} />}</Field>
      </div>
      <p className="mt-2 text-xs text-fg-faint">All times are shown in UTC to match exchange candles.</p>
      <IssueList error={err} />
      <div className="mt-3 flex items-center gap-3">
        <Button onClick={() => void save()} loading={busy}>
          Save defaults
        </Button>
        {saved && <span className="text-xs text-accent">Saved.</span>}
      </div>
    </Panel>
  );
}

function Account() {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  async function exportAll() {
    setBusy(true);
    setErr(null);
    try {
      const data = await api<Record<string, unknown>>("/auth/me/export");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([formatJson(data)], { type: "application/json" }));
      a.download = `nexus-quant-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Account">
      <KV
        items={[
          ["Email", user?.email],
          ["Member since", date(user?.created_at)],
          ["Live trading", "not available (simulation only)"],
          ["Exchange API keys", "not used or stored"],
        ]}
      />
      <IssueList error={err} />
      <Button className="mt-3" onClick={() => void exportAll()} loading={busy}>
        Export my data (JSON)
      </Button>
    </Panel>
  );
}
