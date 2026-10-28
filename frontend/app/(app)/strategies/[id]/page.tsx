"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { RunBacktestForm, RunValidationForm } from "@/components/runs";
import { StrategyEditor } from "@/components/strategy-editor";
import { Badge, Button, EmptyState, ErrorState, Field, Hash, Input, IssueList, KV, LoadingBlock, PageHeader, Panel, Select, StatusBadge, SyntheticBadge, Table, Tabs, Value } from "@/components/ui";
import { ValidationView } from "@/components/validation-view";
import { api, post } from "@/lib/api";
import { ago, dt, formatJson, int, pct } from "@/lib/format";
import { isActive, useApi } from "@/lib/hooks";
import { describeCondition } from "@/lib/strategy";
import type { Strategy, StrategyDefinition, Validation, Version } from "@/lib/types";

type Tab = "overview" | "backtest" | "validation" | "logic" | "history";
type BacktestRow = { id: string; status: string; created_at: string; version_number: number | null; is_synthetic_data: boolean; metrics: Record<string, number | null> | null; error_message: string | null };

export default function StrategyPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <StrategyDetail />
    </Suspense>
  );
}

function StrategyDetail() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const initialTab = (search.get("tab") as Tab | null) ?? "overview";
  const [tab, setTab] = useState<Tab>(initialTab);
  const { data: s, error, loading, reload, setData } = useApi<Strategy>(`/strategies/${id}`);
  const [actionError, setActionError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);

  if (loading && !s) return <LoadingBlock rows={6} />;
  if (error || !s) return <ErrorState error={error} onRetry={reload} />;
  const v = s.current_version;
  const d = v?.definition_json;

  async function act(name: string, fn: () => Promise<void>) {
    setBusy(name);
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(null);
    }
  }

  async function exportJson() {
    const doc = await api<Record<string, unknown>>(`/strategies/${id}/export`);
    const blob = new Blob([formatJson(doc)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${s!.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}-v${v?.version_number ?? 1}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <>
      <PageHeader
        title={s.name}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={s.status} />
            <Badge>{s.origin}</Badge>
            {v && <span className="num">v{v.version_number}</span>}
            {d && (
              <span>
                {d.symbols.join(", ")} · {d.timeframe} · {d.market_type === "futures_sim" ? "futures (sim)" : "spot"} · {d.direction.replace("_", "/")}
              </span>
            )}
          </span>
        }
        actions={
          <>
            <Button size="sm" onClick={() => void act("export", exportJson)} loading={busy === "export"}>
              Export JSON
            </Button>
            <Button
              size="sm"
              loading={busy === "duplicate"}
              onClick={() =>
                void act("duplicate", async () => {
                  const c = await post<Strategy>(`/strategies/${id}/duplicate`);
                  router.push(`/strategies/${c.id}`);
                })
              }
            >
              Duplicate
            </Button>
            <Button
              size="sm"
              variant={s.status === "archived" ? "secondary" : "danger"}
              loading={busy === "archive"}
              onClick={() => void act("archive", async () => setData(await post<Strategy>(`/strategies/${id}/archive${s.status === "archived" ? "?restore=true" : ""}`)))}
            >
              {s.status === "archived" ? "Restore" : "Archive"}
            </Button>
          </>
        }
      />
      <IssueList error={actionError} />
      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "overview", label: "Overview" },
          { value: "backtest", label: "Backtest" },
          { value: "validation", label: "Validation" },
          { value: "logic", label: "Logic" },
          { value: "history", label: "History" },
        ]}
      />
      {!v || !d ? (
        <EmptyState title="This strategy has no version" />
      ) : tab === "overview" ? (
        <OverviewTab s={s} v={v} d={d} onRun={() => setTab("backtest")} />
      ) : tab === "backtest" ? (
        <BacktestTab s={s} d={d} />
      ) : tab === "validation" ? (
        <ValidationTab v={v} d={d} />
      ) : tab === "logic" ? (
        <LogicTab s={s} d={d} onSaved={(n) => setData(n)} />
      ) : (
        <HistoryTab s={s} />
      )}
    </>
  );
}

function OverviewTab({ s, v, d, onRun }: { s: Strategy; v: Version; d: StrategyDefinition; onRun: () => void }) {
  const rm = d.risk_management;
  const sides: ("long" | "short")[] = d.direction === "long_short" ? ["long", "short"] : [d.direction];
  return (
    <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
      <Panel title="Rules in plain language">
        <div className="space-y-3 text-[13px]">
          {d.description && <p className="text-fg-muted">{d.description}</p>}
          {sides.map((side) => (
            <div key={side} className="space-y-1">
              <div>
                <span className="mr-2 text-xs uppercase tracking-wide text-fg-faint">Enter {side}</span>
                <code className="text-fg">{describeCondition(d.entry[side], d.indicators)}</code>
              </div>
              <div>
                <span className="mr-2 text-xs uppercase tracking-wide text-fg-faint">Exit {side}</span>
                <code className="text-fg">{d.exit[side] ? describeCondition(d.exit[side], d.indicators) : "stop, target or time limit only"}</code>
              </div>
            </div>
          ))}
          <KV
            items={[
              ["Stop loss", rm.stop_loss.type === "none" ? "none" : rm.stop_loss.type === "percent" ? `${rm.stop_loss.value} %` : `${rm.stop_loss.value} × ATR`],
              ["Take profit", rm.take_profit.type === "none" ? "none" : rm.take_profit.type === "percent" ? `${rm.take_profit.value} %` : rm.take_profit.type === "atr" ? `${rm.take_profit.value} × ATR` : `${rm.take_profit.value} R`],
              ["Time limit", rm.max_bars_in_trade ? `${rm.max_bars_in_trade} candles` : "none"],
              ["Sizing", d.position_sizing.type === "risk_percent" ? `risk ${d.position_sizing.risk_percent} % per trade, max ${pct(d.position_sizing.fraction, 0)} of equity` : `${pct(d.position_sizing.fraction, 0)} of equity`],
              ["Costs", `${d.costs.fee_bps} bps fee + ${d.costs.slippage_bps} bps slippage per fill`],
              ["Execution", "signal on close, fill at next open"],
            ]}
          />
        </div>
      </Panel>
      <div className="space-y-4">
        <Panel title="Last backtest" actions={<Button size="sm" variant="primary" onClick={onRun}>Run backtest</Button>}>
          {s.last_backtest ? (
            <div className="flex items-center justify-between gap-3 text-[13px]">
              <div className="flex items-center gap-2">
                <StatusBadge status={s.last_backtest.status} />
                <span className="text-fg-muted">{ago(s.last_backtest.created_at)}</span>
              </div>
              <div className="flex items-center gap-3">
                {s.last_backtest.status === "completed" && <Value v={s.last_backtest.net_return} text={pct(s.last_backtest.net_return, 2, true)} />}
                <Link href={`/backtests/${s.last_backtest.id}`} className="text-accent hover:underline">
                  Open
                </Link>
              </div>
            </div>
          ) : (
            <p className="text-[13px] text-fg-muted">Not backtested yet.</p>
          )}
        </Panel>
        <Panel title="Version">
          <KV
            items={[
              ["Version", `v${v.version_number} of ${s.version_count}`],
              ["Saved", dt(v.created_at)],
              ["Hash", <Hash key="h" value={v.canonical_hash} len={16} />],
              ["Schema", v.schema_version],
              ["Note", v.note || "none"],
            ]}
          />
        </Panel>
      </div>
    </div>
  );
}

function BacktestTab({ s, d }: { s: Strategy; d: StrategyDefinition }) {
  const { data, error, reload } = useApi<{ items: BacktestRow[] }>(`/strategies/${s.id}/backtests?limit=50`, { pollMs: 3000, shouldPoll: (x) => !!x?.items.some((b) => isActive(b.status)) });
  return (
    <div className="space-y-4">
      <Panel title={`Run a backtest (v${s.current_version?.version_number})`}>
        {s.status === "archived" ? (
          <p className="text-[13px] text-fg-muted">Restore the strategy to run new backtests.</p>
        ) : (
          <RunBacktestForm strategyId={s.id} symbol={d.symbols[0]} timeframe={d.timeframe} fee={d.costs.fee_bps} slippage={d.costs.slippage_bps} />
        )}
      </Panel>
      <Panel title="Backtest history" pad={false}>
        {error ? (
          <div className="p-4">
            <ErrorState error={error} onRetry={reload} />
          </div>
        ) : !data ? (
          <div className="p-4">
            <LoadingBlock />
          </div>
        ) : data.items.length === 0 ? (
          <p className="p-4 text-[13px] text-fg-muted">No backtests yet.</p>
        ) : (
          <Table head={["Run", "Version", "Status", "Net return", "Max DD", "Trades", "Data", "Created"]}>
            {data.items.map((b) => (
              <tr key={b.id}>
                <td>
                  <Link href={`/backtests/${b.id}`} className="num text-fg hover:text-accent">
                    {b.id.slice(0, 8)}
                  </Link>
                </td>
                <td className="num">v{b.version_number ?? "?"}</td>
                <td>
                  <StatusBadge status={b.status} />
                </td>
                <td>{b.metrics ? <Value v={b.metrics.net_return} text={pct(b.metrics.net_return, 2, true)} /> : <span className="text-fg-faint">{b.error_message ?? "n/a"}</span>}</td>
                <td className="num">{b.metrics ? pct(b.metrics.max_drawdown) : "n/a"}</td>
                <td className="num">{b.metrics ? int(b.metrics.trade_count) : "n/a"}</td>
                <td>
                  <SyntheticBadge show={b.is_synthetic_data} />
                </td>
                <td className="text-fg-muted">{ago(b.created_at)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Panel>
    </div>
  );
}

function ValidationTab({ v, d }: { v: Version; d: StrategyDefinition }) {
  const { data, error, reload } = useApi<Validation[]>(`/validations?strategy_version_id=${v.id}`, { pollMs: 3000, shouldPoll: (x) => !!x?.some((r) => isActive(r.status)) });
  const [selected, setSelected] = useState<string | null>(null);
  const current = data?.find((x) => x.id === selected) ?? data?.[0];
  return (
    <div className="space-y-4">
      <Panel title={`Out-of-sample validation (v${v.version_number})`}>
        <p className="mb-3 text-xs text-fg-muted">
          Splits the data chronologically, runs rolling walk-forward windows without re-optimizing, doubles costs and nudges each numeric parameter by ±20 %. A strategy that only works in-sample shows it here.
        </p>
        <RunValidationForm
          versionId={v.id}
          symbol={d.symbols[0]}
          timeframe={d.timeframe}
          onCreated={(x) => {
            setSelected(x.id);
            void reload();
          }}
        />
      </Panel>
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data ? (
        <LoadingBlock />
      ) : data.length === 0 ? (
        <p className="text-[13px] text-fg-muted">No validation runs for this version yet.</p>
      ) : (
        <>
          {data.length > 1 && (
            <Field label="Validation run" className="max-w-sm">
              {(fid) => <Select id={fid} value={current?.id} onChange={(e) => setSelected(e.target.value)} options={data.map((x) => ({ value: x.id, label: `${dt(x.created_at)} · ${x.status}` }))} />}
            </Field>
          )}
          {current && <ValidationView v={current} />}
        </>
      )}
    </div>
  );
}

function LogicTab({ s, d, onSaved }: { s: Strategy; d: StrategyDefinition; onSaved: (s: Strategy) => void }) {
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState<string | null>(null);
  if (s.status === "archived") return <p className="text-[13px] text-fg-muted">Archived strategies are read-only. Restore it to edit.</p>;

  async function save(def: StrategyDefinition) {
    setSaving(true);
    setError(null);
    setSaved(null);
    try {
      const before = s.current_version?.version_number;
      const n = await api<Strategy>(`/strategies/${s.id}`, { method: "PATCH", json: { name: def.name, description: def.description ?? "", definition: def, note } });
      onSaved(n);
      setSaved(n.current_version?.version_number === before ? "No logic change: the definition is identical to the current version, so no new version was created." : `Saved as v${n.current_version?.version_number}.`);
      setNote("");
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }

  return (
    <StrategyEditor
      key={s.current_version?.id}
      initial={d}
      onSave={(def) => void save(def)}
      saving={saving}
      saveError={error}
      saveLabel="Save as new version"
      extraFields={
        <>
          <Field label="Version note (optional)" className="max-w-xl">
            {(id) => <Input id={id} value={note} maxLength={300} placeholder="What changed and why" onChange={(e) => setNote(e.target.value)} />}
          </Field>
          {saved && <p className="text-[13px] text-accent">{saved}</p>}
        </>
      }
    />
  );
}

function flatten(o: unknown, prefix = "", out: Record<string, string> = {}): Record<string, string> {
  if (o && typeof o === "object" && !Array.isArray(o)) {
    for (const [k, v] of Object.entries(o)) flatten(v, prefix ? `${prefix}.${k}` : k, out);
  } else if (Array.isArray(o) && o.some((x) => x && typeof x === "object")) {
    o.forEach((v, i) => flatten(v, `${prefix}[${i}]`, out));
  } else {
    out[prefix] = JSON.stringify(o);
  }
  return out;
}

function HistoryTab({ s }: { s: Strategy }) {
  const { data, error, reload } = useApi<Version[]>(`/strategies/${s.id}/versions`);
  const [a, setA] = useState<string>("");
  const [b, setB] = useState<string>("");
  const versions = useMemo(() => data ?? [], [data]);
  const va = versions.find((x) => x.id === a) ?? versions[1];
  const vb = versions.find((x) => x.id === b) ?? versions[0];
  const diff = useMemo(() => {
    if (!va || !vb) return [];
    const fa = flatten(va.definition_json);
    const fb = flatten(vb.definition_json);
    return [...new Set([...Object.keys(fa), ...Object.keys(fb)])].filter((k) => fa[k] !== fb[k]).map((k) => ({ path: k, before: fa[k], after: fb[k] }));
  }, [va, vb]);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return <LoadingBlock />;
  const opts = versions.map((x) => ({ value: x.id, label: `v${x.version_number} · ${dt(x.created_at)}` }));
  return (
    <div className="space-y-4">
      <Panel title="Versions" pad={false}>
        <Table head={["Version", "Saved", "Hash", "Note"]}>
          {versions.map((x) => (
            <tr key={x.id}>
              <td className="num">
                v{x.version_number} {x.id === s.current_version_id && <Badge tone="positive">current</Badge>}
              </td>
              <td className="text-fg-muted">{dt(x.created_at)}</td>
              <td>
                <Hash value={x.canonical_hash} len={12} />
              </td>
              <td className="text-fg-muted">{x.note || "—"}</td>
            </tr>
          ))}
        </Table>
      </Panel>
      {versions.length > 1 && va && vb && (
        <Panel title="Compare versions">
          <div className="mb-3 flex flex-wrap gap-3">
            <Field label="From" className="w-60">
              {(id) => <Select id={id} value={va.id} options={opts} onChange={(e) => setA(e.target.value)} />}
            </Field>
            <Field label="To" className="w-60">
              {(id) => <Select id={id} value={vb.id} options={opts} onChange={(e) => setB(e.target.value)} />}
            </Field>
          </div>
          {diff.length === 0 ? (
            <p className="text-[13px] text-fg-muted">No differences.</p>
          ) : (
            <Table head={["Field", `v${va.version_number}`, `v${vb.version_number}`]}>
              {diff.map((r) => (
                <tr key={r.path}>
                  <td>
                    <code className="text-xs">{r.path}</code>
                  </td>
                  <td>
                    <code className="text-xs text-negative">{r.before ?? "—"}</code>
                  </td>
                  <td>
                    <code className="text-xs text-accent">{r.after ?? "—"}</code>
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </Panel>
      )}
    </div>
  );
}
