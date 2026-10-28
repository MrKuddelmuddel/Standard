# Known Limitations

Ehrliche Liste dessen, was das MVP **nicht** kann oder nur eingeschränkt.

## Daten
- **In dieser Entwicklungsumgebung waren Börsen-APIs gesperrt (HTTP 403).** Der Binance-Adapter ist mit Mocks getestet (Paginierung, Retries, Fehler), aber nicht gegen die echte API. Sobald der Server Zugriff auf `api.binance.com` hat, sollte er funktionieren; geo-Beschränkungen und Nutzungsbedingungen beachten.
- Alle Screenshots, E2E-Läufe und Beispielergebnisse nutzen **synthetische Random-Walk-Daten**. Sie testen die Software, nicht einen Markt-Edge.
- Nur BTCUSDT und ETHUSDT, Timeframes 15m/1h/4h/1d, eine Datenquelle pro Backtest.
- Kein automatisches Nachladen neuer Kerzen; Daten werden manuell importiert oder abgerufen.

## Simulation
- Fills ausschließlich `next_open`; keine Limit-Orders, keine Teilfüllungen, kein Orderbuch, keine Latenz.
- Slippage ist ein fester Basispunktwert, unabhängig von Volatilität und Volumen.
- Shorts nur als `futures_sim`: **Funding, Hebel, Margin und Liquidation sind nicht modelliert**.
- Bei Stop und Target in derselben Kerze wird immer der Stop angenommen (konservativ, kann Ergebnisse verschlechtern).
- Paper Trading ist **Historical Replay** gespeicherter Kerzen; es gibt keinen Live-Feed.

## Statistik
- Keine Korrektur für Mehrfachtests in Discovery (Hinweis im UI). Kennzahlen wie Sharpe/Sortino fehlen.
- Bootstrap-Intervall nur für die mittlere Trade-Expectancy; Trades werden als unabhängig angenommen.

## Plattform
- Rate-Limits sind **prozesslokal** (In-Memory). Mit mehreren API-Prozessen braucht es einen gemeinsamen Store.
- Job-Claim per atomarem `UPDATE`; für sehr viele parallele Worker wäre `SKIP LOCKED` effizienter.
- Keine E-Mail-Verifikation, kein Passwort-Reset, kein 2FA, keine Rollen/Teams.
- Strategien können nur archiviert, nicht gelöscht werden.
- Zeitzone der Oberfläche ist fest UTC.
- AI Research ist mit einem Fake-Provider getestet; ein echter Lauf gegen die Anthropic-API wurde hier mangels Key **nicht** durchgeführt. Kostenschätzung nur für bekannte Modellpreise.
- **Docker Compose**: `docker compose config` ist validiert, ein vollständiger Image-Build konnte in der Entwicklungsumgebung nicht abgeschlossen werden (Docker-Hub-Rate-Limit und kein Paketzugriff aus Build-Containern). Backend und Frontend wurden stattdessen direkt (uvicorn, `next start`) mit denselben Einstellungen getestet.
- Die CI-Pipeline ist geschrieben, aber noch nicht auf GitHub gelaufen.
