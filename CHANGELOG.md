# Changelog

Alle nennenswerten Änderungen an ScandyPro werden hier dokumentiert.

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/) (vor
1.0.0: `0.MINOR.PATCH`, MINOR kann auch für neue Features brechende Änderungen
enthalten - üblich für Software vor dem ersten stabilen Release). Gepflegt
analog zum Schwestermodul Scandy-Lite.

## [0.1.10] - 2026-08-03

Rest von [tasks/ganzheitliche-verbesserungen/](tasks/ganzheitliche-verbesserungen/README.md)
(VB-007 bis VB-017) umgesetzt - damit ist die gesamte Liste abgearbeitet.

### Fixed
- Upload-Validierung prüft jetzt zusätzlich zur Dateiendung die
  tatsächliche Datei-Signatur (Magic Bytes) für PDF/JPEG/PNG/DOC/DOCX
  (`app/core/uploads.py`).
- Demo-Logins auf der Login-Seite erscheinen nur noch, wenn
  `SEED_DEMO_DATA=true` gesetzt ist.
- Deaktivierte Accounts (siehe unten) werden auch bei bereits laufender
  Session sofort ausgesperrt, nicht erst beim nächsten Login.

### Added
- **Admin: Account-Deaktivierung** als Zwischenstufe zwischen aktiv und
  Löschung (`User.aktiv`), plus Anzeige des letzten Logins
  (`User.letzter_login`) in der Benutzerverwaltung.
- **"Meine Freigaben"**: neue Übersicht der für die eigene(n)
  Teilnehmergruppe(n) freigegebenen Team-Boards; dritte Lösch-Option für
  die persönliche Kanban-Aufgabenliste ergänzt die bestehenden
  Wohlbefinden-/Bewerbungs-Löschungen.
- **Bewerbungen**: Termine können jetzt mit Uhrzeit und Ort erfasst werden,
  erscheinen zusammen mit fälligen Kanban-Karten im Dashboard ("Was steht
  an"); Status-Wechsel zu "abgesagt"/"zugesagt" zeigen eine kurze, sanft
  formulierte Rückmeldung statt stiller Statusänderung.
- **Wochenberichte**: in dieser Woche abgeschlossene Kanban-Karten werden
  als antippbare Vorschläge im "Neuer Wochenbericht"-Formular angeboten
  (übernimmt nichts automatisch).
- **PSM und Einrichtungs-Admin** haben jetzt ebenfalls eine
  Bottom-Tab-Bar für schmale Bildschirme (vorher nur Teilnehmer/
  Berufstrainer).

### Changed
- Kaskadierendes Löschen von Kanban-Boards/-Spalten läuft jetzt über
  `app/core/deletion.py` (vorher inline in `app/routers/kanban.py` dupliziert).
- Wochenbericht-Formularfelder-Zuordnung in einer gemeinsamen Funktion
  statt zweimal ausgeschrieben (`bericht_erstellen`/`bericht_bearbeiten`).

### Verified (kein Code-Änderungsbedarf)
- Kanban-Kartenbewegung ist bereits per Tastatur/Touch bedienbar (natives
  `<select>` als Alternative zum Drag&Drop, seit einem früheren Commit) -
  die ursprüngliche Rechercheannahme dazu war veraltet.

## [0.1.9] - 2026-08-03

Umsetzung der ersten sechs Punkte aus
[tasks/ganzheitliche-verbesserungen/](tasks/ganzheitliche-verbesserungen/README.md)
(Accountverwaltung- und Mein-Tag-Review über alle Rollen hinweg).

### Fixed
- **IDOR bei privaten Kanban-Karten**: mutierende Karten-/Unteraufgaben-
  Endpunkte prüften Sichtbarkeit privater Karten (Personen-Board) nicht,
  nur die reine Board-Zugriffsprüfung - ein zuständiger Trainer konnte über
  die Karten-ID private Karten lesen/ändern/löschen. Neue zentrale Prüfung
  `require_karte_sichtbar` (`app/core/access.py`).
- Kein Rate-Limiting beim Login - einfacher In-Memory-Schutz gegen
  Brute-Force-Versuche ergänzt (`app/core/rate_limit.py`).

### Added
- **"Ich möchte jetzt Unterstützung"**: unabhängig vom Tagebuch immer
  sichtbarer Hinweis in "Mein Tag" mit PSM-Kontakt und externen
  Hilfsangeboten (TelefonSeelsorge, Nummer gegen Kummer) - nie automatisch
  ausgelöst.
- `/konto`: Link zu "Meine Freigaben", Datenexport der eigenen Daten
  (Art. 15 DSGVO, `GET /konto/export`) und Selbstlöschung der eigenen
  Wohlbefinden-/Bewerbungsdaten sowie der persönlichen Kanban-Aufgabenliste.
  Vollständige Konto-/Login-Löschung bewusst zurückgestellt (siehe
  `app/core/deletion.py`, VB-004.md) - blockiert durch nicht-nullbare
  Fremdschlüssel auf Team-Boards.
- Dashboard-Kachel **"Was steht an"** für Teilnehmer und Berufstrainer:
  fällige/überfällige Kanban-Karten der nächsten 7 Tage über alle
  sichtbaren Boards hinweg.
- **Mein-Tag-Übungspool auf 12 Typen erweitert** (siehe
  `app/core/tagesuebungen.py`): zusätzlich zu Atemübung und Zeichnung nun
  Körper-Scan, 5-4-3-2-1-Erdung, Ein Wort für heute, Stärken-Karte,
  Ausmal-Mandala, Ruhe-Ort-Visualisierung, Gedanken-Waage, Sorgen
  loslassen, Dankbarkeits-Foto-Moment und Mini-Ziel des Tages - wöchentlich
  rotierend (Fisher-Yates je Kalenderwoche), sodass innerhalb einer
  Arbeitswoche (Mo-Fr) kein Übungstyp doppelt gezeigt wird. Alle neuen
  Typen folgen demselben Prinzip wie die bestehenden: kein Scoring, keine
  wertende Sprache.

## [0.1.8] - 2026-08-03

### Added
- **Atemübungs-Pool mit 15 Varianten** (siehe `app/core/atemuebungen.py`):
  statt einer einzigen fest verdrahteten Verbinde-die-Punkte-Übung wird
  morgens täglich eine von 15 Varianten deterministisch ausgewählt (Box-
  Atmung, Dreieck-Atmung, Sechseck-Atmung, Anker setzen, ...) - Layout
  (Punktanzahl/-anordnung) wird je nach Übung automatisch berechnet.
  Migration `a1b2c3d4e5f6` speichert den gezeigten Namen, damit er beim
  erneuten Aufruf stabil bleibt.
- **Sinnvoller Halten-Timer (5-6 Sekunden)**: "Halten"-Punkte schalten
  nicht mehr sofort weiter, sondern zeigen einen kurzen Countdown ("Halten
  … noch 4"), bevor zum nächsten Punkt weitergezogen werden kann - eine
  bewusste Pause statt eines Präzisionstests.

### Fixed
- **"Zeichnung löschen" hat nicht funktioniert**: der Button lag im Markup
  außerhalb des von der JS als Container verwendeten `data-zeichenfeld`-
  Wrappers, wodurch der Klick-Handler nie gefunden/gebunden wurde - jetzt
  innerhalb des Wrappers verschachtelt.

## [0.1.7] - 2026-08-02

### Added
- **Vertikale Tab-Leiste** als wiederverwendbare Komponente (`.seiten-tabs`,
  siehe `app/static/css/style.css`) für Seiten mit mehreren klar getrennten
  Abschnitten - Alpine-gestützt, ohne Server-Roundtrip beim Wechseln. Auf
  schmalen Screens wird daraus eine horizontal scrollende Leiste statt
  einer Sidebar.
- **Bewerbungen-Seite komplett auf diese Tab-Leiste umgebaut**: "Neue
  Bewerbung", "Meine Unterlagen", "Laufende Bewerbungen", "Abgeschlossene
  Bewerbungen" und "Für wen freigeben" sind jetzt getrennte Abschnitte statt
  einer einzigen langen Seite mit allem untereinander.
- **4 interaktive Elemente im 5-Minuten-Tagebuch** (siehe
  `app/static/js/tagebuch-interaktiv.js`, `app/models/wohlbefinden.py`):
  eine Verbinde-die-Punkte-Atemübung morgens (nur der Zeitpunkt wird
  gespeichert, kein Zeichenpfad), ein optionaler Energie-Level als
  Batterie-Symbol morgens (rein privat, taucht nie im Dashboard-Trend auf),
  ein Freihand-Zeichenfeld abends ("Male, was dich heute gefreut hat" -
  wie Bewerbungsunterlagen verschlüsselt gespeichert, siehe
  `app/core/uploads.py`, mit eigenem Hard-Delete-Pfad) und drei antippbare
  Checklisten-Kacheln abends. Migration `f6a7b8c9d0e1`.

### Fixed
- Echter Bug beim Verbinde-die-Punkte-Widget behoben: der Startpunkt der
  Atemübung wurde nie als "erreicht" gezählt, da die Trefferprüfung nur bei
  Zeigerbewegung lief, nicht beim initialen Antippen selbst.
- CSS-Spezifitätsbug behoben, durch den die gefüllten Segmente der
  Energie-Batterie unsichtbar blieben (`button:not(.btn)` war spezifischer
  als `.energie-segment--voll`).
- Mobile Tab-Leiste verursachte horizontales Scrollen der gesamten Seite
  statt nur der Leiste selbst (fehlendes `min-width: 0` auf Flex-Kindern,
  plus `width: 100%` auf einzelnen Tab-Buttons, die dadurch je die volle
  Leistenbreite beanspruchten).

## [0.1.6] - 2026-08-02

### Fixed
- **Echter, reproduzierbarer CSRF-Bug behoben**: "+ Spalte hinzufügen" im
  Kanban (und praktisch jedes andere Formular) konnte mit "Ungültige oder
  abgelaufene Anfrage" (403) fehlschlagen, sobald zwischen dem Laden der
  Seite und dem Absenden mehr als eine Sekunde lag. Ursache: Starlettes
  `SessionMiddleware` signiert den Session-Cookie bei **jeder** Antwort mit
  einem neuen Zeitstempel neu (`itsdangerous.TimestampSigner`) - der rohe
  Cookie-String ändert sich dadurch bei jedem Request-Response-Zyklus,
  obwohl die enthaltenen Daten (z. B. `user_id`) gleich bleiben. Das
  CSRF-Token wurde bisher direkt aus diesem rohen, instabilen Cookie-Wert
  abgeleitet - ein beim Seitenaufruf eingebettetes Token war dadurch schon
  beim nächsten Request wieder ungültig. Fix: Das Token wird jetzt aus
  einem stabilen, zufälligen Wert abgeleitet, der im entschlüsselten
  Session-Dict liegt (`request.session["_csrf_secret"]`, siehe
  `app/core/templating.py:csrf_token`) und über beliebig viele Requests
  hinweg gültig bleibt, bis die Session geleert wird (Login/Logout).

## [0.1.5] - 2026-08-02

### Changed
- **"Mein Tag" komplett auf ein 5-Minuten-Tagebuch umgestellt** (in
  Anlehnung an das klassische "Five Minute Journal"-Format): die
  Stimmungs-/Energie-Skala (1-10, Heatmap-Verlauf) wurde vollständig durch
  ein strukturiertes Tagebuch ersetzt: morgens 3 feste
  Dankbarkeits-Felder + 1 täglich rotierender Klarheits-/Vorsatz-Impuls,
  abends 3 feste "großartige Dinge"-Felder + 1 rotierender
  Abendreflexions-Impuls. Der rotierende Impuls wird deterministisch aus
  Teilnehmer:in + Datum abgeleitet (`app/core/tagebuch_prompts.py`) - am
  selben Tag immer derselbe, ohne dass er separat gespeichert werden muss.
- Neues Datenmodell `TagebuchEintrag` ersetzt `WohlbefindenEintrag`
  (Migration `e5f6a7b8c9d0`); bestehende Stimmungs-Einträge werden dabei
  hart gelöscht (siehe CLAUDE.md §10 Löschkonzept - konsistent mit der
  bestehenden Hard-Delete-Pflicht für diese Datenkategorie).
- "Dein Verlauf" zeigt jetzt eine lesbare Liste der letzten 14 Tage mit
  Inhalt statt einer Farbraster-Heatmap - Freitext lässt sich nicht
  sinnvoll auf eine Farbskala reduzieren, ohne genau die Bewertungs-Optik
  zu erzeugen, die das neue Format vermeiden soll.
- Dashboard-Rückblick zählt jetzt Tage mit Tagebuch-Eintrag
  (`woechentliche_tagebuch_tage`) statt eines Stimmungs-Trends - eine
  reine Teilnahme-Zählung, die inhaltlich nie negativ ausfallen kann.

### Removed
- `app/core/skala.py`, `app/static/js/wohlbefinden.js` (nicht mehr
  benötigt, siehe oben).

## [0.1.4] - 2026-08-02

### Changed
- Kanban-Board-Layout von horizontal scrollender Flex-Reihe auf ein
  wrappendes CSS-Grid umgestellt: alle Spalten passen auf gängigen
  Breiten in eine Zeile (kein Scrollbalken, keine Pfeil-Buttons mehr
  nötig), bei mehr Spalten oder auf schmalen Screens wird umgebrochen
  statt seitlich zu scrollen. "+ Spalte hinzufügen" ist jetzt eine
  schlanke Leiste über den Spalten statt einer leeren Geister-Spalte im
  Spalten-Grid.

## [0.1.3] - 2026-08-02

### Changed
- **Neue Definition von "Schritte geschafft"**: zählt jetzt jede Karte, die
  mindestens einen Schritt nach rechts (in eine Spalte mit höherer
  Reihenfolge) gezogen wurde - nicht mehr erst bei vollständigem Abschluss.
  Neue Tabelle `kartenbewegung` protokolliert Vorwärtsbewegungen (Migration
  `d4e5f6a7b8c9`); Zurückziehen wird nicht negativ gewertet, zählt aber auch
  nicht doppelt.
- **Stimmungs-Trend statt Emoji als Primäranzeige** im Dashboard-Rückblick:
  großer Pfeil zeigt die Entwicklung, Emoji nur noch als Rückfall-Anzeige
  vor dem ersten Vergleichswert.
- **Trend-Sprache/-Farbe nie mehr wertend**: `app/core/skala.py:trend()`
  vermeidet jetzt Formulierungen wie "schwerer" zugunsten neutraler
  Beschreibungen ("diese Woche ruhiger"); die CSS-Klasse für rückläufige
  Werte ist bewusst NICHT mehr rot eingefärbt (wirkt auf Dashboard UND
  "Mein Tag" gleichermaßen, da beide dieselbe Funktion nutzen).
- Mood-Heatmap-Kacheln ("Mein Tag" → Verlauf) zeigen kein kleines,
  schlecht lesbares Emoji mehr - Farbe bleibt das alleinige Signal in der
  Kachel, Details weiterhin per Tooltip/Antippen abrufbar.

## [0.1.2] - 2026-08-02

### Added
- Bottom-Tab-Bar für echtes Mobile (`partials/tabbar.html`, analog Scandy-
  Lite): 4 Kernziele für Teilnehmer:innen (Projekte, Wochenberichte, Mein
  Tag, Bewerbungen), 3 für Berufstrainer:innen; seltenere Ziele bleiben im
  Hamburger-Menü.
- Dashboard für Teilnehmer:innen ausgebaut: Kachel-Schnellzugriff
  (`.quick-tiles`, analog Scandy-Lite) statt reiner Karten, plus
  "Deine Woche im Rückblick" mit Stimmungs-Trend und Bewerbungs-Überblick
  neben dem bestehenden Schritte-Signal - durchgehend sanfte Sprache ohne
  Bewertung (CLAUDE.md Abschnitt 24/25).

## [0.1.1] - 2026-08-02

### Added
- CSRF-Schutz für alle mutierenden Formulare/Requests.

### Fixed
- Hauptnav war auf breiten Screens dauerhaft unsichtbar (fehlende
  Gegenregel zu Alpines `x-show`, siehe Commit `e69b2bc`).
- Grellweiße native Formularelemente im Dark-Mode (fehlende
  `color-scheme`-Deklaration).
- **Wichtig für Cache-Busting**: versionierte Assets (`?v={{ asset_version }}`)
  werden ein Jahr lang unveränderlich gecacht (`app/core/static_cache.py`) -
  jede CSS/JS-Änderung MUSS ab sofort mit einem Bump von `__version__`
  (`app/version.py`) einhergehen, sonst bekommen wiederkehrende Browser
  die alte, gecachte Datei weiter ausgeliefert (genau das ist bei den
  beiden obigen Fixes zunächst passiert).

## [0.1.0] - 2026-08-02

### Added
- UI/UX-Audit mit 22 umgesetzten Befunden (siehe `tasks/uiux-audit/`):
  u.a. maskierte Passwortfelder, gestaltete Fehlerseiten statt roher
  JSON-Antworten, tastaturbedienbare Alternative zum Kanban-Drag&Drop,
  Dark-Mode, `aria-live` auf Speicher-Toasts, mobile Nav-Kollaps.
- Manueller Dark-/Light-Mode-Umschalter (zusätzlich zur automatischen
  Systemerkennung), `localStorage`-gestützt.
- Struktur an das Schwestermodul Scandy-Lite angeglichen: Alpine.js + htmx
  vendort, `asset_version`-Cache-Busting, `.icon-btn`/`.link-btn`-Klassen,
  `app/core/static_cache.py` (versionierte Assets cachebar bis zu einem
  Jahr), Test-Scaffolding (`tests/`, `pytest.ini`, `ruff.toml`).

### Known Gaps
- Kein CSRF-Schutz auf POST-Formularen (im Unterschied zu Scandy-Lite) -
  vorgemerkt als eigener, sicherheitskritischer Auftrag.
