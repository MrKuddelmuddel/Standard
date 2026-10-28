"use client";

import { date, int, pct } from "@/lib/format";
import type { SplitMetrics, Validation } from "@/lib/types";

import { MetricCell } from "./runs";
import { Badge, JobProgress, Notice, Panel, StatusBadge, SyntheticBadge, Table } from "./ui";

const COLS = ["net_return", "max_drawdown", "trade_count", "win_rate", "profit_factor", "expectancy_r"];
const HEAD = ["Net return", "Max DD", "Trades", "Win rate", "PF", "Exp. (R)"];

function Row({ name, m, extra }: { name: React.ReactNode; m: SplitMetrics | undefined; extra?: React.ReactNode }) {
  if (m?.error) {
    return (
      <tr>
        <td className="font-medium">{name}</td>
        <td colSpan={COLS.length} className="text-xs text-warning">
          {m.message ?? m.error}
        </td>
        {extra !== undefined && <td>{extra}</td>}
      </tr>
    );
  }
  return (
    <tr>
      <td className="font-medium">{name}</td>
      {COLS.map((k) => (
        <td key={k}>
          <MetricCell k={k} m={m} />
        </td>
      ))}
      {extra !== undefined && <td>{extra}</td>}
    </tr>
  );
}

/** Out-of-sample report: chronological splits, walk-forward, cost stress and parameter neighbours. */
export function ValidationView({ v }: { v: Validation }) {
  const m = v.metrics;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
        <StatusBadge status={v.status} />
        <SyntheticBadge show={v.is_synthetic_data} />
        <span>
          {v.method} · train {pct(v.configuration.train_fraction, 0)} / validation {pct(v.configuration.validation_fraction, 0)} · {v.configuration.folds} folds · costs ×{v.configuration.cost_multiplier}
        </span>
        <span>· {date(v.created_at)}</span>
      </div>
      {v.status === "queued" || v.status === "running" ? <JobProgress job={{ id: v.id, status: v.status, progress_current: null, progress_total: null, error_code: null, error_message: null, cancel_requested: false }} /> : null}
      {v.error_message && <Notice tone="negative">{v.error_message}</Notice>}
      {v.warnings && v.warnings.length > 0 && (
        <Notice tone="warning" title="Read before trusting these numbers">
          <ul className="list-disc pl-4 text-xs">
            {v.warnings.map((w, i) => (
              <li key={i}>{String(w)}</li>
            ))}
          </ul>
        </Notice>
      )}
      {m && (
        <>
          <Panel title="Chronological splits" pad={false}>
            <Table head={["Segment", ...HEAD]}>
              {(v.segments ?? []).map((s) => (
                <Row
                  key={s.name}
                  m={m.splits[s.name]}
                  name={
                    <span>
                      {s.name}
                      <span className="ml-2 text-xs font-normal text-fg-faint">
                        {date(s.start_time)} – {date(s.end_time)} · {int(s.bars)} candles
                      </span>
                    </span>
                  }
                />
              ))}
            </Table>
            <p className="border-t border-line px-4 py-2 text-xs text-fg-faint">Parameters are fixed. The test segment shows how the unchanged strategy behaved on data it was not tuned on.</p>
          </Panel>
          <Panel
            title="Walk-forward folds"
            pad={false}
            actions={m.walk_forward_summary && <Badge tone={m.walk_forward_summary.profitable_folds * 2 > m.walk_forward_summary.folds_with_trades ? "positive" : "warning"}>
                  {m.walk_forward_summary.profitable_folds}/{m.walk_forward_summary.folds_with_trades} folds with trades profitable
                </Badge>}
          >
            <Table head={["Fold", ...HEAD]}>
              {m.walk_forward.map((f) => (
                <Row
                  key={f.name}
                  m={f}
                  name={
                    <span>
                      {f.name}
                      <span className="ml-2 text-xs font-normal text-fg-faint">
                        {date(f.start_time)} – {date(f.end_time)}
                      </span>
                    </span>
                  }
                />
              ))}
            </Table>
            {m.walk_forward_summary?.note && <p className="border-t border-line px-4 py-2 text-xs text-fg-faint">{m.walk_forward_summary.note}</p>}
          </Panel>
          <div className="grid gap-4 xl:grid-cols-2">
            <Panel title={`Cost sensitivity (×${m.cost_sensitivity.multiplier})`} pad={false}>
              <Table head={["Costs", ...HEAD]}>
                <Row name="Base" m={m.cost_sensitivity.base} />
                <Row name={`×${m.cost_sensitivity.multiplier}`} m={m.cost_sensitivity.stressed} />
              </Table>
            </Panel>
            <Panel
              title="Parameter neighbours (±20 %)"
              pad={false}
              actions={m.parameter_stability_summary && <Badge tone={m.parameter_stability_summary.sign_flips === 0 ? "positive" : "warning"}>{m.parameter_stability_summary.sign_flips} sign flips</Badge>}
            >
              {m.parameter_stability.length === 0 ? (
                <p className="p-4 text-xs text-fg-faint">No tunable numeric parameters found.</p>
              ) : (
                <Table head={["Change", ...HEAD]}>
                  {m.parameter_stability.map((p, i) => (
                    <Row key={i} name={<code className="text-xs">{p.change}</code>} m={p} />
                  ))}
                </Table>
              )}
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
