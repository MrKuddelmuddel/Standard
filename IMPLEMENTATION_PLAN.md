# NEXUS QUANT – Implementierungsplan

Legende: [x] erledigt und getestet, [~] teilweise, [ ] offen.

## Ausgangslage (Phase 0)

- Branch `claude/nexus-quant`, abgeleitet vom Backtest-Labor (`legacy/backtest-lab/`, unverändert lauffähig).
- Umgebung: Python 3.13, Node 22, PostgreSQL-Binaries, Docker-Client, Chromium/Playwright.
- Netzwerk: Paketregistries erreichbar, Börsen-APIs gesperrt (HTTP 403 über Proxy). Echte Marktdaten konnten hier nicht abgerufen werden.

## Phasen

### Phase 0 – Inspektion und Plan
- [x] Repository und Tools geprüft
- [x] IMPLEMENTATION_PLAN.md, DECISIONS.md, KNOWN_LIMITATIONS.md

### Phase 1 – Projekt läuft
- [x] Backend (FastAPI) mit Healthcheck, Konfiguration, strukturierten JSON-Logs, Request-IDs
- [x] Frontend (Next.js 16, TypeScript, Tailwind 4) mit Dark-Designsystem, Navigation, Empty/Loading/Error-States
- [~] docker-compose.yml (Postgres, Migrate, API, Worker, Web, Healthchecks), .env.example, README – Compose-Config validiert, Image-Build in dieser Umgebung nicht möglich (siehe KNOWN_LIMITATIONS)

### Phase 2 – Datenmodell und Auth
- [x] SQLAlchemy-Modelle, Alembic-Migration (SQLite und PostgreSQL: upgrade/check/downgrade/upgrade)
- [x] Registrierung/Login mit scrypt-Hashes und HttpOnly-Session-Cookie, CSRF-Header
- [x] Owner-Isolation, Strategie-CRUD, unveränderliche Versionen, Export/Import, Versionsvergleich

### Phase 3 – Daten und Backtesting
- [x] CSV-Import, synthetische Demo-Daten (markiert), Binance-Adapter (gemockt getestet)
- [x] Strategy-DSL mit Validierung und kanonischem Hash
- [x] Engine: Next-Open-Fills, Gebühren, Slippage, SL/TP konservativ, Long/Short (Short nur Futures-Simulation)
- [x] Metriken mit dokumentierten Edge Cases und Bootstrap-Intervall
- [x] API + UI: Backtest starten, Fortschritt, Equity/Drawdown, Trade-Tabelle, Reproduzierbarkeit

### Phase 4 – Validierung
- [x] Chronologische Splits, Walk-forward ohne Re-Optimierung, Kosten-Sensitivität, Parameter-Stabilität, Warnungen, UI

### Phase 5 – Discovery
- [x] Suchraum aus Vorlagen, Deduplizierung, Rejection Reasons, Ranking v1, Hintergrundjobs mit Abbruch, UI mit Speichern als Strategie

### Phase 6 – Journal und Paper Trading
- [x] Journal-CRUD, CSV-Import mit Vorschau/Mapping/Dubletten, Kennzahlen, Filter, UI
- [x] Paper-Sessions als Historical Replay mit idempotenten Orders/Fills, Audit, UI

### Phase 7 – AI Research
- [x] Provider-Abstraktion, Research- und Explain-Agent mit begrenzten Tools, Logs, Limits, Bestätigung, Fallback ohne Key, UI
- [ ] Echter Lauf gegen die Anthropic-API (kein Key in dieser Umgebung)

### Phase 8 – Stabilisierung
- [x] TradingView-Webhook mit Token-Rotation und Alert → Journal
- [x] E2E-Workflow (Playwright) lokal grün
- [x] Dokumentation (README, docs/, SECURITY, ROADMAP, KNOWN_LIMITATIONS)
- [~] CI-Workflow geschrieben, noch nicht auf GitHub gelaufen

## Nächste Schritte
1. Mit Netzwerkzugang echte BTC/ETH-Daten laden und die Vorlagen ehrlich validieren.
2. CI auf GitHub laufen lassen und Docker-Images bauen.
3. Funding-Rates für Futures-Simulation und Multiple-Testing-Korrektur für Discovery (siehe docs/ROADMAP.md).
