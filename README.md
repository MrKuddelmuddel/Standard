# Krypto-Backtest-Labor

Ein kleines Labor, um Krypto-Handelsideen **ehrlich zu testen, bevor Geld im Spiel ist**. Es handelt nicht, es hat keine Börsen-Schlüssel und es kann kein Geld bewegen.

## Wichtig vorweg

- Das Labor liefert keine Gewinne. Es soll dir zeigen, ob eine Idee **überhaupt** etwas taugt, und das ist selten der Fall.
- Die mitgelieferten Strategien sind einfache Lehrbeispiele. Sie sind keine Empfehlung und kein bewiesener Vorteil.
- Mit den künstlichen Zufallsdaten (`--synthetic`) darf es keinen verlässlichen Vorteil geben. Ein Ergebnis dort beweist nur, dass die Technik läuft.
- Das ist keine Anlageberatung.

## Schnellstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install numpy pandas            # reicht für den Beispiel-Lauf
python run_example.py --synthetic   # Beispiel mit Zufallsdaten
python run_example.py --journal     # Journal ansehen
python -m unittest discover -s tests
```

Der Bericht landet in `out/report.md`, das Journal in `out/journal.db` (SQLite) und `out/journal.csv`.

## Mit echten Kursen

Auf deinem eigenen Rechner (öffentliche Daten, **kein Schlüssel nötig**):

```bash
pip install ccxt
python fetch_data.py --exchange binance --symbol BTC/USDT --timeframe 1h --since 2020-01-01 --out data/btc_1h.csv
python run_example.py --csv data/btc_1h.csv
```

Nimm einen langen Zeitraum, der Bullen- und Bärenphasen enthält, und teste mehrere Coins. Ein Test nur in einer steigenden Phase sagt wenig. `fetch_data.py` wurde in der Entwicklungsumgebung nicht gegen eine echte Börse getestet, weil Börsen dort gesperrt sind. Die Abruf-Logik ist mit einem Ersatzobjekt geprüft.

## Was das Labor macht

1. **Daten laden und prüfen** (Lücken, kaputte Kerzen).
2. **Training und Test trennen.** Die Parameter werden nur auf dem ersten Teil gewählt. Bewertet wird auf dem zweiten, den die Auswahl nie gesehen hat.
3. **Setups erzeugen.** Signal am Ende einer Kerze, Einstieg zur Eröffnung der nächsten. Kein Blick in die Zukunft (per Test abgesichert).
4. **Titan prüft jedes Setup** mit festen Regeln: nur eine Position, Abkühlphase, Tagesverlust-Limit, gültiger Stop, Mindest-Chance-Risiko-Verhältnis, Kosten im Verhältnis zum Risiko, Positionsgröße nach der 1-%-Regel.
5. **Backtest mit Kosten.** Gebühren und Slippage auf Kauf und Verkauf. Berühren Stop und Ziel dieselbe Kerze, zählt der Stop zuerst.
6. **Journal.** Jedes Setup wird festgehalten, auch die abgelehnten, samt Grund und dem Ergebnis, das sie gehabt hätten. So siehst du, ob Titan Verluste verhindert oder gute Chancen blockiert.
7. **Ehrliche Maßstäbe im Bericht:** 95-%-Spanne für den Durchschnitt in R (Bootstrap), Kosten-Stress mit doppelten Gebühren, Vergleich mit zufälligen Einstiegen, Buy & Hold, Zähler für alle getesteten Parametersätze.

## Aufbau und Rollen

| Datei | Rolle im späteren Agenten-Dorf |
|---|---|
| `lab/data.py`, `fetch_data.py` | ATLAS, der Daten-Scout |
| `lab/indicators.py`, `lab/strategies.py` | VEGA, der Chart-Analyst |
| `lab/risk.py` | TITAN, der Risiko-Wächter (feste Regeln, nicht KI) |
| `lab/backtest.py`, `lab/metrics.py`, `lab/report.py` | der Backtester |
| `lab/journal.py` | das Journal |
| (später) | ORION (Nachrichten), LUNA (Stimmung), NOVA (Entscheider), Controller (Kosten) |

## Grenzen dieser Version

- Nur Long (Kauf), eine Position gleichzeitig, ein Coin pro Lauf, Kerzen statt Orderbuch.
- Keine Hebel, keine Finanzierungsgebühren, keine Börsenausfälle. Vereinfachte Ausführung, echte Orders sind schlechter.
- Gelistete Coins von heute zu testen verzerrt (Überlebens-Effekt): gescheiterte Coins fehlen.
- Die Auswahl der Parameter auf dem Trainingsteil ist selbst ein Versuch. Je größer das Raster, desto eher gewinnt der Zufall.
- Ein gutes Ergebnis hier ist **kein Beweis**. Der nächste Schritt wäre ein Paper-Forward-Test auf Live-Daten (mindestens ca. 100 Setups), danach erst ein sehr kleiner Echtgeld-Test mit Schlüsseln **ohne Auszahlungsrecht** und festen Verlustgrenzen.
