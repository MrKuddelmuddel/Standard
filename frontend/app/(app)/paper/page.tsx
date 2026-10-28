"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { compatibleSources, NoCompatibleData, NoDataNotice, sourceLabel, useSources } from "@/components/runs";
import { Button, Checkbox, EmptyState, ErrorState, Field, Input, IssueList, LinkButton, LoadingBlock, Notice, PageHeader, Panel, Select, StatusBadge, SyntheticBadge, Table, Value } from "@/components/ui";
import { post } from "@/lib/api";
import { ago, int, money, pct } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Page, PaperSession, Strategy } from "@/lib/types";

export default function PaperPage() {
  const { data, error, loading, reload } = useApi<Page<PaperSession>>("/paper/sessions?limit=50", { pollMs: 5000, shouldPoll: (d) => !!d?.items.some((s) => s.status === "running") });
  return (
    <>
      <PageHeader title="Paper Trading" subtitle="Replay stored candles bar by bar through the same simulator as the backtest. No real orders, no exchange connection." />
      <Notice tone="info">
        Mode: <strong>historical replay</strong>. Sessions step through candles that are already stored, one bar at a time, with the same fills and costs as a backtest. A live feed is not connected in this
        version.
      </Notice>
      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_1.3fr]">
        <Panel title="New session">
          <Suspense fallback={<LoadingBlock />}>
            <CreateSession />
          </Suspense>
        </Panel>
        <Panel title="Sessions" pad={false}>
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
              <EmptyState title="No paper sessions yet">Pick a strategy and a data source to start a replay.</EmptyState>
            </div>
          ) : data ? (
            <Table head={["Session", "Status", "Progress", "Equity", "Return", "Created"]}>
              {data.items.map((s) => (
                <tr key={s.id}>
                  <td>
                    <Link href={`/paper/${s.id}`} className="font-medium text-fg hover:text-accent">
                      {s.name}
                    </Link>{" "}
                    <SyntheticBadge show={s.is_synthetic_data} />
                  </td>
                  <td>
                    <StatusBadge status={s.status} />
                  </td>
                  <td className="num text-fg-muted">{s.progress ? `${int(s.progress.processed)} / ${int(s.progress.total)}` : "n/a"}</td>
                  <td className="num">{money(s.equity)}</td>
                  <td>
                    <Value v={s.equity / s.initial_capital - 1} text={pct(s.equity / s.initial_capital - 1, 2, true)} />
                  </td>
                  <td className="text-fg-muted">{ago(s.created_at)}</td>
                </tr>
              ))}
            </Table>
          ) : null}
        </Panel>
      </div>
    </>
  );
}

function CreateSession() {
  const router = useRouter();
  const search = useSearchParams();
  const { data: strategies, loading } = useApi<Page<Strategy>>("/strategies?limit=100");
  const { data: sources } = useSources();
  const [versionId, setVersionId] = useState(search.get("strategy_version_id") ?? "");
  const [sourceId, setSourceId] = useState(search.get("source_id") ?? "");
  const [name, setName] = useState("Paper session");
  const [capital, setCapital] = useState("10000");
  const [start, setStart] = useState("");
  const [auto, setAuto] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (loading && !strategies) return <LoadingBlock />;
  if (!sources || sources.length === 0) return <NoDataNotice />;
  const withVersion = (strategies?.items ?? []).filter((s) => s.current_version);
  if (withVersion.length === 0)
    return (
      <EmptyState title="No strategy yet" action={<LinkButton href="/strategies/new" variant="primary">Create a strategy</LinkButton>}>
        Paper sessions run a saved strategy version.
      </EmptyState>
    );
  const versionOptions = withVersion.map((s) => ({ value: s.current_version!.id, label: `${s.name} · v${s.current_version!.version_number}` }));
  if (versionId && !versionOptions.some((o) => o.value === versionId)) versionOptions.unshift({ value: versionId, label: "Version from backtest" });
  const selVersion = versionId || versionOptions[0].value;
  const selDef = withVersion.find((s) => s.current_version!.id === selVersion)?.current_version?.definition_json;
  const usable = selDef ? compatibleSources(sources, selDef.symbols[0], selDef.timeframe) : sources.filter((s) => s.row_count > 0);
  const selSource = usable.some((s) => s.id === sourceId) ? sourceId : (usable[0]?.id ?? "");

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const startMs = start ? Date.parse(`${start}T00:00:00Z`) : null;
      const s = await post<PaperSession>("/paper/sessions", {
        name,
        strategy_version_id: selVersion,
        market_data_source_id: selSource,
        initial_capital: Number(capital),
        start_time: startMs,
        auto_advance: auto,
      });
      router.push(`/paper/${s.id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <Field label="Name">{(id) => <Input id={id} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />}</Field>
      <Field label="Strategy version">{(id) => <Select id={id} value={selVersion} onChange={(e) => setVersionId(e.target.value)} options={versionOptions} />}</Field>
      {usable.length === 0 ? (
        <NoCompatibleData symbol={selDef?.symbols[0]} timeframe={selDef?.timeframe} />
      ) : (
        <Field label="Data source">{(id) => <Select id={id} value={selSource} onChange={(e) => setSourceId(e.target.value)} options={usable.map((s) => ({ value: s.id, label: sourceLabel(s) }))} />}</Field>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Initial capital (USDT)">{(id) => <Input id={id} type="number" min={1} value={capital} onChange={(e) => setCapital(e.target.value)} />}</Field>
        <Field label="Replay from (UTC, optional)" hint="Default: the first candle after the indicator warm-up.">
          {(id) => <Input id={id} type="date" value={start} onChange={(e) => setStart(e.target.value)} />}
        </Field>
      </div>
      <Checkbox label="Advance automatically in the background while running" checked={auto} onChange={setAuto} />
      <IssueList error={error} />
      <Button variant="primary" onClick={() => void create()} loading={busy} disabled={!selSource}>
        Create session
      </Button>
    </div>
  );
}
