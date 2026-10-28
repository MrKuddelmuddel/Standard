# Sicherheit

## Grundsätze
- **Kein Live-Trading.** Es gibt keinen Code-Pfad, der Orders an eine Börse sendet. Exchange-API-Keys werden weder abgefragt noch gespeichert. Paper Trading ist reine Simulation.
- **Keine Codeausführung aus Strategien.** Die DSL ist ein validierter Ausdrucksbaum mit Limits (Tiefe, Knoten, Indikatoren).
- **Secrets nur über Umgebungsvariablen**, nie im Frontend. `ANTHROPIC_API_KEY` erscheint nicht in Logs (`repr=False`, Log-Redaction für Schlüssel wie `password`, `secret`, `token`, `api_key`, `authorization`, `cookie` sowie für Werte, die wie Anthropic-Keys oder Bearer-Tokens aussehen).

## Authentifizierung und Sessions
- Passwörter: `hashlib.scrypt` (N=2^14, r=8, p=1) mit zufälligem Salt; Vergleich in konstanter Zeit. Mindestlänge 10.
- Sessions: Zufallstoken aus 32 Byte (`secrets.token_urlsafe`), in der DB nur als SHA-256 gespeichert, Ablauf nach `SESSION_DAYS`. Cookie `HttpOnly`, `SameSite=Lax`, `Secure` über `COOKIE_SECURE`.
- CSRF: Cookie-authentifizierte, zustandsändernde Requests verlangen `X-Requested-With: nexus` (zusätzlich zu SameSite). Bearer-Token sind nicht CSRF-anfällig.
- Login-Fehler unterscheiden nicht zwischen unbekannter E-Mail und falschem Passwort. Die Registrierung meldet eine bereits vergebene E-Mail (`409 email_taken`) – ein bewusster UX-Kompromiss, abgefedert durch Rate-Limits (10/min pro IP für Registrierung, pro IP und pro E-Mail für Login).

## Autorisierung
Jede Ressource hat `owner_id`; Zugriffe auf fremde Objekte liefern `404` (keine Existenz-Leaks). Getestet für Strategien, Backtests, Datenquellen, Journal, Paper, Alerts.

## Eingaben und Uploads
- Pydantic-Validierung aller Bodies; unbekannte Felder in Strategien werden abgelehnt.
- CSV-Uploads: Größenlimit (`MAX_CSV_BYTES`), Zeilenlimit, UTF-8, Spalten mit Namen wie `api_key`/`secret`/`password` werden ignoriert und nicht gespeichert.
- Teure Endpunkte (Backtest, Discovery, Import, KI) haben ein Limit pro Minute; Jobs pro Nutzer sind begrenzt; Backtests haben ein Kerzenlimit, Discovery ein Kandidaten- und Zeitlimit.

## TradingView-Webhook
Secret (mind. 16 Zeichen) im JSON-Body, serverseitig nur als Hash gespeichert und rotierbar. Prüfung von Zeitabweichung (±600 s) und Dubletten (`event_id`). Rate-Limit pro IP und pro Token.

## KI-Assistent
- Werkzeuge sind auf Lesen/Validieren/Vorschlagen beschränkt; kein Netzwerk, keine Orders, keine Datenbankschreibzugriffe durch das Modell.
- Nutzertext wird in `<user_task>`-Tags eingefasst und als Daten behandelt; Tool-Argumente werden serverseitig validiert.
- Grenzen pro Lauf (Tool-Calls, Zeit, Output-Tokens) und pro Tag. Jede Aktion mit Wirkung (Strategie anlegen, Backtest starten) braucht eine ausdrückliche Bestätigung im UI.
- Alle Tool-Aufrufe werden mit Argumenten, Ergebnis und Dauer protokolliert.

## HTTP
API: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, restriktive CSP für JSON-Antworten, HSTS bei `COOKIE_SECURE=true`. Web: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`; `X-Powered-By` deaktiviert; Request-IDs in allen Antworten und Logs.

## Bekannte Lücken
Siehe [KNOWN_LIMITATIONS.md](../KNOWN_LIMITATIONS.md): Rate-Limits sind prozesslokal, keine E-Mail-Verifikation, kein Passwort-Reset, kein 2FA.
