# Backtesting

## Ausführungsmodell `next_open_v1`

1. Indikatoren und Signale werden auf **abgeschlossenen** Kerzen berechnet.
2. Ein Signal an Kerze *i* wird zum **Open von Kerze *i+1*** ausgeführt. Keine Fills zum Close der Signalkerze.
3. **Slippage** verschlechtert jeden Fill um `slippage_bps` (Kauf höher, Verkauf tiefer).
4. **Gebühren**: `fee_bps` auf das Notional jedes Fills (Ein- und Ausstieg).
5. **Stop/Target intrabar**: Werden in derselben Kerze Stop und Target berührt, zählt der **Stop** (konservativ). Öffnet eine Kerze jenseits des Stops (Gap), wird zum **Open** gefüllt. Ein Target wird zum Target-Preis gefüllt.
6. Exit-Signale schließen zum nächsten Open. `max_bars_in_trade` schließt nach N Kerzen.
7. Eine Position pro Strategie; kein Pyramiding, kein Hebel über `fraction` hinaus.
8. Shorts nur in `futures_sim`; **Funding wird nicht modelliert** (`funding_cost = null`, Warnung im Ergebnis).
9. Am Ende des Zeitfensters offene Positionen werden zum letzten Close (inkl. Slippage) geschlossen (`exit_reason = end_of_period`, mit Warnung).

Derselbe `Simulator` treibt Paper-Sessions; ein Replay über dieselben Kerzen liefert dieselbe Equity wie der Backtest (getestet).

## Kennzahlen

`net_return`, `gross_return` (vor Kosten), `final_equity`, `max_drawdown` (auf Kerzenbasis inkl. offener Positionen), `trade_count`, `win_rate`, `profit_factor`, `expectancy` (je Trade, netto), `expectancy_r`, `avg_win`, `avg_loss`, `largest_loss`, `avg_holding_hours`, `exposure`, `total_fees`, `total_slippage`, `expectancy_ci_low/high` (95 %-Bootstrap des mittleren Trade-P&L, 2000 Resamples, fester Seed).

Undefinierte Werte sind `null` mit Begründung in `metric_notes` (z. B. Profit Factor ohne Verlusttrades, R-Multiples ohne Stop). Unter 30 Trades erscheint ein Stichprobenhinweis. Synthetische Daten werden in jedem Ergebnis markiert.

## Datenqualität

Importe sind idempotent: Kerzen sind über (Quelle, `open_time`) eindeutig, ein erneuter Import überschreibt bestehende Kerzen, und jede Änderung erhöht die Revision der Quelle. OHLC-Konsistenz wird geprüft, Lücken werden erkannt und in den Metadaten gespeichert. Der Fingerprint (SHA-256 über die Kerzen) ändert sich mit jeder inhaltlichen Änderung. Strategie und Datenquelle müssen in Symbol und Timeframe übereinstimmen.

## Validierung (`split+walk_forward+sensitivity_v1`)

- **Chronologische Splits** train / validation / test mit festen Parametern
- **Walk-forward**: rollierende Fenster über den Out-of-Sample-Bereich, **ohne Re-Optimierung**
- **Kosten-Stresstest**: Gebühren und Slippage × Multiplikator (Standard 2)
- **Parameter-Nachbarn**: jede numerische Periode ±20 %, Vorzeichenwechsel der Expectancy werden gezählt
- Warnungen bei kleiner Stichprobe, Einbruch train → OOS, unprofitablen Folds, Kostensensitivität, synthetischen Daten
