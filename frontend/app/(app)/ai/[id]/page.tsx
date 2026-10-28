"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Suspense, useState } from "react";

import { compatibleSources, NoCompatibleData, NoDataNotice, sourceLabel, useSources } from "@/components/runs";
import { Badge, Button, ErrorState, Field, Input, IssueList, JobProgress, KV, LinkButton, LoadingBlock, Notice, PageHeader, Panel, Select, StatusBadge, Table } from "@/components/ui";
import { post } from "@/lib/api";
import { dt, formatJson, int } from "@/lib/format";
import { isActive, useApi } from "@/lib/hooks";
import { describeCondition } from "@/lib/strategy";
import type { AgentRun } from "@/lib/types";

export default function AiRunPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <RunDetail />
    </Suspense>
  );
}

function List({ title, items, tone }: { title: string; items?: string[]; tone?: "warning" }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <div className={tone === "warning" ? "mb-1 text-xs font-medium text-warning" : "mb-1 text-xs font-medium text-fg-muted"}>{title}</div>
      <ul className="list-disc space-y-0.5 pl-4 text-[13px]">
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </div>
  );
}

function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: r, error, loading, reload, setData } = useApi<AgentRun>(`/ai/runs/${id}`, { pollMs: 1500, shouldPoll: (x) => !x || isActive(x.status) });
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);

  if (loading && !r) return <LoadingBlock rows={6} />;
  if (error || !r) return <ErrorState error={error} onRetry={reload} />;
  const out = r.structured_output;
  const def = out?.definition;
  const sides: ("long" | "short")[] = def ? (def.direction === "long_short" ? ["long", "short"] : [def.direction]) : [];

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

  return (
    <>
      <PageHeader
        title={r.kind === "research" ? "Research run" : "Explanation"}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={r.status} />
            <span>
              {r.provider}
              {r.model && ` · ${r.model}`} · {dt(r.created_at)}
            </span>
          </span>
        }
        actions={
          <>
            {isActive(r.status) && (
              <Button size="sm" variant="danger" loading={busy === "cancel"} onClick={() => void act("cancel", async () => void (await post(`/ai/runs/${id}/cancel`), await reload()))}>
                Cancel
              </Button>
            )}
            {r.strategy_id && (
              <LinkButton size="sm" href={`/strategies/${r.strategy_id}`}>
                Strategy
              </LinkButton>
            )}
            {r.backtest_run_id && (
              <LinkButton size="sm" href={`/backtests/${r.backtest_run_id}`}>
                Backtest
              </LinkButton>
            )}
          </>
        }
      />
      <IssueList error={actionError} />
      <Panel title="Task" className="mb-4">
        <p className="whitespace-pre-wrap text-[13px]">{r.task}</p>
      </Panel>
      {isActive(r.status) && (
        <Panel className="mb-4">
          <JobProgress job={r.job} />
          <p className="mt-2 text-xs text-fg-faint">Waiting for the model. The page updates automatically.</p>
        </Panel>
      )}
      {r.status === "failed" && (
        <Notice tone="negative" title="Run failed">
          {r.error_message} {r.error_code && <code className="text-xs">({r.error_code})</code>}
        </Notice>
      )}

      {out && def && (
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-2">
            <Panel title="Proposal">
              <div className="space-y-3 text-[13px]">
                {out.hypothesis && (
                  <div>
                    <div className="mb-1 text-xs font-medium text-fg-muted">Hypothesis</div>
                    <p>{out.hypothesis}</p>
                  </div>
                )}
                <div>
                  <div className="mb-1 text-xs font-medium text-fg-muted">{def.name}</div>
                  <p className="text-fg-muted">
                    {def.symbols.join(", ")} · {def.timeframe} · {def.market_type} · {def.direction}
                  </p>
                </div>
                {sides.map((side) => (
                  <div key={side} className="space-y-1">
                    <div>
                      <span className="mr-2 text-xs uppercase text-fg-faint">Enter {side}</span>
                      <code>{describeCondition(def.entry[side], def.indicators)}</code>
                    </div>
                    <div>
                      <span className="mr-2 text-xs uppercase text-fg-faint">Exit {side}</span>
                      <code>{def.exit[side] ? describeCondition(def.exit[side], def.indicators) : "stop / target / time only"}</code>
                    </div>
                  </div>
                ))}
                <details>
                  <summary className="cursor-pointer text-xs text-fg-muted">Strategy JSON</summary>
                  <pre className="mt-2 max-h-80 overflow-auto rounded-md bg-panel-2 p-3 text-xs">{formatJson(def)}</pre>
                </details>
              </div>
            </Panel>
            <Panel title="Assumptions and limits">
              <div className="space-y-3">
                <List title="Not supported (left out)" items={out.unsupported_requests} tone="warning" />
                <List title="Assumptions" items={out.assumptions} />
                <List title="Suggested tests" items={out.suggested_tests} />
                {!out.unsupported_requests?.length && !out.assumptions?.length && <p className="text-[13px] text-fg-muted">None reported.</p>}
              </div>
            </Panel>
          </div>
          {r.status === "awaiting_confirmation" && <ConfirmPanel run={r} onDone={(x) => setData(x)} />}
          {r.status === "confirmed" && (
            <Panel title="Next">
              <div className="flex flex-wrap items-center gap-3 text-[13px]">
                <span className="text-fg-muted">Strategy saved, backtest and validation started.</span>
                <Button
                  size="sm"
                  variant="primary"
                  loading={busy === "explain"}
                  onClick={() =>
                    void act("explain", async () => {
                      const e = await post<AgentRun>(`/ai/runs/${id}/explain`);
                      router.push(`/ai/${e.id}`);
                    })
                  }
                >
                  Explain backtest results
                </Button>
                <span className="text-xs text-fg-faint">Available once the backtest has completed.</span>
              </div>
            </Panel>
          )}
        </div>
      )}

      {r.report && r.kind === "explanation" && (
        <div className="space-y-4">
          <Notice tone="warning">
            <span className="text-xs">This text is generated by a language model from the stored metrics. Check every claim against the backtest page.</span>
          </Notice>
          <Panel title="Explanation">
            <div className="space-y-3">
              {r.report.summary && <p className="text-[13px]">{r.report.summary}</p>}
              <List title="Observations" items={r.report.observations} />
              <List title="Interpretation" items={r.report.interpretation} />
              <List title="Risks and limitations" items={r.report.risks_and_limitations} tone="warning" />
              <List title="Next tests" items={r.report.next_tests} />
            </div>
          </Panel>
        </div>
      )}

      {(r.usage.input_tokens !== undefined || (r.tool_calls?.length ?? 0) > 0) && (
        <Panel title="Usage and tool calls" className="mt-4" pad={false}>
          <div className="px-4 py-3">
            <KV
              items={[
                ["Model calls", int(r.usage.model_calls)],
                ["Input tokens", int(r.usage.input_tokens)],
                ["Output tokens", int(r.usage.output_tokens)],
                ["Estimated cost", r.usage.estimated_cost_usd !== null && r.usage.estimated_cost_usd !== undefined ? `$${r.usage.estimated_cost_usd.toFixed(4)}` : (r.usage.cost_note ?? "not estimated")],
              ]}
            />
          </div>
          {r.tool_calls && r.tool_calls.length > 0 && (
            <Table head={["#", "Tool", "Result", "Duration"]}>
              {r.tool_calls.map((t) => (
                <tr key={t.sequence}>
                  <td className="num text-fg-faint">{t.sequence}</td>
                  <td>
                    <code className="text-xs">{t.tool_name}</code>
                  </td>
                  <td>
                    {t.is_error ? <Badge tone="negative">error</Badge> : <Badge tone="positive">ok</Badge>}
                    <details className="inline-block align-top">
                      <summary className="ml-2 cursor-pointer text-xs text-fg-muted">details</summary>
                      <pre className="mt-1 max-h-64 max-w-xl overflow-auto rounded bg-panel-2 p-2 text-[11px]">{formatJson({ arguments: t.arguments, result: t.result })}</pre>
                    </details>
                  </td>
                  <td className="num text-fg-muted">{t.duration_ms} ms</td>
                </tr>
              ))}
            </Table>
          )}
        </Panel>
      )}
      <p className="mt-3 text-xs text-fg-faint">
        <Link href="/ai" className="hover:underline">
          Back to AI Research
        </Link>
      </p>
    </>
  );
}

function ConfirmPanel({ run, onDone }: { run: AgentRun; onDone: (r: AgentRun) => void }) {
  const { data: sources, loading } = useSources();
  const [sourceId, setSourceId] = useState("");
  const [capital, setCapital] = useState("10000");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const def = run.structured_output?.definition;
  if (loading && !sources) return <LoadingBlock />;
  if (!sources || sources.length === 0) return <NoDataNotice />;
  const usable = compatibleSources(sources, def?.symbols[0], def?.timeframe);
  if (usable.length === 0) return <NoCompatibleData symbol={def?.symbols[0]} timeframe={def?.timeframe} />;
  const selected = usable.some((s) => s.id === sourceId) ? sourceId : usable[0].id;

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      onDone(await post<AgentRun>(`/ai/runs/${run.id}/confirm`, { market_data_source_id: selected, initial_capital: Number(capital) }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="Confirm and test">
      <p className="mb-3 text-xs text-fg-muted">Confirming saves this strategy as version 1 and starts a backtest and an out-of-sample validation. Nothing is created until you confirm.</p>
      <div className="grid gap-3 md:grid-cols-[1fr_200px]">
        <Field label="Data source">
          {(id) => <Select id={id} value={selected} onChange={(e) => setSourceId(e.target.value)} options={usable.map((s) => ({ value: s.id, label: sourceLabel(s) }))} />}
        </Field>
        <Field label="Initial capital">{(id) => <Input id={id} type="number" min={1} value={capital} onChange={(e) => setCapital(e.target.value)} />}</Field>
      </div>
      <IssueList error={error} />
      <Button variant="primary" className="mt-3" onClick={() => void confirm()} loading={busy}>
        Confirm, save and test
      </Button>
    </Panel>
  );
}
