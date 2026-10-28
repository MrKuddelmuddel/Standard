"use client";

import { useRef, useState } from "react";

import { Badge, Button, Checkbox, EmptyState, ErrorState, Field, Input, IssueList, LoadingBlock, Notice, PageHeader, Panel, Select, Stat, Table, Textarea, Value } from "@/components/ui";
import { del, post, put } from "@/lib/api";
import { dt, int, money, num, pct, price, qty } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { JournalStats, JournalTrade, Page, Strategy } from "@/lib/types";

type ListResponse = Page<JournalTrade> & { stats: JournalStats };
type Preview = {
  headers: string[];
  mapping: Record<string, string>;
  missing_required: string[];
  secret_columns_ignored: string[];
  rows: { line: number; errors: string[]; duplicate: boolean; data: Record<string, unknown> | null }[];
  valid: number;
  invalid: number;
  duplicates: number;
  fields: string[];
  required: string[];
};

const PAGE = 50;

export default function JournalPage() {
  const [filters, setFilters] = useState({ symbol: "", side: "", source_type: "", tag: "", q: "" });
  const [applied, setApplied] = useState(filters);
  const [offset, setOffset] = useState(0);
  const [mode, setMode] = useState<"none" | "add" | "import">("none");
  const [editing, setEditing] = useState<JournalTrade | null>(null);
  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  for (const [k, v] of Object.entries(applied)) if (v) params.set(k, v);
  const { data, error, loading, reload } = useApi<ListResponse>(`/journal/trades?${params}`);
  const st = data?.stats;

  return (
    <>
      <PageHeader
        title="Journal"
        subtitle="Your own trades: manual entries, CSV imports and TradingView alerts. Statistics only use trades with a known P&L."
        actions={
          <>
            <Button onClick={() => setMode(mode === "import" ? "none" : "import")}>Import CSV</Button>
            <Button
              variant="primary"
              onClick={() => {
                setEditing(null);
                setMode(mode === "add" ? "none" : "add");
              }}
            >
              Add trade
            </Button>
          </>
        }
      />
      {mode === "add" && (
        <TradeForm
          key={editing?.id ?? "new"}
          trade={editing}
          onDone={() => {
            setMode("none");
            setEditing(null);
            void reload();
          }}
        />
      )}
      {mode === "import" && (
        <ImportPanel
          onDone={() => {
            setMode("none");
            void reload();
          }}
        />
      )}

      {st && (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          <Stat label="Trades" value={int(st.trades)} sub={`${int(st.closed_with_pnl)} with P&L`} />
          <Stat label="Net P&L" value={<Value v={st.net_pnl} text={money(st.net_pnl, true)} />} />
          <Stat label="Win rate" value={pct(st.win_rate)} />
          <Stat label="Profit factor" value={num(st.profit_factor)} />
          <Stat label="Expectancy" value={<Value v={st.expectancy} text={money(st.expectancy, true)} />} />
          <Stat label="Avg win" value={money(st.avg_win)} />
          <Stat label="Avg loss" value={money(st.avg_loss)} />
        </div>
      )}
      {st?.note && <p className="-mt-2 mb-4 text-xs text-fg-faint">{st.note}</p>}

      <Panel
        pad={false}
        title={
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              setOffset(0);
              setApplied(filters);
            }}
          >
            <Input aria-label="Symbol" placeholder="Symbol" className="h-7 w-28 text-xs" value={filters.symbol} onChange={(e) => setFilters({ ...filters, symbol: e.target.value.toUpperCase() })} />
            <Select
              aria-label="Side"
              className="h-7 w-24 text-xs"
              value={filters.side}
              onChange={(e) => setFilters({ ...filters, side: e.target.value })}
              options={[
                { value: "", label: "Any side" },
                { value: "long", label: "Long" },
                { value: "short", label: "Short" },
              ]}
            />
            <Select
              aria-label="Source"
              className="h-7 w-32 text-xs"
              value={filters.source_type}
              onChange={(e) => setFilters({ ...filters, source_type: e.target.value })}
              options={[
                { value: "", label: "Any source" },
                { value: "manual", label: "Manual" },
                { value: "csv", label: "CSV" },
                { value: "tradingview", label: "TradingView" },
              ]}
            />
            <Input aria-label="Tag" placeholder="Tag" className="h-7 w-24 text-xs" value={filters.tag} onChange={(e) => setFilters({ ...filters, tag: e.target.value })} />
            <Input aria-label="Search notes" placeholder="Search notes / setup" className="h-7 w-44 text-xs" value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
            <Button size="sm" type="submit">
              Filter
            </Button>
          </form>
        }
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
        {loading && !data ? (
          <div className="p-4">
            <LoadingBlock />
          </div>
        ) : error ? (
          <div className="p-4">
            <ErrorState error={error} onRetry={reload} />
          </div>
        ) : data && data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No trades in your journal" action={<Button variant="primary" onClick={() => setMode("add")}>Add your first trade</Button>}>
              Record trades by hand, import an exchange CSV, or connect TradingView alerts in Settings.
            </EmptyState>
          </div>
        ) : data ? (
          <Table head={["Entry", "Symbol", "Side", "Qty", "Entry price", "Exit price", "P&L", "Setup / tags", "Source", ""]}>
            {data.items.map((t) => (
              <tr key={t.id}>
                <td className="whitespace-nowrap text-fg-muted">{dt(t.entry_time)}</td>
                <td className="font-medium">{t.symbol}</td>
                <td>
                  <Badge tone={t.side === "long" ? "positive" : "negative"}>{t.side}</Badge>
                </td>
                <td className="num">{qty(t.quantity)}</td>
                <td className="num">{price(t.entry_price)}</td>
                <td className="num">{t.exit_price !== null ? price(t.exit_price) : <span className="text-fg-faint">open</span>}</td>
                <td title={t.pnl_is_computed ? "Computed from prices, quantity and fees" : undefined}>
                  <Value v={t.realized_pnl} text={money(t.realized_pnl, true)} />
                  {t.pnl_is_computed && <span className="ml-1 text-[10px] text-fg-faint">calc</span>}
                </td>
                <td className="max-w-56 truncate text-fg-muted" title={t.notes}>
                  {t.setup}
                  {t.tags.map((g) => (
                    <Badge key={g}>{g}</Badge>
                  ))}
                </td>
                <td>
                  <Badge>{t.source_type}</Badge>
                </td>
                <td className="whitespace-nowrap text-right">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setEditing(t);
                      setMode("add");
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                  >
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      if (!window.confirm(`Delete ${t.symbol} ${t.side} from ${dt(t.entry_time)}?`)) return;
                      await del(`/journal/trades/${t.id}`);
                      void reload();
                    }}
                  >
                    Delete
                  </Button>
                </td>
              </tr>
            ))}
          </Table>
        ) : null}
      </Panel>
    </>
  );
}

const toLocalInput = (iso: string | null) => (iso ? new Date(iso).toISOString().slice(0, 16) : "");
const fromLocalInput = (v: string) => (v ? `${v}:00Z` : null);

function TradeForm({ trade, onDone }: { trade: JournalTrade | null; onDone: () => void }) {
  const { data: strategies } = useApi<Page<Strategy>>("/strategies?limit=100");
  const [f, setF] = useState({
    symbol: trade?.symbol ?? "BTCUSDT",
    market_type: trade?.market_type ?? "spot",
    side: trade?.side ?? "long",
    entry_time: toLocalInput(trade?.entry_time ?? null),
    exit_time: toLocalInput(trade?.exit_time ?? null),
    entry_price: trade ? String(trade.entry_price) : "",
    exit_price: trade?.exit_price !== null && trade?.exit_price !== undefined ? String(trade.exit_price) : "",
    quantity: trade ? String(trade.quantity) : "",
    fees: trade ? String(trade.fees) : "0",
    realized_pnl: trade?.realized_pnl !== null && trade?.realized_pnl !== undefined && !trade.pnl_is_computed ? String(trade.realized_pnl) : "",
    strategy_id: trade?.strategy_id ?? "",
    setup: trade?.setup ?? "",
    tags: trade?.tags.join(", ") ?? "",
    notes: trade?.notes ?? "",
    emotions: trade?.emotions ?? "",
    rule_compliance: trade?.rule_compliance ?? null,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = {
      symbol: f.symbol.trim().toUpperCase(),
      market_type: f.market_type,
      side: f.side,
      entry_time: fromLocalInput(f.entry_time),
      exit_time: fromLocalInput(f.exit_time),
      entry_price: Number(f.entry_price),
      exit_price: f.exit_price ? Number(f.exit_price) : null,
      quantity: Number(f.quantity),
      fees: Number(f.fees || 0),
      realized_pnl: f.realized_pnl ? Number(f.realized_pnl) : null,
      strategy_id: f.strategy_id || null,
      setup: f.setup,
      tags: f.tags
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
      notes: f.notes,
      emotions: f.emotions || null,
      rule_compliance: f.rule_compliance,
    };
    try {
      if (trade) await put(`/journal/trades/${trade.id}`, body);
      else await post("/journal/trades", body);
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title={trade ? "Edit trade" : "Add trade"} className="mb-4">
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Symbol">{(id) => <Input id={id} required value={f.symbol} onChange={set("symbol")} />}</Field>
          <Field label="Market">
            {(id) => (
              <Select
                id={id}
                value={f.market_type}
                onChange={set("market_type")}
                options={[
                  { value: "spot", label: "Spot" },
                  { value: "futures", label: "Futures" },
                ]}
              />
            )}
          </Field>
          <Field label="Side">
            {(id) => (
              <Select
                id={id}
                value={f.side}
                onChange={set("side")}
                options={[
                  { value: "long", label: "Long" },
                  { value: "short", label: "Short" },
                ]}
              />
            )}
          </Field>
          <Field label="Strategy (optional)">
            {(id) => <Select id={id} value={f.strategy_id} onChange={set("strategy_id")} options={[{ value: "", label: "None" }, ...(strategies?.items ?? []).map((s) => ({ value: s.id, label: s.name }))]} />}
          </Field>
          <Field label="Entry time (UTC)">{(id) => <Input id={id} type="datetime-local" required value={f.entry_time} onChange={set("entry_time")} />}</Field>
          <Field label="Entry price">{(id) => <Input id={id} type="number" step="any" min={0} required value={f.entry_price} onChange={set("entry_price")} />}</Field>
          <Field label="Quantity">{(id) => <Input id={id} type="number" step="any" min={0} required value={f.quantity} onChange={set("quantity")} />}</Field>
          <Field label="Fees">{(id) => <Input id={id} type="number" step="any" min={0} value={f.fees} onChange={set("fees")} />}</Field>
          <Field label="Exit time (UTC, optional)">{(id) => <Input id={id} type="datetime-local" value={f.exit_time} onChange={set("exit_time")} />}</Field>
          <Field label="Exit price (optional)">{(id) => <Input id={id} type="number" step="any" min={0} value={f.exit_price} onChange={set("exit_price")} />}</Field>
          <Field label="Realized P&L (optional)" hint="Empty: computed from prices, quantity and fees.">
            {(id) => <Input id={id} type="number" step="any" value={f.realized_pnl} onChange={set("realized_pnl")} />}
          </Field>
          <Field label="Followed my rules?">
            {(id) => (
              <Select
                id={id}
                value={f.rule_compliance === null ? "" : String(f.rule_compliance)}
                onChange={(e) => setF({ ...f, rule_compliance: e.target.value === "" ? null : e.target.value === "true" })}
                options={[
                  { value: "", label: "Not recorded" },
                  { value: "true", label: "Yes" },
                  { value: "false", label: "No" },
                ]}
              />
            )}
          </Field>
          <Field label="Setup">{(id) => <Input id={id} value={f.setup} maxLength={120} onChange={set("setup")} />}</Field>
          <Field label="Tags (comma separated)">{(id) => <Input id={id} value={f.tags} onChange={set("tags")} />}</Field>
          <Field label="Emotions">{(id) => <Input id={id} value={f.emotions} maxLength={120} onChange={set("emotions")} />}</Field>
          <Field label="Notes" className="sm:col-span-2 lg:col-span-4">
            {(id) => <Textarea id={id} className="min-h-16" value={f.notes} maxLength={5000} onChange={set("notes")} />}
          </Field>
        </div>
        <IssueList error={error} />
        <div className="flex gap-2">
          <Button type="submit" variant="primary" loading={busy}>
            {trade ? "Save changes" : "Add trade"}
          </Button>
          <Button onClick={onDone}>Cancel</Button>
        </div>
      </form>
    </Panel>
  );
}

function ImportPanel({ onDone }: { onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<{ name: string; content: string } | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [skipDup, setSkipDup] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [result, setResult] = useState<{ imported: number; skipped: number; errors: unknown[] } | null>(null);

  async function load(content: string, name: string, map?: Record<string, string>) {
    setBusy(true);
    setError(null);
    try {
      const p = await post<Preview>("/journal/imports/preview", { filename: name, content, mapping: map ?? null });
      setPreview(p);
      setMapping(p.mapping);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await post("/journal/imports", { filename: file.name, content: file.content, mapping, skip_duplicates: skipDup }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Import trades from CSV" className="mb-4">
      <div className="space-y-3">
        <p className="text-xs text-fg-muted">
          Needs columns for symbol, side, entry time, entry price and quantity. Common exchange headers are detected automatically. Columns that look like API keys or secrets are ignored and never stored.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          aria-label="CSV file"
          className="block text-xs text-fg-muted file:mr-3 file:rounded-md file:border file:border-line-strong file:bg-raised file:px-3 file:py-1.5 file:text-fg"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            const content = await f.text();
            setFile({ name: f.name, content });
            setResult(null);
            void load(content, f.name);
          }}
        />
        <IssueList error={error} />
        {result ? (
          <>
            <Notice tone="positive" title="Import finished">
              Imported {result.imported}, skipped {result.skipped}
              {result.errors.length > 0 && `, ${result.errors.length} rows with errors`}.
            </Notice>
            <Button onClick={onDone}>Close</Button>
          </>
        ) : preview && file ? (
          <>
            {preview.secret_columns_ignored.length > 0 && <Notice tone="warning">Ignored sensitive-looking columns: {preview.secret_columns_ignored.join(", ")}</Notice>}
            <div>
              <div className="mb-2 text-xs font-medium text-fg-muted">Column mapping</div>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {preview.fields.map((field) => (
                  <Field key={field} label={`${field}${preview.required.includes(field) ? " *" : ""}`}>
                    {(id) => (
                      <Select
                        id={id}
                        value={mapping[field] ?? ""}
                        onChange={(e) => {
                          const next = { ...mapping };
                          if (e.target.value) next[field] = e.target.value;
                          else delete next[field];
                          setMapping(next);
                        }}
                        options={[{ value: "", label: "—" }, ...preview.headers.map((h) => ({ value: h, label: h }))]}
                      />
                    )}
                  </Field>
                ))}
              </div>
              <Button size="sm" className="mt-2" onClick={() => void load(file.content, file.name, mapping)} loading={busy}>
                Re-check with this mapping
              </Button>
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <Badge tone="positive">{preview.valid} valid</Badge>
              <Badge tone={preview.invalid ? "negative" : "neutral"}>{preview.invalid} invalid</Badge>
              <Badge tone={preview.duplicates ? "warning" : "neutral"}>{preview.duplicates} duplicates</Badge>
            </div>
            <Table head={["Line", "Symbol", "Side", "Entry time", "Entry", "Qty", "Exit", "P&L", "Status"]}>
              {preview.rows.slice(0, 20).map((r) => (
                <tr key={r.line}>
                  <td className="num text-fg-faint">{r.line}</td>
                  <td>{String(r.data?.symbol ?? "")}</td>
                  <td>{String(r.data?.side ?? "")}</td>
                  <td className="text-fg-muted">{r.data?.entry_time ? dt(String(r.data.entry_time)) : ""}</td>
                  <td className="num">{r.data ? price(r.data.entry_price) : ""}</td>
                  <td className="num">{r.data ? qty(r.data.quantity) : ""}</td>
                  <td className="num">{r.data?.exit_price ? price(r.data.exit_price) : ""}</td>
                  <td className="num">{r.data?.realized_pnl !== undefined && r.data?.realized_pnl !== null ? money(r.data.realized_pnl) : ""}</td>
                  <td>{r.errors.length ? <span className="text-xs text-negative">{r.errors.join("; ")}</span> : r.duplicate ? <Badge tone="warning">duplicate</Badge> : <Badge tone="positive">ok</Badge>}</td>
                </tr>
              ))}
            </Table>
            {preview.rows.length > 20 && <p className="text-xs text-fg-faint">Showing 20 of {preview.rows.length} rows.</p>}
            <Checkbox label="Skip duplicates" checked={skipDup} onChange={setSkipDup} />
            <div className="flex gap-2">
              <Button variant="primary" onClick={() => void commit()} loading={busy} disabled={preview.valid === 0 || preview.missing_required.length > 0}>
                Import {preview.valid} trades
              </Button>
              <Button onClick={onDone}>Cancel</Button>
            </div>
          </>
        ) : busy ? (
          <LoadingBlock rows={2} />
        ) : null}
      </div>
    </Panel>
  );
}
