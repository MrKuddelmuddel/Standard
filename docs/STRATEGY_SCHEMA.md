# Strategy-Schema 1.0

Strategien sind JSON-Dokumente, validiert durch `quant/strategy_schema/model.py`. Es wird **kein Code ausgeführt**; Regeln sind ein Ausdrucksbaum aus festen Operatoren. Abfrage zur Laufzeit: `GET /api/v1/strategies/schema` (inkl. JSON-Schema), Prüfung: `POST /api/v1/strategies/validate`.

```json
{
  "schema_version": "1.0",
  "name": "EMA 20/50 crossover",
  "description": "",
  "symbols": ["BTCUSDT"],
  "timeframe": "1h",
  "market_type": "spot",
  "direction": "long",
  "indicators": [
    {"id": "fast", "type": "ema", "period": 20, "source": "close"},
    {"id": "slow", "type": "ema", "period": 50, "source": "close"},
    {"id": "atr14", "type": "atr", "period": 14, "source": "close"}
  ],
  "entry": {"long": {"op": "crosses_above", "left": {"ind": "fast"}, "right": {"ind": "slow"}}},
  "exit":  {"long": {"op": "crosses_below", "left": {"ind": "fast"}, "right": {"ind": "slow"}}},
  "risk_management": {
    "stop_loss": {"type": "atr", "value": 2, "atr_indicator": "atr14"},
    "take_profit": {"type": "r_multiple", "value": 2},
    "max_bars_in_trade": null
  },
  "position_sizing": {"type": "risk_percent", "fraction": 1, "risk_percent": 1},
  "execution": {"fill_model": "next_open"},
  "costs": {"fee_bps": 10, "slippage_bps": 5}
}
```

## Felder

- `symbols`: `BTCUSDT`, `ETHUSDT` · `timeframe`: `15m`, `1h`, `4h`, `1d`
- `market_type`: `spot` (nur long) oder `futures_sim` (long/short, ohne Funding – wird als Warnung ausgewiesen)
- `indicators` (max. 12): `id` (`^[a-z][a-z0-9_]{0,31}$`), `type` ∈ `ema`, `sma`, `rsi`, `atr`, `highest`, `lowest`, `volume_sma`, `period` 2–500. EMA startet mit SMA-Seed; RSI/ATR nach Wilder; `highest`/`lowest` betrachten nur **vorherige** Kerzen (kein Look-ahead beim Breakout).
- Bedingungen: `{"op": gt|lt|gte|lte|crosses_above|crosses_below, "left": O, "right": O}`, `{"all": [...]}`, `{"any": [...]}`, `{"not": {...}}`. Operanden: `{"ind": id}`, `{"price": open|high|low|close|volume}`, `{"value": Zahl}`. Grenzen: Tiefe 5, 40 Knoten, je Liste 1–8 Elemente. Jede referenzierte Indikator-ID muss existieren.
- `stop_loss`: `none` | `percent` (Prozent vom Einstieg) | `atr` (Vielfaches eines ATR-Indikators)
- `take_profit`: `none` | `percent` | `atr` | `r_multiple` (Vielfaches des Stop-Abstands, braucht Stop)
- `position_sizing`: `fixed_fraction` (Anteil des Kapitals, max. 1 = kein Hebel) oder `risk_percent` (Verlust am Stop in % des Kapitals, gedeckelt durch `fraction`, braucht Stop)
- `costs`: Gebühr und Slippage in Basispunkten pro Fill

## Versionierung

Beim Speichern wird das Dokument kanonisch serialisiert (sortierte Schlüssel, normalisierte Zahlen) und gehasht. Ist der Hash identisch zur aktuellen Version, entsteht keine neue Version. Versionen sind unveränderlich. Export-Format: `{"format": "nexus-quant-strategy", "format_version": 1, "strategy": {...}, "definition": {...}}`.

`warmup_bars` = größte Indikatorperiode + 1. Vor Ablauf des Warm-ups werden keine Signale erzeugt.
