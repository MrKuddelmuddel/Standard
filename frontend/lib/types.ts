// Types mirroring the backend API (see backend/app/schemas and docs/API.md).

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export type User = { id: string; email: string; created_at: string; preferences: Record<string, unknown> };

export type JobInfo = {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress_current: number | null;
  progress_total: number | null;
  error_code: string | null;
  error_message: string | null;
  cancel_requested: boolean;
} | null;

export type Operand = { ind: string } | { price: "open" | "high" | "low" | "close" | "volume" } | { value: number };
export type Compare = { op: "gt" | "lt" | "gte" | "lte" | "crosses_above" | "crosses_below"; left: Operand; right: Operand };
export type Condition = Compare | { all: Condition[] } | { any: Condition[] } | { not: Condition };

export type Indicator = { id: string; type: string; period: number; source?: string };

export type StrategyDefinition = {
  schema_version: "1.0";
  name: string;
  description?: string;
  symbols: string[];
  timeframe: string;
  market_type: "spot" | "futures_sim";
  direction: "long" | "short" | "long_short";
  indicators: Indicator[];
  entry: { long?: Condition | null; short?: Condition | null };
  exit: { long?: Condition | null; short?: Condition | null };
  risk_management: {
    stop_loss: { type: "none" | "percent" | "atr"; value: number; atr_indicator?: string | null };
    take_profit: { type: "none" | "percent" | "atr" | "r_multiple"; value: number; atr_indicator?: string | null };
    max_bars_in_trade?: number | null;
  };
  position_sizing: { type: "fixed_fraction" | "risk_percent"; fraction: number; risk_percent?: number | null };
  execution: { fill_model: "next_open" };
  costs: { fee_bps: number; slippage_bps: number };
};

export type Version = {
  id: string;
  strategy_id: string;
  version_number: number;
  schema_version: string;
  definition_json: StrategyDefinition;
  canonical_hash: string;
  note: string;
  created_at: string;
};

export type Strategy = {
  id: string;
  name: string;
  description: string;
  origin: "manual" | "imported" | "discovery" | "ai";
  status: "active" | "archived";
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
  current_version: Version | null;
  version_count: number;
  last_backtest: { id: string; status: string; created_at: string; net_return: number | null } | null;
};

export type Source = {
  id: string;
  provider: string;
  exchange: string;
  market_type: string;
  symbol: string;
  timeframe: string;
  status: string;
  is_synthetic: boolean;
  revision: number;
  fingerprint: string | null;
  row_count: number;
  first_time: number | null;
  last_time: number | null;
  meta: { gap_count?: number; gaps?: { after: number; before: number; missing_bars: number }[]; last_import?: Record<string, unknown>; note?: string };
  created_at: string;
  updated_at: string;
};

export type Metrics = Record<string, number | null>;

export type Backtest = {
  id: string;
  strategy_version_id: string;
  market_data_source_id: string;
  data_revision: number;
  data_fingerprint: string | null;
  start_time: number | null;
  end_time: number | null;
  initial_capital: number;
  fee_model: { type: string; fee_bps: number };
  slippage_model: { type: string; slippage_bps: number; applies_to?: string };
  execution_model_version: string;
  engine_version: string;
  config_json: Record<string, unknown>;
  is_synthetic_data: boolean;
  status: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_code: string | null;
  error_message: string | null;
  metrics: Metrics | null;
  result: {
    metrics: Metrics;
    metric_notes: Record<string, string>;
    warnings: string[];
    curve: [number, number, number][];
    curve_columns: string[];
  } | null;
  strategy: { id: string; name: string; version_number: number } | null;
  job: JobInfo;
};

export type Trade = {
  sequence: number;
  side: string;
  entry_time: number;
  exit_time: number;
  entry_price: number;
  exit_price: number;
  quantity: number;
  gross_pnl: number;
  fees: number;
  slippage_cost: number;
  funding_cost: number | null;
  net_pnl: number;
  exit_reason: string;
  meta: { bars_held?: number; r_multiple?: number | null; return_pct?: number; stop?: number | null; target?: number | null };
};

export type SplitMetrics = Record<string, number | null> & { error?: string; message?: string };

export type Validation = {
  id: string;
  strategy_version_id: string;
  market_data_source_id: string;
  data_fingerprint: string | null;
  method: string;
  configuration: Record<string, number>;
  segments: { name: string; start_time: number; end_time: number; bars: number }[] | null;
  metrics: {
    splits: Record<string, SplitMetrics>;
    walk_forward: (SplitMetrics & { name: string; start_time: number; end_time: number; bars: number })[];
    walk_forward_summary?: { folds_with_trades: number; profitable_folds: number; note: string };
    cost_sensitivity: { multiplier: number; base: SplitMetrics; stressed: SplitMetrics };
    parameter_stability: (SplitMetrics & { change: string })[];
    parameter_stability_summary?: { neighbours: number; sign_flips: number };
  } | null;
  warnings: string[] | null;
  is_synthetic_data: boolean;
  status: string;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
};

export type Discovery = {
  id: string;
  market_data_source_id: string;
  data_fingerprint: string | null;
  search_config: Record<string, unknown>;
  status: string;
  candidate_count: number;
  report: {
    generated: number;
    duplicates_removed: number;
    tested: number;
    stopped_early: string | null;
    segments: { name: string; start_time: number; end_time: number; bars: number }[];
    ranking_version: string;
    status_counts: Record<string, number>;
    note: string;
    warning?: string;
  } | null;
  is_synthetic_data: boolean;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_code: string | null;
  error_message: string | null;
  job: JobInfo;
};

export type Candidate = {
  id: string;
  template: string;
  name: string;
  candidate_hash: string;
  definition_json: StrategyDefinition;
  status: "generated" | "rejected" | "shortlisted" | "validated";
  rejection_reason: string | null;
  metrics: { train: SplitMetrics; validation: SplitMetrics; test: SplitMetrics; validation_2x_costs: SplitMetrics };
  flags: string[];
  score: number | null;
  score_parts: Record<string, number>;
  strategy_version_id: string | null;
};

export type JournalTrade = {
  id: string;
  source_type: string;
  external_id: string | null;
  symbol: string;
  market_type: string;
  side: "long" | "short";
  entry_time: string;
  exit_time: string | null;
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  fees: number;
  realized_pnl: number | null;
  pnl_is_computed: boolean;
  strategy_id: string | null;
  setup: string;
  tags: string[];
  notes: string;
  emotions: string | null;
  rule_compliance: boolean | null;
  created_at: string;
};

export type JournalStats = {
  trades: number;
  closed_with_pnl: number;
  open_or_incomplete: number;
  by_source: Record<string, number>;
  net_pnl: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  expectancy: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  note: string;
};

export type PaperSession = {
  id: string;
  name: string;
  strategy_version_id: string;
  market_data_source_id: string;
  data_fingerprint: string;
  mode: string;
  status: "created" | "running" | "paused" | "stopped" | "completed";
  initial_capital: number;
  config_json: { fee_bps: number; slippage_bps: number; auto_advance: boolean; mode_note?: string };
  start_index: number;
  end_index: number;
  cursor_index: number;
  equity: number;
  is_synthetic_data: boolean;
  created_at: string;
  updated_at: string;
  position: { side: string; quantity: number; entry_price: number | null; stop: number | null; target: number | null; unrealized_pnl: number } | null;
  progress: { processed: number; total: number } | null;
  current_time: number | null;
};

export type PaperDetail = PaperSession & {
  equity_curve: [number, number][];
  orders: { id: string; bar_time: number; side: string; intent: string; order_type: string; quantity: number; status: string; reason: string | null }[];
  fills: { id: string; order_id: string; bar_time: number; price: number; ref_price: number; quantity: number; fee: number }[];
  audit: { action: string; created_at: string }[];
};

export type AgentRun = {
  id: string;
  kind: "research" | "explanation";
  task: string;
  provider: string;
  model: string | null;
  status: string;
  structured_output: {
    hypothesis?: string;
    definition?: StrategyDefinition;
    unsupported_requests?: string[];
    assumptions?: string[];
    suggested_tests?: string[];
    symbol?: string;
    timeframe?: string;
  } | null;
  report: {
    summary?: string;
    observations?: string[];
    interpretation?: string[];
    risks_and_limitations?: string[];
    next_tests?: string[];
    backtest_id?: string;
    validation_run_id?: string;
  } | null;
  usage: { input_tokens?: number; output_tokens?: number; model_calls?: number; estimated_cost_usd?: number | null; cost_note?: string };
  strategy_id: string | null;
  backtest_run_id: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  job: JobInfo;
  tool_calls?: { sequence: number; tool_name: string; arguments: Record<string, unknown>; result: Record<string, unknown> | null; is_error: boolean; duration_ms: number }[];
};

export type Overview = {
  counts: { strategies: number; backtests: number; discoveries: number; active_paper_sessions: number; journal_trades: number; data_sources: number };
  recent_backtests: { id: string; status: string; created_at: string; strategy: string | null; is_synthetic_data: boolean; net_return: number | null; trade_count: number | null }[];
  recent_discoveries: { id: string; status: string; created_at: string; candidate_count: number; job: JobInfo }[];
  last_journal_activity: string | null;
  data_status: { id: string; symbol: string; timeframe: string; provider: string; is_synthetic: boolean; rows: number; first_time: number | null; last_time: number | null; gap_count: number }[];
  ai_configured: boolean;
};
