import type { Compare, Condition, Indicator, Operand, StrategyDefinition } from "./types";

export const INDICATOR_TYPES = [
  { value: "ema", label: "EMA", help: "Exponential moving average" },
  { value: "sma", label: "SMA", help: "Simple moving average" },
  { value: "rsi", label: "RSI", help: "Relative Strength Index (Wilder)" },
  { value: "atr", label: "ATR", help: "Average True Range (Wilder)" },
  { value: "highest", label: "Highest high", help: "Highest high of the previous N candles" },
  { value: "lowest", label: "Lowest low", help: "Lowest low of the previous N candles" },
  { value: "volume_sma", label: "Volume SMA", help: "Average volume" },
];

export const OPERATORS: { value: Compare["op"]; label: string }[] = [
  { value: "crosses_above", label: "crosses above" },
  { value: "crosses_below", label: "crosses below" },
  { value: "gt", label: ">" },
  { value: "gte", label: "≥" },
  { value: "lt", label: "<" },
  { value: "lte", label: "≤" },
];

export const PRICE_FIELDS = ["close", "open", "high", "low", "volume"] as const;

export function emptyDefinition(): StrategyDefinition {
  return {
    schema_version: "1.0",
    name: "New strategy",
    description: "",
    symbols: ["BTCUSDT"],
    timeframe: "1h",
    market_type: "spot",
    direction: "long",
    indicators: [],
    entry: { long: null },
    exit: {},
    risk_management: { stop_loss: { type: "none", value: 0 }, take_profit: { type: "none", value: 0 }, max_bars_in_trade: null },
    position_sizing: { type: "fixed_fraction", fraction: 1 },
    execution: { fill_model: "next_open" },
    costs: { fee_bps: 10, slippage_bps: 5 },
  };
}

export const TEMPLATES: { id: string; name: string; description: string; build: () => StrategyDefinition }[] = [
  {
    id: "ema_cross",
    name: "EMA crossover",
    description: "Long when the fast EMA crosses above the slow EMA, exit on the opposite cross. ATR stop, 2R target.",
    build: () => ({
      ...emptyDefinition(),
      name: "EMA 20/50 crossover",
      indicators: [
        { id: "fast", type: "ema", period: 20, source: "close" },
        { id: "slow", type: "ema", period: 50, source: "close" },
        { id: "atr14", type: "atr", period: 14, source: "close" },
      ],
      entry: { long: { op: "crosses_above", left: { ind: "fast" }, right: { ind: "slow" } } },
      exit: { long: { op: "crosses_below", left: { ind: "fast" }, right: { ind: "slow" } } },
      risk_management: { stop_loss: { type: "atr", value: 2, atr_indicator: "atr14" }, take_profit: { type: "r_multiple", value: 2 }, max_bars_in_trade: null },
      position_sizing: { type: "risk_percent", fraction: 1, risk_percent: 1 },
    }),
  },
  {
    id: "rsi_reversion",
    name: "RSI mean reversion",
    description: "Long when RSI crosses back above 30 in an uptrend (close above EMA 200). Exit when RSI is above 60.",
    build: () => ({
      ...emptyDefinition(),
      name: "RSI reversion in uptrend",
      indicators: [
        { id: "rsi14", type: "rsi", period: 14, source: "close" },
        { id: "trend", type: "ema", period: 200, source: "close" },
        { id: "atr14", type: "atr", period: 14, source: "close" },
      ],
      entry: {
        long: {
          all: [
            { op: "crosses_above", left: { ind: "rsi14" }, right: { value: 30 } },
            { op: "gt", left: { price: "close" }, right: { ind: "trend" } },
          ],
        },
      },
      exit: { long: { op: "gt", left: { ind: "rsi14" }, right: { value: 60 } } },
      risk_management: { stop_loss: { type: "atr", value: 2.5, atr_indicator: "atr14" }, take_profit: { type: "none", value: 0 }, max_bars_in_trade: 48 },
      position_sizing: { type: "risk_percent", fraction: 1, risk_percent: 1 },
    }),
  },
  {
    id: "breakout",
    name: "Range breakout",
    description: "Long when the close breaks above the highest high of the previous 40 candles with above-average volume.",
    build: () => ({
      ...emptyDefinition(),
      name: "40-bar breakout",
      indicators: [
        { id: "hi40", type: "highest", period: 40, source: "close" },
        { id: "vol20", type: "volume_sma", period: 20, source: "close" },
        { id: "atr14", type: "atr", period: 14, source: "close" },
      ],
      entry: {
        long: {
          all: [
            { op: "gt", left: { price: "close" }, right: { ind: "hi40" } },
            { op: "gt", left: { price: "volume" }, right: { ind: "vol20" } },
          ],
        },
      },
      exit: {},
      risk_management: { stop_loss: { type: "atr", value: 2, atr_indicator: "atr14" }, take_profit: { type: "r_multiple", value: 3 }, max_bars_in_trade: 96 },
      position_sizing: { type: "risk_percent", fraction: 1, risk_percent: 1 },
    }),
  },
];

/** Flatten a condition into a list of comparisons plus a combiner, if it has that simple shape. */
export function toRules(c: Condition | null | undefined): { mode: "all" | "any"; rules: Compare[] } | null {
  if (!c) return { mode: "all", rules: [] };
  if ("op" in c) return { mode: "all", rules: [c] };
  if ("all" in c && c.all.every((x) => "op" in x)) return { mode: "all", rules: c.all as Compare[] };
  if ("any" in c && c.any.every((x) => "op" in x)) return { mode: "any", rules: c.any as Compare[] };
  return null; // nested shapes are edited in the JSON tab
}

export function fromRules(mode: "all" | "any", rules: Compare[]): Condition | null {
  if (rules.length === 0) return null;
  if (rules.length === 1) return rules[0];
  return mode === "all" ? { all: rules } : { any: rules };
}

export function operandLabel(o: Operand, indicators: Indicator[]): string {
  if ("ind" in o) {
    const i = indicators.find((x) => x.id === o.ind);
    return i ? `${i.type.toUpperCase()}(${i.period})` : o.ind;
  }
  if ("price" in o) return o.price;
  return String(o.value);
}

export function describeCondition(c: Condition | null | undefined, ind: Indicator[]): string {
  if (!c) return "—";
  if ("op" in c) {
    const op = OPERATORS.find((x) => x.value === c.op)?.label ?? c.op;
    return `${operandLabel(c.left, ind)} ${op} ${operandLabel(c.right, ind)}`;
  }
  if ("all" in c) return c.all.map((x) => describeCondition(x, ind)).join(" AND ");
  if ("any" in c) return `(${c.any.map((x) => describeCondition(x, ind)).join(" OR ")})`;
  return `NOT (${describeCondition(c.not, ind)})`;
}

/** Remove empty optional parts before sending to the API. */
export function cleanDefinition(d: StrategyDefinition): StrategyDefinition {
  const entry = Object.fromEntries(Object.entries(d.entry).filter(([, v]) => v)) as StrategyDefinition["entry"];
  const exit = Object.fromEntries(Object.entries(d.exit).filter(([, v]) => v)) as StrategyDefinition["exit"];
  const rm = { ...d.risk_management };
  if (!rm.max_bars_in_trade) delete rm.max_bars_in_trade;
  const ps = { ...d.position_sizing };
  if (ps.type !== "risk_percent") delete ps.risk_percent;
  return { ...d, entry, exit, risk_management: rm, position_sizing: ps };
}
