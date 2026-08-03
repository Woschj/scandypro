# ScandyPro – Prototyp

Funktionaler Klick-Prototyp zur Bewertung der Kernmodule: Kanban
(Abteilung → Handlungsfeld → Teilnehmergruppe → Board), Wochenberichte mit
Tagesfeldern (Mo-Fr, angelehnt an Scandy2), Wohlbefinden-Tracking als
interaktive Drag-Zeitlinie, Bewerbungs-Tracking mit Datei-Upload
(Lebenslauf/Zeugnisse/Anschreiben). Konzept und Datenschutzgrundlagen:
siehe [CLAUDE.md](CLAUDE.md) und [docs/](docs/).

## Starten

Zwei Wege - beide analog zu [Scandy-Lite](https://github.com/Woschj/scandy-lite),
gedacht für Parallelbetrieb auf demselben Host mit derselben Bedienung.

### Docker (Kurzstart)

```bash
git clone https://github.com/Woschj/scandypro.git && cd scandypro
./install.sh          # Linux/Mac
# oder: .\install.ps1   # Windows (PowerShell)
```

Erzeugt automatisch eine `.env` mit sicheren, zufällig generierten Werten
(`SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`),
baut und startet den Stack, wartet auf den ersten erfolgreichen Start und
zeigt danach URL + Admin-Zugangsdaten an. Erneutes Ausführen ist gefahrlos
(eine bereits vorhandene `.env` wird nicht überschrieben).

Manuell statt über das Skript:

```bash
cp .env.example .env   # Werte anpassen, siehe Kommentare in der Datei
docker compose up -d --build
```

Beim ersten Start führt die App automatisch `alembic upgrade head` aus (siehe
`app/core/database.py`) - kein manueller Migrationsschritt nötig. App läuft
danach unter **http://localhost:8080** (Port über `APP_PORT` in `.env`
anpassbar, z. B. für Parallelbetrieb mit weiteren Stacks auf demselben Host).

### Proxmox VE (LXC-Container)

Auf dem Proxmox-Host (als root):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Woschj/scandypro/main/proxmox/ct/scandypro.sh)"
```

Legt einen eigenen, unprivilegierten LXC-Container an (Debian 12,
PostgreSQL 16, Python-venv, systemd-Dienst `scandypro` auf Port 8000) und
zeigt am Ende IP + Admin-Zugangsdaten. Erneuter Aufruf des Skripts bietet
im Menü "Aktualisieren" für eine bestehende Installation an (git pull +
Migrationen + Dienst-Neustart). Läuft komplett unabhängig von einer
Scandy-Lite-Installation im selben Proxmox-Host (eigener Container, eigene
IP, keine Port-Kollision).

### Admin-Zugang (Produktivbetrieb)

Ohne `SEED_DEMO_DATA` legt die App beim ersten Start automatisch einen
Einrichtungs-Admin an, falls `ADMIN_EMAIL`/`ADMIN_PASSWORD` in der `.env`
gesetzt sind (siehe `app/core/seed.py:seed_admin`) - beide Installationswege
oben setzen das automatisch. Nach dem ersten erfolgreichen Login das
Passwort über **Mein Konto** (`/konto`, verlinkt im User-Chip oben rechts)
ändern und `ADMIN_PASSWORD` aus der `.env` entfernen (liegt bis dahin im
Klartext).

Weitere Accounts legt der Admin unter **Benutzerverwaltung**
(`/admin/benutzer`) an - Name, E-Mail, Passwort und Rolle festlegen; die
Rolle bestehender Accounts lässt sich dort ebenfalls jederzeit ändern
(außer der eigenen, aus Sicherheitsgründen).

### Demo-Daten (nur Bewertungs-/Testphase)

Mit `SEED_DEMO_DATA=true` in `.env` werden beim ersten Start zusätzlich feste
Demo-Accounts angelegt, Passwort jeweils `demo1234` - **niemals in echten
Einrichtungen aktivieren** (siehe Kommentar in `app/core/config.py`):

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

## Single Sign-On (SSO)

Optional: Login über einen OIDC-Provider wie Authentik, gedacht für einen
gemeinsamen Login mit [Scandy-Lite](https://github.com/Woschj/scandy-lite)
(zentral gesteuerte Nutzer:innen über beide Apps hinweg). Ohne Konfiguration
verhält sich ScandyPro exakt wie oben beschrieben - lokales Login bleibt
immer verfügbar. Vollständige Installations- und Anbindungsanleitung
(inkl. Authentik selbst aufsetzen, falls noch keine Instanz existiert):
[SSO_AUTHENTIK.md](SSO_AUTHENTIK.md).

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
