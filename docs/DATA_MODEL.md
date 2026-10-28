# Datenmodell

Alle IDs sind UUID-Strings, Zeitstempel in UTC. Kerzenzeiten sind Millisekunden seit Epoch (Open-Time). Schema: `backend/app/models/__init__.py`, Migration: `backend/migrations/versions/`.

| Tabelle | Zweck | Wichtige Felder / Constraints |
|---|---|---|
| `users` | Konten | `email` unique, `password_hash` (scrypt), `preferences` JSON |
| `auth_sessions` | Login-Sessions | `token_hash` (SHA-256) unique, `expires_at` |
| `audit_logs` | Nachvollziehbarkeit | `action`, `entity_type`, `entity_id`, `detail` |
| `strategies` | Strategie-Kopf | `origin` (manual/imported/discovery/ai), `status` (active/archived), `current_version_id` |
| `strategy_versions` | **unveränderliche** Versionen | `definition_json`, `canonical_hash`, unique (`strategy_id`, `version_number`); ORM-Hook verhindert Updates |
| `market_data_sources` | Datenreihe pro Symbol/Timeframe/Provider | `revision`, `fingerprint`, `row_count`, `is_synthetic`, `metadata` (Lücken), unique (`owner_id`, `provider`, `symbol`, `timeframe`) |
| `candles` | OHLCV | PK (`source_id`, `open_time`), `revision` |
| `jobs` | Job-Queue | `kind`, `target_id`, `status`, Fortschritt, `cancel_requested`, Fehler |
| `backtest_runs` | Backtest inkl. Reproduzierbarkeitsdaten | Version, Quelle, `data_revision`, `data_fingerprint`, Kosten-/Ausführungsmodell, `engine_version`, `result_json` |
| `backtest_metrics` | Kennzahlen einzeln abfragbar | unique (`backtest_run_id`, `metric_name`), `note` bei undefinierten Werten |
| `backtest_trades` | Trades | unique (`backtest_run_id`, `sequence`), Kosten getrennt (Gebühren, Slippage, Funding = null) |
| `validation_runs` | Out-of-Sample-Berichte | `configuration`, `segments`, `metrics`, `warnings` |
| `discovery_jobs` / `discovery_candidates` | Suche und Kandidaten | unique (`discovery_job_id`, `candidate_hash`), `status`, `rejection_reason`, `flags`, `score`, `score_parts` |
| `journal_trades` / `journal_imports` | Eigene Trades | `source_type` (manual/csv/tradingview), `dedupe_key`, `realized_pnl` (null = wird aus Preisen berechnet, falls möglich) |
| `paper_sessions` | Replay-Sessions | `cursor_index`, `state_json` (Simulatorzustand), `equity_curve` |
| `paper_orders` / `paper_fills` | Orders und Fills | unique (`session_id`, `idempotency_key`) – mehrfaches Verarbeiten erzeugt keine Dubletten |
| `paper_positions` | Aktuelle Position | unique (`session_id`) |
| `webhook_tokens` | TradingView-Secret | nur `token_hash` + `hint` gespeichert |
| `tradingview_alerts` | Eingegangene Alerts | unique (`owner_id`, `event_id`), `journal_trade_id` |
| `agent_runs` / `agent_tool_calls` | KI-Läufe und jeder Tool-Aufruf | Status, strukturierte Ausgabe, Token-Nutzung |

Löschen von Strategien ist bewusst nicht vorgesehen (Archivieren), damit Backtests ihre Version behalten.
