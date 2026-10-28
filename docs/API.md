# API (v1)

Basis: `/api/v1`. Interaktive OpenAPI-Doku: `http://localhost:8000/api/docs` (nicht in `NEXUS_ENV=prod`), Schema: `/api/v1/openapi.json`.

**Auth**: Session-Cookie `nq_session` (HttpOnly, SameSite=Lax) nach Login, alternativ `Authorization: Bearer <token>`. Zustandsändernde Requests mit Cookie brauchen den Header `X-Requested-With: nexus`. Fremde Ressourcen liefern `404`.
**Fehler**: `{"error": {"code", "message", "details", "request_id"}}`. Listen: `?limit=` (max. 100) und `?offset=`, Antwort `{items, total, limit, offset}`.
**Langlaufende Aktionen** antworten mit `202` und einem Objekt mit `status` und `job` (`progress_current/total`, `cancel_requested`). Pollen über den jeweiligen GET-Endpunkt.

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/health` | Status, DB, Engine-Version, Jobs-Modus |
| POST | `/auth/register`, `/auth/login`, `/auth/logout` | Konto, Session |
| GET / PATCH | `/auth/me`, `/auth/me/preferences` | Profil, Standardwerte |
| GET | `/auth/me/export` | Alle eigenen Daten als JSON |
| GET | `/strategies/schema` | Unterstützte Indikatoren, Operatoren, JSON-Schema |
| POST | `/strategies/validate` | Definition prüfen (Fehler mit Pfad), Hash, Warm-up |
| GET / POST | `/strategies` | Liste (`status`, `q`) / anlegen (Version 1) |
| POST | `/strategies/import` | Export-Dokument importieren |
| GET / PATCH | `/strategies/{id}` | Details / Name, Beschreibung, neue Version (`definition`, `note`) |
| POST | `/strategies/{id}/duplicate`, `/strategies/{id}/archive[?restore=true]` | Kopie, Archiv |
| GET | `/strategies/{id}/versions`, `/strategies/{id}/export[?version_id=]`, `/strategies/{id}/backtests` | Historie |
| GET | `/market-data/sources`, `/market-data/sources/{id}`, `/market-data/sources/{id}/candles?limit=` | Datenquellen, Kerzenvorschau |
| POST | `/market-data/demo` | Synthetische Daten (markiert) |
| POST | `/market-data/import-csv` | Multipart: `symbol`, `timeframe`, `file` |
| POST | `/market-data/fetch` | Binance-Klines `{symbol, timeframe, start, end}` |
| GET | `/market-data/providers` | Verfügbare Quellen |
| POST | `/backtests`, `/strategies/{id}/backtests` | Backtest starten (`market_data_source_id`, `initial_capital`, optional Zeitfenster und Kosten-Overrides) |
| GET | `/backtests`, `/backtests/{id}`, `/backtests/{id}/trades`, `/backtests/{id}/metrics` | Ergebnisse |
| POST | `/backtests/{id}/cancel` | Abbrechen |
| POST / GET | `/validations`, `/validations/{id}` | Validierung starten / abrufen (`?strategy_version_id=`) |
| POST / GET | `/discoveries`, `/discoveries/{id}` | Discovery `{market_data_source_id, config}` |
| GET | `/discoveries/{id}/candidates?status=&sort=score|name` | Kandidaten |
| POST | `/discoveries/{id}/cancel`, `/discoveries/{id}/candidates/{cid}/save` | Abbrechen, als Strategie speichern |
| GET / POST | `/journal/trades` | Liste mit Filtern (`symbol`, `side`, `source_type`, `strategy_id`, `tag`, `start`, `end`, `q`) und `stats` / anlegen |
| GET / PUT / DELETE | `/journal/trades/{id}` | Einzeltrade |
| POST | `/journal/imports/preview`, `/journal/imports` | CSV-Vorschau mit Mapping / Import (`skip_duplicates`) |
| GET / POST | `/paper/sessions` | Sessions |
| GET | `/paper/sessions/{id}` | Details inkl. Equity, Orders, Fills, Audit |
| POST | `/paper/sessions/{id}/start|pause|resume|stop` | Statuswechsel |
| POST | `/paper/sessions/{id}/advance` | `{bars}` Kerzen verarbeiten (idempotent) |
| POST | `/tradingview/token` | Secret erzeugen/rotieren (einmalig angezeigt) |
| POST | `/tradingview/webhook` | Alert empfangen (Secret im Body, ohne Login) |
| GET | `/tradingview/alerts` | Alerts, Token-Status, Beispiel-Payload |
| POST | `/tradingview/alerts/{id}/journal` | `{quantity}` → Journal-Trade |
| GET | `/ai/status` | Konfiguration und Limits |
| POST | `/ai/research` | `{task, symbol, timeframe}` → Entwurf |
| GET | `/ai/runs`, `/ai/runs/{id}` | Läufe inkl. Tool-Calls |
| POST | `/ai/runs/{id}/confirm` | `{market_data_source_id, initial_capital}` → Strategie + Backtest + Validierung |
| POST | `/ai/runs/{id}/explain`, `/ai/runs/{id}/cancel` | Erklärung der Ergebnisse, Abbruch |
| GET | `/overview` | Dashboard-Daten |

## TradingView-Payload

```json
{"secret": "<dein Secret>", "event_id": "{{strategy.order.id}}-{{timenow}}", "symbol": "BTCUSDT",
 "action": "buy", "price": "{{close}}", "time": "{{timenow}}", "strategy": "EMA cross", "note": "optional"}
```
`event_id` ist pro Nutzer eindeutig (Wiederholungen werden ignoriert), `time` darf höchstens 10 Minuten abweichen. Alerts lösen nie Orders aus.
