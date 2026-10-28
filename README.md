# NEXUS QUANT

Krypto-Trading-Intelligence als lauffähiges MVP: Strategien regelbasiert bauen, versionieren, mit realistischen Kosten backtesten, out-of-sample validieren, systematisch suchen (Discovery), im Paper Trading nachspielen und eigene Trades im Journal auswerten. Optional formuliert ein KI-Assistent Strategieentwürfe aus Text.

**Analyse- und Simulationswerkzeug. Keine echten Orders, kein Live-Trading, keine Anlageberatung.** Vergangene Ergebnisse sagen nichts über zukünftige Renditen.

## Was funktioniert

| Bereich | Stand |
|---|---|
| Auth | Registrierung/Login, scrypt-Hashes, HttpOnly-Session-Cookie, CSRF-Header, Owner-Isolation |
| Marktdaten | CSV-Import (idempotent, Revisionen, Fingerprint, Lückenerkennung), Binance-Spot-Adapter (öffentliche Klines), synthetische Demo-Daten (überall markiert) |
| Strategy Lab | Builder mit Vorlagen, Regel-Editor, JSON-Modus, serverseitige Validierung, unveränderliche Versionen mit Hash, Versionsvergleich, Export/Import, Duplizieren, Archivieren |
| Backtesting | Engine `next_open_v1` (Signal am Close, Fill am nächsten Open, Gebühren + Slippage, Stop vor Target), Equity/Drawdown, Trade-Liste, Kennzahlen mit Bootstrap-Intervall, volle Reproduzierbarkeit |
| Validierung | Chronologische Splits, Walk-forward ohne Re-Optimierung, Kosten-Stresstest, Parameter-Nachbarn (±20 %), Warnungen |
| Discovery | Raster über Vorlagen, Deduplizierung per Hash, Ablehnungsgründe, Ranking nur auf Validierungsdaten, Testsegment nur für validierte Kandidaten, Abbruch/Zeitlimit |
| Journal | Manuelle Trades, CSV-Import mit Vorschau/Mapping/Dubletten, Filter, Kennzahlen |
| Paper Trading | Historical Replay mit demselben Simulator, idempotente Orders/Fills, Start/Pause/Stop, Audit-Log |
| TradingView | Webhook mit Secret, Dubletten- und Zeitprüfung, Alert → Journal |
| AI Research | Optional (Anthropic). Begrenzter Tool-Loop, Bestätigung vor jeder Aktion, Tool-Call-Log, Tageslimit. Ohne Key: klarer Hinweis, Rest funktioniert |

Details: [docs/](docs/) · Grenzen: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) · Entscheidungen: [DECISIONS.md](DECISIONS.md)

## Schnellstart lokal (ohne Docker)

Voraussetzungen: Python 3.12+ (getestet mit 3.13), Node 22.

```bash
# Backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"            # optional: ".[dev,ai]" für AI Research
uvicorn app.main:app --port 8000   # SQLite unter backend/data/, Migrationen laufen in NEXUS_ENV=dev automatisch

# Frontend (zweites Terminal)
cd frontend
npm ci
npm run dev                        # http://localhost:3000, /api/v1 wird an 127.0.0.1:8000 weitergeleitet
```

Dann im Browser: Konto anlegen → **Settings → Market data** (CSV hochladen, Binance abrufen oder synthetische Demo-Daten erzeugen) → **Strategy Lab → New strategy** → **Run backtest**.

## Mit Docker Compose (PostgreSQL, API, Worker, Web)

```bash
cp .env.example .env               # POSTGRES_PASSWORD setzen
docker compose up --build          # http://localhost:3000
```

Der Dienst `migrate` führt `alembic upgrade head` aus, bevor API und Worker starten. Alle Dienste haben Healthchecks.

## Tests und Checks

```bash
cd backend && pytest -o addopts="" && ruff check . && ruff format --check . && mypy app quant
cd frontend && npx next typegen && npx tsc --noEmit && npm run lint && npm run build

# End-to-End (API mit JOBS_MODE=thread und Web laufen lokal; Playwright mit Chromium installiert)
node e2e/workflow.mjs ./screenshots
```

Der E2E-Lauf deckt ab: Registrierung → Demo-Daten → Strategie anlegen → Backtest → Ergebnis und Trade-Liste → neue Version speichern → Validierung → Paper-Session → Journal-Eintrag → Discovery → Overview. CI: [.github/workflows/ci.yml](.github/workflows/ci.yml).

## Umgebungsvariablen

Vollständige Liste mit Kommentaren in [.env.example](.env.example). Die wichtigsten:

| Variable | Standard | Zweck |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/nexus.db` | SQLite oder `postgresql+psycopg://…` |
| `NEXUS_ENV` | `dev` | `dev` migriert SQLite beim Start automatisch; `prod` nie |
| `JOBS_MODE` | `thread` | `thread` = Worker im API-Prozess, `external` = `python -m app.workers.runner` |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Erlaubte Origins (JSON-Liste) |
| `COOKIE_SECURE` | `false` | Hinter HTTPS auf `true` |
| `API_ORIGIN` | `http://127.0.0.1:8000` | Ziel des Next.js-Proxys für `/api/v1` |
| `AI_PROVIDER` / `ANTHROPIC_API_KEY` | `none` / leer | AI Research aktivieren |

## Projektstruktur

```
backend/
  quant/        reines Python-Paket: Daten, Strategy-DSL, Indikatoren, Engine, Metriken, Validierung, Discovery
  app/          FastAPI: Konfiguration, Modelle, Schemas, Services, Router, Worker
  migrations/   Alembic
  tests/        pytest (Engine, Kern, API)
frontend/       Next.js 16 (App Router), React 19, Tailwind 4, eigene SVG-Charts
e2e/            Playwright-Workflow
docs/           Architektur, Datenmodell, Schema, Backtesting, Discovery, API, Security, Roadmap
legacy/         früheres Backtest-Labor (unverändert lauffähig)
```
