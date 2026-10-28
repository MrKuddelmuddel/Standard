"use client";

import { useParams, useRouter } from "next/navigation";
import { Suspense, useState } from "react";

import { MetricCell } from "@/components/runs";
import { Badge, Button, ErrorState, IssueList, JobProgress, KV, LoadingBlock, Notice, PageHeader, Panel, Select, Stat, StatusBadge, SyntheticBadge, Table } from "@/components/ui";
import { post } from "@/lib/api";
import { date, dt, int, num } from "@/lib/format";
import { isActive, useApi } from "@/lib/hooks";
import { describeCondition } from "@/lib/strategy";
import type { Candidate, Discovery, Page, Strategy } from "@/lib/types";

export default function DiscoveryPage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <DiscoveryDetail />
    </Suspense>
  );
}

function DiscoveryDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: d, error, loading, reload } = useApi<Discovery>(`/discoveries/${id}`, { pollMs: 1500, shouldPoll: (x) => !x || isActive(x.status) });
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("score");
  const [open, setOpen] = useState<string | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const running = isActive(d?.status);
  const cands = useApi<Page<Candidate>>(d && !running ? `/discoveries/${id}/candidates?limit=200&sort=${sort}${status ? `&status=${status}` : ""}` : null);

  if (loading && !d) return <LoadingBlock rows={6} />;
  if (error || !d) return <ErrorState error={error} onRetry={reload} />;
  const rep = d.report;

  async function save(c: Candidate) {
    setSaving(c.id);
    setActionError(null);
    try {
      const s = await post<Strategy>(`/discoveries/${id}/candidates/${c.id}/save`);
      router.push(`/strategies/${s.id}`);
    } catch (e) {
      setActionError(e);
      setSaving(null);
    }
  }

  return (
    <>
      <PageHeader
        title={`Discovery ${d.id.slice(0, 8)}`}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={d.status} />
            <SyntheticBadge show={d.is_synthetic_data} />
            <span>
              {String(d.search_config.symbol)} {String(d.search_config.timeframe)} · {String(d.search_config.direction)} · {(d.search_config.templates as string[] | undefined)?.join(", ")}
            </span>
          </span>
        }
        actions={
          running ? (
            <Button
              size="sm"
              variant="danger"
              onClick={async () => {
                await post(`/discoveries/${id}/cancel`).catch(setActionError);
                await reload();
              }}
            >
              Cancel
            </Button>
          ) : null
        }
      />
      <IssueList error={actionError} />
      {running && (
        <Panel className="mb-4">
          <JobProgress job={d.job} />
        </Panel>
      )}
      {d.status === "failed" && <Notice tone="negative" title="Discovery failed">{d.error_message}</Notice>}
      {rep && (
        <div className="mb-4 space-y-4">
          {rep.warning && <Notice tone="warning">{rep.warning}</Notice>}
          {rep.stopped_early && <Notice tone="info">Stopped early: {rep.stopped_early}</Notice>}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            <Stat label="Generated" value={int(rep.generated)} />
            <Stat label="Duplicates removed" value={int(rep.duplicates_removed)} />
            <Stat label="Tested" value={int(rep.tested)} />
            <Stat label="Validated" value={int(rep.status_counts.validated ?? 0)} />
            <Stat label="Shortlisted" value={int(rep.status_counts.shortlisted ?? 0)} />
            <Stat label="Rejected" value={int(rep.status_counts.rejected ?? 0)} />
          </div>
          <Panel title="Segments">
            <div className="grid gap-4 md:grid-cols-2">
              <KV items={rep.segments.map((s) => [s.name, `${date(s.start_time)} – ${date(s.end_time)} · ${int(s.bars)} candles`] as [string, string])} />
              <p className="text-xs text-fg-muted">
                {rep.note} Ranking: <code>{rep.ranking_version}</code>.
              </p>
            </div>
          </Panel>
        </div>
      )}
      {!running && (
        <Panel
          title="Candidates"
          pad={false}
          actions={
            <>
              <Select
                aria-label="Filter by status"
                className="h-7 w-36 text-xs"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                options={[
                  { value: "", label: "All statuses" },
                  { value: "validated", label: "Validated" },
                  { value: "shortlisted", label: "Shortlisted" },
                  { value: "rejected", label: "Rejected" },
                  { value: "generated", label: "Generated" },
                ]}
              />
              <Select
                aria-label="Sort"
                className="h-7 w-32 text-xs"
                value={sort}
                onChange={(e) => setSort(e.target.value)}
                options={[
                  { value: "score", label: "By score" },
                  { value: "name", label: "By name" },
                ]}
              />
            </>
          }
        >
          {cands.error ? (
            <div className="p-4">
              <ErrorState error={cands.error} onRetry={cands.reload} />
            </div>
          ) : !cands.data ? (
            <div className="p-4">
              <LoadingBlock />
            </div>
          ) : cands.data.items.length === 0 ? (
            <p className="p-4 text-[13px] text-fg-muted">No candidates match.</p>
          ) : (
            <Table head={["Candidate", "Status", "Score", "Val. return", "Val. max DD", "Val. trades", "Val. PF", "Val. ×2 costs", "Test return", "Test trades", ""]}>
              {cands.data.items.map((c) => (
                <CandidateRow key={c.id} c={c} open={open === c.id} onToggle={() => setOpen(open === c.id ? null : c.id)} onSave={() => void save(c)} saving={saving === c.id} />
              ))}
            </Table>
          )}
          <p className="border-t border-line px-4 py-2 text-xs text-fg-faint">Score uses validation metrics only. Test results are shown for candidates that passed validation and were never used for ranking.</p>
        </Panel>
      )}
      <p className="mt-3 text-xs text-fg-faint">Created {dt(d.created_at)} · data fingerprint {d.data_fingerprint?.slice(0, 12) ?? "n/a"}</p>
    </>
  );
}

function CandidateRow({ c, open, onToggle, onSave, saving }: { c: Candidate; open: boolean; onToggle: () => void; onSave: () => void; saving: boolean }) {
  const def = c.definition_json;
  const side = def.direction === "short" ? "short" : "long";
  const tested = Object.keys(c.metrics.test ?? {}).length > 0;
  return (
    <>
      <tr>
        <td>
          <button type="button" onClick={onToggle} aria-expanded={open} className="text-left font-medium text-fg hover:text-accent">
            {c.name}
          </button>
          {c.flags.length > 0 && (
            <div className="mt-0.5 flex flex-wrap gap-1">
              {c.flags.map((f) => (
                <Badge key={f} tone="warning">
                  {f.replaceAll("_", " ")}
                </Badge>
              ))}
            </div>
          )}
        </td>
        <td>
          <StatusBadge status={c.status} />
        </td>
        <td className="num">{c.score !== null ? num(c.score, 3) : "n/a"}</td>
        <td>
          <MetricCell k="net_return" m={c.metrics.validation} />
        </td>
        <td>
          <MetricCell k="max_drawdown" m={c.metrics.validation} />
        </td>
        <td>
          <MetricCell k="trade_count" m={c.metrics.validation} />
        </td>
        <td>
          <MetricCell k="profit_factor" m={c.metrics.validation} />
        </td>
        <td>
          <MetricCell k="net_return" m={c.metrics.validation_2x_costs} />
        </td>
        <td>{tested ? <MetricCell k="net_return" m={c.metrics.test} /> : <span className="text-fg-faint">not run</span>}</td>
        <td>{tested ? <MetricCell k="trade_count" m={c.metrics.test} /> : null}</td>
        <td className="text-right">
          {c.strategy_version_id ? (
            <Badge tone="positive">saved</Badge>
          ) : (
            <Button size="sm" onClick={onSave} loading={saving}>
              Save as strategy
            </Button>
          )}
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={11} className="bg-panel-2">
            <div className="grid gap-3 py-1 text-xs md:grid-cols-2">
              <div className="space-y-1">
                <div>
                  <span className="text-fg-faint">Entry: </span>
                  <code>{describeCondition(def.entry[side], def.indicators)}</code>
                </div>
                <div>
                  <span className="text-fg-faint">Exit: </span>
                  <code>{def.exit[side] ? describeCondition(def.exit[side], def.indicators) : "stop / target only"}</code>
                </div>
                {c.rejection_reason && <div className="text-negative">Rejected: {c.rejection_reason}</div>}
              </div>
              <Table head={["Segment", "Return", "Max DD", "Trades", "Win rate", "PF"]}>
                {(["train", "validation", "test"] as const).map((k) => (
                  <tr key={k}>
                    <td>{k}</td>
                    {["net_return", "max_drawdown", "trade_count", "win_rate", "profit_factor"].map((m) => (
                      <td key={m}>
                        <MetricCell k={m} m={c.metrics[k]} />
                      </td>
                    ))}
                  </tr>
                ))}
              </Table>
            </div>
            {Object.keys(c.score_parts).length > 0 && (
              <p className="pb-1 text-xs text-fg-faint">
                Score parts:{" "}
                {Object.entries(c.score_parts)
                  .map(([k, v]) => `${k} ${num(v, 3)}`)
                  .join(" · ")}
              </p>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
