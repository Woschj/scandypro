# Changelog

Alle nennenswerten Änderungen an ScandyPro werden hier dokumentiert.

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/) (vor
1.0.0: `0.MINOR.PATCH`, MINOR kann auch für neue Features brechende Änderungen
enthalten - üblich für Software vor dem ersten stabilen Release). Gepflegt
analog zum Schwestermodul Scandy-Lite.

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
