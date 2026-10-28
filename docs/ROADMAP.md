# Roadmap

Reihenfolge nach Nutzen für die Kernfrage „Hat diese Strategie wirklich einen Vorteil?“.

## Als Nächstes
1. **Echte Marktdaten im Betrieb**: geplanter Binance-Abruf (inkrementell, Lücken-Nachladen) als Job; zusätzlich Bybit/OKX-Adapter über dieselbe `MarketDataProvider`-Schnittstelle.
2. **Funding und Futures realistischer**: historische Funding-Rates importieren und in `futures_sim` verrechnen; Liquidationspreis als Warnung.
3. **Robustere Statistik**: Deflated Sharpe / Multiple-Testing-Korrektur für Discovery, Monte-Carlo über Trade-Reihenfolge, Sharpe/Sortino/Calmar.

## Danach
- Live-Paper-Trading mit Websocket-Kerzen (weiterhin ohne Orders), Benachrichtigungen bei Signalen
- Portfolio-Backtests über mehrere Symbole und Strategien, Korrelationen
- Mehr Indikatoren (MACD, Bollinger, VWAP) und Regime-Filter im DSL, mit Schema-Version 1.1 und Migration
- Journal: Screenshots, Tags-Statistiken, Abgleich Journal ↔ Strategie-Signale
- Gemeinsamer Rate-Limit-Store (Redis) für mehrere API-Replikas, E-Mail-Verifikation, Passwort-Reset, 2FA
- Job-Queue mit `FOR UPDATE SKIP LOCKED` auf PostgreSQL für viele Worker

## Bewusst nicht geplant
- Automatisches Live-Trading mit echten Orders
- Renditeversprechen, „Signale zum Kopieren“
