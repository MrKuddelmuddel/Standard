# Architektur

```
Browser ──► Next.js (frontend, :3000) ──/api/v1 rewrite──► FastAPI (backend/app, :8000) ──► PostgreSQL / SQLite
                                                              │            ▲
                                                              ▼            │ jobs-Tabelle (Claim per UPDATE … WHERE status='queued')
                                                         backend/quant ◄── Worker (Thread im API-Prozess oder `python -m app.workers.runner`)
```

## Schichten

- **`backend/quant`** – reines Python (NumPy). Keine Abhängigkeit zu Web oder DB. Enthält Kerzen-Container mit Fingerprint, CSV-Parser, Binance-Adapter, Strategy-DSL (Pydantic), Indikatoren, Signalberechnung, den `Simulator` (geteilt von Backtest und Paper Trading), Metriken, Validierung und Discovery. Komplett unit-getestet.
- **`backend/app`** – FastAPI. `core/` (Settings, JSON-Logs mit Redaction, Fehlerformat, Security, Rate-Limits), `models/` (SQLAlchemy 2), `schemas/` (Pydantic v2), `services/` (Geschäftslogik), `api/v1/` (Router), `workers/` (Job-Runner).
- **`frontend`** – Next.js 16 App Router, React 19, Tailwind 4. Alle Seiten sind Client-Komponenten, die über `lib/api.ts` dieselbe Origin ansprechen; Next leitet `/api/v1/*` an `API_ORIGIN` weiter. Dadurch bleibt das Session-Cookie First-Party, und der Browser braucht kein CORS.

## Hintergrundjobs

Backtests, Validierungen, Discovery und KI-Läufe werden als Zeile in `jobs` angelegt (Status `queued`). Ein Worker beansprucht einen Job atomar (`UPDATE jobs SET status='running' WHERE id=? AND status='queued'`), meldet Fortschritt, prüft `cancel_requested` und schreibt Ergebnis oder Fehler. Hängengebliebene Jobs werden nach `JOB_TIMEOUT_SECONDS` als fehlgeschlagen markiert. Pro Nutzer sind höchstens `MAX_PARALLEL_JOBS_PER_USER` Jobs gleichzeitig aktiv. Der Worker stößt außerdem Paper-Sessions mit Auto-Advance an.

`JOBS_MODE=thread` startet den Worker im API-Prozess (lokal), `external` erwartet separate Worker-Prozesse (Compose-Dienst `worker`), `inline` führt Jobs synchron aus (Tests).

## Reproduzierbarkeit

Jeder Backtest speichert: Strategieversion (unveränderlich, kanonischer SHA-256-Hash), Datenquelle mit Revision und Fingerprint der verwendeten Kerzen, Zeitfenster, Startkapital, Gebühren- und Slippage-Modell, `execution_model_version`, `engine_version` und die vollständige Konfiguration. Gleiche Eingaben ergeben gleiche Ergebnisse (Bootstrap mit festem Seed).

## Fehlerformat

Alle Fehler: `{"error": {"code", "message", "details", "request_id"}}`. Jede Antwort trägt `X-Request-ID`; Logs sind JSON mit derselben ID, Secrets werden geschwärzt.
