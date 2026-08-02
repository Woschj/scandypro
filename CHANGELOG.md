# Changelog

Alle nennenswerten Änderungen an ScandyPro werden hier dokumentiert.

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/) (vor
1.0.0: `0.MINOR.PATCH`, MINOR kann auch für neue Features brechende Änderungen
enthalten - üblich für Software vor dem ersten stabilen Release). Gepflegt
analog zum Schwestermodul Scandy-Lite.

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
