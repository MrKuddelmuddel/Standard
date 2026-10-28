"use client";

import { useState } from "react";

import { errorMessage, post } from "@/lib/api";
import { cleanDefinition, describeCondition, fromRules, INDICATOR_TYPES, OPERATORS, PRICE_FIELDS, toRules } from "@/lib/strategy";
import type { Compare, Condition, Indicator, Operand, StrategyDefinition } from "@/lib/types";

import { Badge, Button, Field, Hash, Input, Notice, Panel, Select, Tabs, Textarea } from "./ui";

type ValidateResult = { valid: boolean; issues: { path: string; message: string }[]; canonical_hash?: string; warmup_bars?: number };

const SYMBOLS = ["BTCUSDT", "ETHUSDT"].map((v) => ({ value: v, label: v }));
const TIMEFRAMES = ["15m", "1h", "4h", "1d"].map((v) => ({ value: v, label: v }));

function numOr(v: string, fallback: number): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

/* ---------------------------------------------------------------- operands and rules */
function operandKey(o: Operand): string {
  if ("ind" in o) return `ind:${o.ind}`;
  if ("price" in o) return `price:${o.price}`;
  return "value";
}

function OperandEditor({ value, onChange, indicators, label }: { value: Operand; onChange: (o: Operand) => void; indicators: Indicator[]; label: string }) {
  const options = [
    ...indicators.map((i) => ({ value: `ind:${i.id}`, label: `${i.id} · ${i.type.toUpperCase()}(${i.period})` })),
    ...PRICE_FIELDS.map((p) => ({ value: `price:${p}`, label: `price: ${p}` })),
    { value: "value", label: "fixed number" },
  ];
  const key = operandKey(value);
  if ("ind" in value && !indicators.some((i) => i.id === value.ind)) options.unshift({ value: key, label: `${value.ind} (missing)` });
  return (
    <div className="flex min-w-0 gap-1.5">
      <Select
        aria-label={label}
        value={key}
        options={options}
        onChange={(e) => {
          const v = e.target.value;
          if (v === "value") onChange({ value: 0 });
          else if (v.startsWith("ind:")) onChange({ ind: v.slice(4) });
          else onChange({ price: v.slice(6) as (typeof PRICE_FIELDS)[number] });
        }}
      />
      {"value" in value && (
        <Input aria-label={`${label} number`} type="number" step="any" className="w-24 shrink-0" value={value.value} onChange={(e) => onChange({ value: numOr(e.target.value, 0) })} />
      )}
    </div>
  );
}

function RuleEditor({ title, condition, indicators, onChange }: { title: string; condition: Condition | null | undefined; indicators: Indicator[]; onChange: (c: Condition | null) => void }) {
  const flat = toRules(condition);
  if (flat === null) {
    return (
      <div className="space-y-1.5">
        <div className="text-xs font-medium text-fg-muted">{title}</div>
        <Notice tone="info">
          Nested logic: <code>{describeCondition(condition, indicators)}</code>. Edit it in the JSON tab.
        </Notice>
      </div>
    );
  }
  const { mode, rules } = flat;
  const set = (m: "all" | "any", r: Compare[]) => onChange(fromRules(m, r));
  const defaultLeft: Operand = indicators[0] ? { ind: indicators[0].id } : { price: "close" };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-medium text-fg-muted">{title}</div>
        {rules.length > 1 && (
          <Select
            aria-label={`${title} combiner`}
            className="h-7 w-auto text-xs"
            value={mode}
            options={[
              { value: "all", label: "all rules must match (AND)" },
              { value: "any", label: "any rule matches (OR)" },
            ]}
            onChange={(e) => set(e.target.value as "all" | "any", rules)}
          />
        )}
      </div>
      {rules.length === 0 && <p className="text-xs text-fg-faint">No rule. {title.startsWith("Exit") ? "Positions close via stop, target or time limit only." : "This side never enters."}</p>}
      {rules.map((r, i) => (
        <div key={i} className="grid grid-cols-1 items-center gap-1.5 rounded-md border border-line bg-panel-2 p-2 sm:grid-cols-[1fr_auto_1fr_auto]">
          <OperandEditor label={`${title} rule ${i + 1} left`} value={r.left} indicators={indicators} onChange={(left) => set(mode, rules.map((x, k) => (k === i ? { ...x, left } : x)))} />
          <Select
            aria-label={`${title} rule ${i + 1} operator`}
            className="sm:w-36"
            value={r.op}
            options={OPERATORS}
            onChange={(e) => set(mode, rules.map((x, k) => (k === i ? { ...x, op: e.target.value as Compare["op"] } : x)))}
          />
          <OperandEditor label={`${title} rule ${i + 1} right`} value={r.right} indicators={indicators} onChange={(right) => set(mode, rules.map((x, k) => (k === i ? { ...x, right } : x)))} />
          <Button size="sm" variant="ghost" aria-label={`Remove ${title} rule ${i + 1}`} onClick={() => set(mode, rules.filter((_, k) => k !== i))}>
            Remove
          </Button>
        </div>
      ))}
      <Button size="sm" onClick={() => set(mode, [...rules, { op: "gt", left: defaultLeft, right: { price: "close" } }])}>
        Add rule
      </Button>
    </div>
  );
}

/* ---------------------------------------------------------------- editor */
export function StrategyEditor({
  initial,
  onSave,
  saving,
  saveLabel,
  saveError,
  extraFields,
}: {
  initial: StrategyDefinition;
  onSave: (d: StrategyDefinition) => void;
  saving?: boolean;
  saveLabel: string;
  saveError?: unknown;
  extraFields?: React.ReactNode;
}) {
  const [def, setDef] = useState<StrategyDefinition>(initial);
  const [tab, setTab] = useState<"builder" | "json">("builder");
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [check, setCheck] = useState<ValidateResult | null>(null);
  const [checking, setChecking] = useState(false);

  const update = (patch: Partial<StrategyDefinition>) => {
    setDef((d) => ({ ...d, ...patch }));
    setCheck(null);
  };
  const sides: ("long" | "short")[] = def.direction === "long_short" ? ["long", "short"] : [def.direction];
  const atrs = def.indicators.filter((i) => i.type === "atr");
  const rm = def.risk_management;

  async function validate(d = def): Promise<ValidateResult | null> {
    setChecking(true);
    try {
      const r = await post<ValidateResult>("/strategies/validate", { definition: cleanDefinition(d) });
      setCheck(r);
      return r;
    } catch (e) {
      setCheck({ valid: false, issues: [{ path: "", message: errorMessage(e) }] });
      return null;
    } finally {
      setChecking(false);
    }
  }

  function switchTab(t: "builder" | "json") {
    if (t === "json") {
      setJsonText(JSON.stringify(cleanDefinition(def), null, 2));
      setJsonError(null);
    } else if (tab === "json") {
      try {
        const parsed = JSON.parse(jsonText) as StrategyDefinition;
        setDef({ ...parsed, entry: parsed.entry ?? {}, exit: parsed.exit ?? {}, indicators: parsed.indicators ?? [] });
        setCheck(null);
      } catch (e) {
        setJsonError(`Invalid JSON: ${(e as Error).message}`);
        return;
      }
    }
    setTab(t);
  }

  async function save() {
    let d = def;
    if (tab === "json") {
      try {
        d = JSON.parse(jsonText) as StrategyDefinition;
        setDef(d);
      } catch (e) {
        setJsonError(`Invalid JSON: ${(e as Error).message}`);
        return;
      }
    }
    const r = await validate(d);
    if (r?.valid) onSave(cleanDefinition(d));
  }

  const setIndicator = (i: number, patch: Partial<Indicator>) => update({ indicators: def.indicators.map((x, k) => (k === i ? { ...x, ...patch } : x)) });

  return (
    <div className="space-y-4">
      <Tabs
        tabs={[
          { value: "builder", label: "Builder" },
          { value: "json", label: "JSON" },
        ]}
        value={tab}
        onChange={switchTab}
      />
      {tab === "json" ? (
        <Panel title="Strategy definition (schema 1.0)">
          <Textarea aria-label="Strategy JSON" spellCheck={false} className="min-h-[480px] font-mono text-xs" value={jsonText} onChange={(e) => setJsonText(e.target.value)} />
          {jsonError && <p className="mt-2 text-xs text-negative">{jsonError}</p>}
          <p className="mt-2 text-xs text-fg-faint">The server validates every field. Unknown keys are rejected.</p>
        </Panel>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          <Panel title="Basics">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Name" className="sm:col-span-2">
                {(id) => <Input id={id} value={def.name} maxLength={80} onChange={(e) => update({ name: e.target.value })} />}
              </Field>
              <Field label="Description" className="sm:col-span-2">
                {(id) => <Textarea id={id} className="min-h-16" value={def.description ?? ""} maxLength={2000} onChange={(e) => update({ description: e.target.value })} />}
              </Field>
              <Field label="Symbol">{(id) => <Select id={id} value={def.symbols[0]} options={SYMBOLS} onChange={(e) => update({ symbols: [e.target.value] })} />}</Field>
              <Field label="Timeframe">{(id) => <Select id={id} value={def.timeframe} options={TIMEFRAMES} onChange={(e) => update({ timeframe: e.target.value })} />}</Field>
              <Field label="Market" hint={def.market_type === "futures_sim" ? "Simulated futures. Funding is not modeled." : "Spot: long only."}>
                {(id) => (
                  <Select
                    id={id}
                    value={def.market_type}
                    options={[
                      { value: "spot", label: "Spot" },
                      { value: "futures_sim", label: "Futures (simulated)" },
                    ]}
                    onChange={(e) => {
                      const market_type = e.target.value as StrategyDefinition["market_type"];
                      update(market_type === "spot" ? { market_type, direction: "long" } : { market_type });
                    }}
                  />
                )}
              </Field>
              <Field label="Direction">
                {(id) => (
                  <Select
                    id={id}
                    value={def.direction}
                    disabled={def.market_type === "spot"}
                    options={[
                      { value: "long", label: "Long only" },
                      { value: "short", label: "Short only" },
                      { value: "long_short", label: "Long and short" },
                    ]}
                    onChange={(e) => update({ direction: e.target.value as StrategyDefinition["direction"] })}
                  />
                )}
              </Field>
            </div>
          </Panel>

          <Panel title="Indicators" actions={<Badge>{def.indicators.length} / 12</Badge>}>
            <div className="space-y-2">
              {def.indicators.length === 0 && <p className="text-xs text-fg-faint">No indicators. Rules can still compare prices with fixed numbers.</p>}
              {def.indicators.map((ind, i) => (
                <div key={i} className="grid grid-cols-[1fr_1fr_80px_auto] items-end gap-1.5">
                  <Field label={i === 0 ? "ID" : ""}>
                    {(id) => <Input id={id} aria-label={`Indicator ${i + 1} id`} value={ind.id} maxLength={32} onChange={(e) => setIndicator(i, { id: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "") })} />}
                  </Field>
                  <Field label={i === 0 ? "Type" : ""}>
                    {(id) => (
                      <Select id={id} aria-label={`Indicator ${i + 1} type`} value={ind.type} options={INDICATOR_TYPES.map((t) => ({ value: t.value, label: t.label }))} onChange={(e) => setIndicator(i, { type: e.target.value })} />
                    )}
                  </Field>
                  <Field label={i === 0 ? "Period" : ""}>
                    {(id) => <Input id={id} aria-label={`Indicator ${i + 1} period`} type="number" min={2} max={500} value={ind.period} onChange={(e) => setIndicator(i, { period: Math.round(numOr(e.target.value, ind.period)) })} />}
                  </Field>
                  <Button size="sm" variant="ghost" className="mb-0.5" aria-label={`Remove indicator ${ind.id}`} onClick={() => update({ indicators: def.indicators.filter((_, k) => k !== i) })}>
                    Remove
                  </Button>
                </div>
              ))}
              <Button
                size="sm"
                disabled={def.indicators.length >= 12}
                onClick={() => {
                  let n = def.indicators.length + 1;
                  while (def.indicators.some((x) => x.id === `ind${n}`)) n++;
                  update({ indicators: [...def.indicators, { id: `ind${n}`, type: "ema", period: 20, source: "close" }] });
                }}
              >
                Add indicator
              </Button>
            </div>
          </Panel>

          <Panel title="Entry and exit rules" className="xl:col-span-2">
            <p className="mb-3 text-xs text-fg-faint">Signals are evaluated on candle close. Orders fill at the next candle&apos;s open plus slippage.</p>
            <div className="grid gap-5 lg:grid-cols-2">
              {sides.map((side) => (
                <div key={side} className="space-y-4">
                  <RuleEditor title={`Entry ${side}`} condition={def.entry[side]} indicators={def.indicators} onChange={(c) => update({ entry: { ...def.entry, [side]: c } })} />
                  <RuleEditor title={`Exit ${side}`} condition={def.exit[side]} indicators={def.indicators} onChange={(c) => update({ exit: { ...def.exit, [side]: c } })} />
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Risk management">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Stop loss">
                {(id) => (
                  <Select
                    id={id}
                    value={rm.stop_loss.type}
                    options={[
                      { value: "none", label: "None" },
                      { value: "percent", label: "Percent of entry" },
                      { value: "atr", label: "ATR multiple" },
                    ]}
                    onChange={(e) =>
                      update({
                        risk_management: {
                          ...rm,
                          stop_loss: { type: e.target.value as "none", value: e.target.value === "none" ? 0 : rm.stop_loss.value || (e.target.value === "atr" ? 2 : 2), atr_indicator: e.target.value === "atr" ? (atrs[0]?.id ?? null) : null },
                        },
                      })
                    }
                  />
                )}
              </Field>
              {rm.stop_loss.type !== "none" && (
                <Field label={rm.stop_loss.type === "percent" ? "Stop distance (%)" : "ATR multiple"} hint={rm.stop_loss.type === "atr" && atrs.length === 0 ? "Add an ATR indicator first." : undefined}>
                  {(id) => (
                    <Input id={id} type="number" step="any" min={0} value={rm.stop_loss.value} onChange={(e) => update({ risk_management: { ...rm, stop_loss: { ...rm.stop_loss, value: numOr(e.target.value, 0) } } })} />
                  )}
                </Field>
              )}
              {rm.stop_loss.type === "atr" && atrs.length > 1 && (
                <Field label="ATR indicator for stop">
                  {(id) => (
                    <Select id={id} value={rm.stop_loss.atr_indicator ?? ""} options={atrs.map((a) => ({ value: a.id, label: a.id }))} onChange={(e) => update({ risk_management: { ...rm, stop_loss: { ...rm.stop_loss, atr_indicator: e.target.value } } })} />
                  )}
                </Field>
              )}
              <Field label="Take profit">
                {(id) => (
                  <Select
                    id={id}
                    value={rm.take_profit.type}
                    options={[
                      { value: "none", label: "None" },
                      { value: "percent", label: "Percent of entry" },
                      { value: "atr", label: "ATR multiple" },
                      { value: "r_multiple", label: "Multiple of stop distance (R)" },
                    ]}
                    onChange={(e) =>
                      update({
                        risk_management: {
                          ...rm,
                          take_profit: { type: e.target.value as "none", value: e.target.value === "none" ? 0 : rm.take_profit.value || 2, atr_indicator: e.target.value === "atr" ? (atrs[0]?.id ?? null) : null },
                        },
                      })
                    }
                  />
                )}
              </Field>
              {rm.take_profit.type !== "none" && (
                <Field label={{ percent: "Target distance (%)", atr: "ATR multiple", r_multiple: "R multiple", none: "" }[rm.take_profit.type]} hint={rm.take_profit.type === "r_multiple" && rm.stop_loss.type === "none" ? "Needs a stop loss." : undefined}>
                  {(id) => (
                    <Input id={id} type="number" step="any" min={0} value={rm.take_profit.value} onChange={(e) => update({ risk_management: { ...rm, take_profit: { ...rm.take_profit, value: numOr(e.target.value, 0) } } })} />
                  )}
                </Field>
              )}
              <Field label="Max candles in trade" hint="Empty means no time limit.">
                {(id) => (
                  <Input
                    id={id}
                    type="number"
                    min={1}
                    value={rm.max_bars_in_trade ?? ""}
                    onChange={(e) => update({ risk_management: { ...rm, max_bars_in_trade: e.target.value === "" ? null : Math.round(numOr(e.target.value, 1)) } })}
                  />
                )}
              </Field>
            </div>
          </Panel>

          <Panel title="Position sizing and costs">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Sizing">
                {(id) => (
                  <Select
                    id={id}
                    value={def.position_sizing.type}
                    options={[
                      { value: "fixed_fraction", label: "Fixed fraction of equity" },
                      { value: "risk_percent", label: "Risk % of equity per trade" },
                    ]}
                    onChange={(e) =>
                      update({ position_sizing: e.target.value === "risk_percent" ? { type: "risk_percent", fraction: def.position_sizing.fraction, risk_percent: def.position_sizing.risk_percent ?? 1 } : { type: "fixed_fraction", fraction: def.position_sizing.fraction } })
                    }
                  />
                )}
              </Field>
              <Field label="Max fraction of equity" hint="1 = 100 %, no leverage.">
                {(id) => (
                  <Input id={id} type="number" step="0.05" min={0.01} max={1} value={def.position_sizing.fraction} onChange={(e) => update({ position_sizing: { ...def.position_sizing, fraction: numOr(e.target.value, 1) } })} />
                )}
              </Field>
              {def.position_sizing.type === "risk_percent" && (
                <Field label="Risk per trade (%)" hint={rm.stop_loss.type === "none" ? "Needs a stop loss." : "Loss at the stop, before slippage."}>
                  {(id) => (
                    <Input id={id} type="number" step="0.1" min={0.01} max={10} value={def.position_sizing.risk_percent ?? 1} onChange={(e) => update({ position_sizing: { ...def.position_sizing, risk_percent: numOr(e.target.value, 1) } })} />
                  )}
                </Field>
              )}
              <Field label="Fee (bps per fill)" hint="10 bps = 0.10 %">
                {(id) => <Input id={id} type="number" step="0.5" min={0} max={100} value={def.costs.fee_bps} onChange={(e) => update({ costs: { ...def.costs, fee_bps: numOr(e.target.value, 0) } })} />}
              </Field>
              <Field label="Slippage (bps per fill)">
                {(id) => <Input id={id} type="number" step="0.5" min={0} max={200} value={def.costs.slippage_bps} onChange={(e) => update({ costs: { ...def.costs, slippage_bps: numOr(e.target.value, 0) } })} />}
              </Field>
            </div>
          </Panel>
        </div>
      )}

      {extraFields}

      {check && !check.valid && (
        <Notice tone="negative" title="The strategy is not valid yet">
          <ul className="list-disc pl-4 text-xs">
            {check.issues.map((i, k) => (
              <li key={k}>
                {i.path && <code className="text-fg-muted">{i.path}: </code>}
                {i.message}
              </li>
            ))}
          </ul>
        </Notice>
      )}
      {check?.valid && (
        <Notice tone="positive">
          Valid. Warm-up {check.warmup_bars} candles · hash <Hash value={check.canonical_hash} />
        </Notice>
      )}
      {saveError ? <Notice tone="negative">{errorMessage(saveError)}</Notice> : null}

      <div className="flex flex-wrap gap-2">
        <Button variant="primary" onClick={() => void save()} loading={saving}>
          {saveLabel}
        </Button>
        <Button onClick={() => void validate(tab === "json" ? safeParse(jsonText, def) : def)} loading={checking}>
          Validate
        </Button>
      </div>
    </div>
  );
}

function safeParse(text: string, fallback: StrategyDefinition): StrategyDefinition {
  try {
    return JSON.parse(text) as StrategyDefinition;
  } catch {
    return fallback;
  }
}
