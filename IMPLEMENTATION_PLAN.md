# NEXUS QUANT – Implementierungsplan

Stand wird während der Arbeit aktualisiert. Legende: [x] erledigt und getestet, [~] teilweise, [ ] offen.

## Ausgangslage (Phase 0)

- Branch `claude/nexus-quant`, abgeleitet vom Backtest-Labor (`legacy/backtest-lab/`, unverändert lauffähig).
- Umgebung: Python 3.13, Node 22, uv, PostgreSQL-Binaries, Redis-Binary, Docker-Client, Chromium/Playwright.
- Netzwerk: Paketregistries erreichbar, Börsen-APIs gesperrt (HTTP 403 über Proxy). Echte Marktdaten können hier nicht abgerufen werden.

## Phasen

### Phase 0 – Inspektion und Plan
- [x] Repository und Tools geprüft
- [x] IMPLEMENTATION_PLAN.md, DECISIONS.md, KNOWN_LIMITATIONS.md

### Phase 1 – Projekt läuft
- [ ] Backend (FastAPI) mit Healthcheck, Konfiguration, strukturierten Logs
- [ ] Frontend (Next.js, TypeScript, Tailwind) mit Dark-Designsystem und Navigation
- [ ] docker-compose.yml, .env.example, README mit Startbefehlen

### Phase 2 – Datenmodell und Auth
- [ ] SQLAlchemy-Modelle, Alembic-Migration
- [ ] Registrierung/Login mit scrypt-Hashes und HttpOnly-Session-Cookie
- [ ] Owner-Isolation, Strategie-CRUD, unveränderliche Versionen

### Phase 3 – Daten und Backtesting
- [ ] Kerzen-Import (CSV), synthetische Demo-Daten (markiert), Binance-Adapter (gemockt getestet)
- [ ] Strategy-DSL mit Validierung, kanonischem Hash
- [ ] Engine: Next-Open-Fills, Gebühren, Slippage, SL/TP konservativ, Long/Short (Short nur Futures-Simulation)
- [ ] Metriken mit dokumentierten Edge Cases
- [ ] API + UI für Backtests, Equity/Drawdown, Trade-Tabelle

### Phase 4 – Validierung
- [ ] Chronologische Splits, OOS, Walk-forward, Kosten-Sensitivität, Parameter-Stabilität, Warnungen

### Phase 5 – Discovery
- [ ] Suchraum aus Vorlagen, Deduplizierung, Rejection Reasons, Ranking v1, Hintergrundjobs mit Abbruch

### Phase 6 – Journal und Paper Trading
- [ ] Journal-CRUD, CSV-Import mit Vorschau/Mapping/Dubletten, Kennzahlen
- [ ] Paper-Sessions als Historical Replay mit idempotenten Orders/Fills, Audit

### Phase 7 – AI Research
- [ ] Provider-Abstraktion, Research Agent mit begrenzten Tools, Logs, Limits, Fallback ohne Key

### Phase 8 – Stabilisierung
- [ ] TradingView-Webhook, Security-Review, E2E-Workflow, Dokumentation

## Nächste Schritte
Siehe offene Punkte oben.
