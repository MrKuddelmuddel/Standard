# Strategy Discovery

Discovery durchsucht ein **begrenztes Raster** aus Vorlagen und Parametern. Es ist ein Werkzeug zur Hypothesenfindung, kein Renditeversprechen: Je mehr Varianten auf derselben Historie getestet werden, desto wahrscheinlicher sind Zufallstreffer. Darauf weist das UI und der Bericht hin.

## Ablauf

1. **Generieren**: Vorlagen `ema_cross` (fast/slow EMA, nur fast < slow), `rsi_reversion` (RSI kreuzt das Einstiegslevel, Ausstieg über dem Exit-Level), `breakout` (Close über dem Hoch bzw. unter dem Tief der vorherigen N Kerzen), kombiniert mit ATR-Stop und R-Target. Kombinationen, die das Schema verletzen, erscheinen als `rejected: invalid`.
2. **Begrenzen und deduplizieren**: Ist das Raster größer als `max_candidates`, wird eine Stichprobe mit festem `seed` gezogen (reproduzierbar). Danach werden identische Definitionen über den kanonischen Hash entfernt.
3. **Train-Filter** (nur Train-Segment): mindestens `min_trades` Trades, Expectancy > 0, Drawdown ≤ `max_drawdown`. Sonst `rejected` mit Grund.
4. **Shortlist**: die besten `shortlist` nach Train-Expectancy (R).
5. **Validierung** der Shortlist auf dem Validierungssegment und mit doppelten Kosten. Flags: `unstable`, `insufficient`, `cost_sensitive`.
6. **Ranking `rank_v1`** ausschließlich aus Validierungsmetriken: Profit Factor (30 %), Drawdown (20 %), Stichprobe (15 %), Expectancy R (15 %), Konsistenz train → validation (10 %), Kostenrobustheit (10 %). Teilwerte werden gespeichert.
7. **Testsegment** wird nur für Kandidaten ohne Flags (`validated`) einmal ausgewertet und nie für das Ranking verwendet. Negativ → Flag `failed_test`.

Abbruch und Zeitlimit (`max_seconds`, Server-Obergrenze `MAX_DISCOVERY_SECONDS`) werden respektiert; der Bericht nennt `stopped_early`. Kandidaten lassen sich als Strategie (Herkunft `discovery`) speichern.
