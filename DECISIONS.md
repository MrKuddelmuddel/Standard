# Architekturentscheidungen

Jede Entscheidung mit Begründung. Neue Einträge unten anhängen.

## D1 – Struktur: `backend/` (API + Quant-Paket) und `frontend/`
Statt des vorgeschlagenen Monorepos mit `apps/`, `services/`, `quant/`, `packages/` gibt es zwei Ordner. Das Quant-Paket (`backend/quant`) hat keine Abhängigkeit zu Datenbank oder Web-Framework und ist separat testbar, wird aber mit derselben `pyproject.toml` installiert. Ein eigenes Paket für geteilte Typen lohnt sich im MVP nicht; die API-Schemas sind über OpenAPI dokumentiert.

## D2 – Altes Backtest-Labor bleibt erhalten
`legacy/backtest-lab/` wurde nur verschoben und bleibt lauffähig. NEXUS QUANT übernimmt die bewährten Regeln (Next-Open, Stop zuerst, Kosten), nicht den Code, weil die neue Engine auf der Strategy-DSL basiert.

## D3 – NumPy statt Pandas/Polars in der Engine
Die Engine arbeitet auf NumPy-Arrays und Standard-Python. Das hält die Abhängigkeiten klein, macht die Indikatoren explizit kausal und die Ergebnisse deterministisch. CSV-Parsing nutzt das `csv`-Modul.

## D4 – Datenbank: PostgreSQL in Docker, SQLite für Tests und Schnellstart
Modelle nutzen portable Typen (`String(36)` für UUIDs, `JSON`). Alembic-Migrationen werden gegen SQLite und eine echte lokale PostgreSQL-Instanz geprüft.

## D5 – Hintergrundjobs: Datenbank-Queue statt Redis
Backtests, Validierungen und Discovery laufen als Jobs in einer `jobs`-Tabelle. Ein Worker (`python -m app.workers.runner`) holt Jobs ab; auf PostgreSQL mit `FOR UPDATE SKIP LOCKED`. Für die lokale Entwicklung startet die API optional einen Worker-Thread (`JOBS_MODE=thread`). Redis entfällt im MVP, weil die Datenbank bereits Persistenz, Status und Wiederholbarkeit liefert. Redis kann später für Caching oder Rate-Limits hinzukommen.

## D6 – Eigene Auth mit scrypt und opaken Session-Tokens
Passwörter mit `hashlib.scrypt` (Standardbibliothek, speicherhart). Sessions als zufällige Tokens, in der DB nur als SHA-256-Hash gespeichert, im Browser als HttpOnly-, SameSite=Lax-Cookie. Zustandsändernde Requests verlangen zusätzlich den Header `X-Requested-With: nexus` (CSRF-Schutz neben SameSite). Das Frontend spricht die API über einen Next.js-Rewrite auf derselben Origin an.

## D7 – Strategie-DSL als JSON-Ausdrucksbaum
Kein `eval`, keine Codeausführung. Bedingungen bestehen aus festen Operatoren (`gt`, `lt`, `gte`, `lte`, `crosses_above`, `crosses_below`, `all`, `any`, `not`) über Indikator-, Preis- und Zahlenoperanden. Limits für Tiefe, Knotenzahl und Indikatorzahl. Kanonische Serialisierung (sortierte Schlüssel) plus SHA-256-Hash pro Version.

## D8 – Ausführungsmodell `next_open_v1`
Signal am Schluss einer Kerze, Ausführung zur Eröffnung der nächsten. Slippage verschlechtert jeden Fill um `slippage_bps`. Gebühren `fee_bps` auf das Notional jedes Fills (Ein- und Ausstieg je einmal). Berühren Stop und Take Profit dieselbe Kerze, zählt der Stop. Öffnet eine Kerze jenseits des Stops, wird zum schlechteren Eröffnungskurs gefüllt. Shorts nur in `futures_sim`; Funding wird nicht modelliert und als Warnung ausgewiesen.

## D9 – Paper Trading als Historical Replay mit derselben Simulationslogik
Paper-Sessions nutzen denselben `Simulator` wie die Engine und verarbeiten gespeicherte Kerzen Schritt für Schritt. Jeder Order/Fill hat einen eindeutigen Idempotency Key (`session:bar_time:action`). Live-Daten sind im MVP nicht angebunden.

## D10 – Charts als eigenes SVG
Equity, Drawdown und Kerzen werden als eigene SVG-Komponenten gezeichnet. Das vermeidet Lizenzfragen (z. B. Attributionspflicht bei TradingView-Bibliotheken) und zusätzliche Abhängigkeiten.
