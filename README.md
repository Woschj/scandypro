# ScandyPro – Prototyp

Funktionaler Klick-Prototyp zur Bewertung der Kernmodule: Kanban
(Abteilung → Handlungsfeld → Teilnehmergruppe → Board), Wochenberichte mit
Tagesfeldern (Mo-Fr, angelehnt an Scandy2), Wohlbefinden-Tracking als
interaktive Drag-Zeitlinie, Bewerbungs-Tracking mit Datei-Upload
(Lebenslauf/Zeugnisse/Anschreiben). Konzept und Datenschutzgrundlagen:
siehe [CLAUDE.md](CLAUDE.md) und [docs/](docs/).

## Starten

```bash
cp .env.example .env   # ggf. Werte anpassen
# SECRET_KEY:            python3 -c "import secrets; print(secrets.token_hex(32))"
# FIELD_ENCRYPTION_KEY:  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose up -d --build
```

Beim ersten Start führt die App automatisch `alembic upgrade head` aus (siehe
`app/core/database.py`) - kein manueller Migrationsschritt nötig.

App läuft danach unter **http://localhost:8080**.

Beim ersten Start (mit `SEED_DEMO_DATA=true` in `.env`) werden Demo-Accounts
angelegt, Passwort jeweils `demo1234`:

| Rolle | E-Mail | Abteilung |
|---|---|---|
| Teilnehmer | teilnehmer@demo.local | Medien & Digital |
| Teilnehmer | teilnehmer2@demo.local | Medien & Digital |
| Berufstrainer | trainer@demo.local | leitet Handlungsfeld "Video-Projekte" |
| Psychosoziale Mitarbeit | psycho@demo.local | betreut teilnehmer@demo.local (PSM-Zuordnung) |
| Einrichtungs-Admin | admin@demo.local | verwaltet Abteilungen/Handlungsfelder/PSM-Zuordnungen |

Zusätzlich vorhanden: Handlungsfeld "Video-Projekte" (Leitung: Bernd
Berufstrainer) in der Abteilung Medien & Digital, die Teilnehmergruppe
"Projektteam Video" (beide Demo-Teilnehmer) mit dem freigegebenen Board
"Imagefilm Werkstatt", sowie ein bereits abgegebener Wochenbericht von
Tanja Teilnehmer – so sind Kanban-Zusammenarbeit und Wochenberichte
direkt sichtbar, ohne erst Grunddaten anlegen zu müssen.

## Word-Vorlage für Wochenberichte

`app/assets/wochenbericht_vorlage.docx` ist das von der Einrichtung
vorgegebene, unterschriftsfähige Formular ("Wochenprotokoll/Tätigkeits-
nachweis") – ScandyPro befüllt es nur, das Layout gehört der Einrichtung.
Wird das Formular dort geändert, muss die Vorlage hier ausgetauscht
werden; die docxtpl-Platzhalter müssen dabei erhalten bleiben: `{{ kw }}`,
`{{ name }}` und je Wochentag (`montag` … `freitag`) `{{ <tag>_tasks }}`,
`{{ <tag>_datum }}`, `{{ <tag>_hours }}`.

## Stoppen / zurücksetzen

```bash
docker compose down          # Container stoppen, Daten bleiben (Volume)
docker compose down -v       # Container stoppen UND Datenbank löschen
```

## Datenschutz-Bausteine (v0.1)

- **Verschlüsselung**: Wohlbefinden-Kommentare, Bewerbungsnotizen und alle
  hochgeladenen Dateien (Lebenslauf/Zeugnisse/Anschreiben/Deckblatt) liegen
  Fernet-verschlüsselt in DB bzw. Upload-Volume (`app/core/crypto.py`).
  Schlüssel kommt aus `FIELD_ENCRYPTION_KEY` (ENV) - noch keine
  Key-Rotation.
- **Freigabe-System (Consent)**: Teilnehmer:innen geben Wohlbefinden
  gezielt für ihre PSM-Kontaktperson bzw. Bewerbungen für ihren
  Berufstrainer frei (ganz oder befristet/einzeln), jederzeit widerrufbar
  - siehe `/wohlbefinden`, `/bewerbungen`, zentrale Übersicht unter
  `/freigaben`. Ersetzt nicht die organisatorische PSM-/Trainer-Zuordnung,
  ergänzt sie (beide nötig für Fremdzugriff).
  Granularität ist bewusst vereinfacht: "gesamter Verlauf oder befristet"
  (Wohlbefinden) bzw. "alle oder eine bestimmte Bewerbung" (Bewerbungen) -
  Freigabe einzelner Einträge (`docs/KONZEPT.md`) ist eine spätere
  Ausbaustufe.
- **Audit-Log**: jeder Fremdzugriff (PSM/Trainer über eine Freigabe) wird
  protokolliert (`app/core/audit.py`), einsehbar für Teilnehmer:innen unter
  `/freigaben`.
- **Hard-Delete**: Teilnehmer:innen können unter `/freigaben` alle eigenen
  Wohlbefinden- bzw. Bewerbungsdaten (inkl. Dateien und Freigaben)
  unwiderruflich löschen (`app/core/deletion.py`). Der Zugang (Login)
  bleibt bestehen - eine vollständige Konto-/Account-Löschung ist Teil der
  geplanten zentralen Benutzerverwaltung (siehe unten), da Kanban-Karten
  aktuell `ersteller_id` ohne Kaskade referenzieren.
- **Alembic-Migrationen** ersetzen das frühere `create_all`
  (`alembic/versions/`, `app/core/database.py`).

## Bekannte Lücken dieses Prototyps (bewusst, siehe CLAUDE.md)

Dieser Stand dient der **Funktions-/UX-Bewertung**, nicht dem
Produktivbetrieb. Vor echtem Einsatz mit echten Teilnehmerdaten fehlen
noch zwingend:

- **Virenscan/Content-Prüfung** von Uploads – aktuell nur Endungs- und
  Größen-Whitelist (`app/core/uploads.py`), kein Scan des Dateiinhalts
- **Vollständige Konto-Löschung** (Login/Account selbst) – aktuell nur
  Inhaltsdaten löschbar, siehe oben
- **Key-Rotation** für die Feldverschlüsselung
- **TLS** – Caddy läuft hier ohne Domain/Auto-HTTPS auf Port 8080 (nur für
  lokale Bewertung, nicht so deployen)
- Tests (Berechtigungs-/Löschtests laut CLAUDE.md-Review-Checkliste)

Diese Punkte sind kein Versehen, sondern bewusst auf spätere Phasen
verschoben, um zuerst die Kernfunktionalität bewerten zu können – siehe
Roadmap in [docs/KONZEPT.md](docs/KONZEPT.md#5-phasen--roadmap).
