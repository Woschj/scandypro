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

Legt einen eigenen, unprivilegierten LXC-Container an (Debian 13,
PostgreSQL 16, Python-venv, zwei systemd-Dienste `scandypro` (HTTP, nur
`127.0.0.1:8000`, nicht von außen erreichbar) und `scandypro-https`
(selbstsigniertes Zertifikat, `0.0.0.0:8443`) - analog zu Scandy-Lite,
siehe Abschnitt "TLS (Produktivbetrieb)") und zeigt am Ende IP +
Admin-Zugangsdaten. Erneuter Aufruf des Skripts bietet im Menü
"Aktualisieren" für eine bestehende Installation an (git pull + Migrationen
+ Dienst-Neustart). Läuft komplett unabhängig von einer
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

## Proxmox-Stack: beliebige Kombination installieren

[`proxmox/ct/scandy-stack.sh`](proxmox/ct/scandy-stack.sh) ist **ein**
Einstiegspunkt für den ganzen Stack - Mehrfachauswahl-Menü (ScandyPro /
Scandy-Lite / Authentik, jede Kombination), installiert die gewählten
Komponenten danach nacheinander. Auf dem Proxmox-Host (als root):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Woschj/scandypro/main/proxmox/ct/scandy-stack.sh)"
```

Ruft dafür bewusst nur die bereits vorhandenen, einzeln getesteten
Installer der drei Komponenten auf (`proxmox/ct/scandypro.sh` in diesem
Repo, `proxmox/ct/scandy-lite.sh` im [Scandy-Lite-Repo](https://github.com/Woschj/scandy-lite),
das offizielle [Authentik-Community-Skript](https://community-scripts.github.io/ProxmoxVE/scripts?id=authentik))
statt eigene Container-Erstellungs-Logik zu duplizieren - jede Komponente
bekommt weiterhin ihren eigenen, unabhängigen LXC-Container.

Werden Authentik **und** mindestens eine App zusammen ausgewählt, versucht
das Skript danach automatisch, einen OAuth2/OIDC-Provider + Application je
App in Authentik anzulegen und die `OIDC_*`-Werte direkt in deren `.env`
einzutragen (per `ak apply_blueprint`) - spart die manuellen Schritte aus
`SSO_AUTHENTIK.md` Teil B. Live gegen einen echten Proxmox-Host bis zum
funktionierenden SSO-Login durchgetestet (siehe CHANGELOG.md 0.1.32-0.1.36).
Schlägt ein einzelner Teilschritt trotzdem fehl (z. B. abweichendes
Authentik-Layout in einer neueren Version), bricht dank sauberer
Fehlerisolierung nur dieser Teilschritt ab - Installation und
Abschluss-Zusammenfassung bleiben unberührt, die SSO-Verknüpfung muss dann
für die betroffene App manuell nach `SSO_AUTHENTIK.md` Teil B nachgeholt
werden.

**Wichtig, IP-Stabilität**: die Automatisierung trägt die zum
Installationszeitpunkt per DHCP vergebenen IP-Adressen fest in Authentiks
Redirect-URI und in `OIDC_ISSUER` der App(s) ein. Ändert sich eine dieser
IPs später (Reboot, Lease-Ablauf), bricht SSO still, bis das manuell
korrigiert wird - allen beteiligten Containern feste IPs oder
DHCP-Reservierungen geben (das Skript weist am Ende noch einmal darauf
hin).

Die einzelnen Installer bleiben weiterhin auch direkt aufrufbar (siehe
oben bzw. Scandy-Lite-README) - `scandy-stack.sh` ist nur die bequeme
Sammelvariante, keine Voraussetzung.

## TLS (Produktivbetrieb)

Im Standard-Setup läuft ScandyPro **unverschlüsselt über HTTP** (Caddy ohne
Domain, siehe `caddy/Caddyfile`) – nur für lokale Bewertung geeignet. Da
ScandyPro besondere Kategorien personenbezogener Daten nach Art. 9 DSGVO
verarbeitet (Wohlbefinden, Bewerbungsdetails, siehe CLAUDE.md Abschnitt 2),
ist TLS für jeden Betrieb mit echten Teilnehmerdaten **zwingend** – ohne
TLS werden Login-Formular und Session-Cookie unverschlüsselt über das Netz
übertragen. Das gilt genauso, wenn der Server **nur intern** (LAN/VPN,
keine Verbindung ins öffentliche Internet) erreichbar ist – "intern" heißt
nicht "vertrauenswürdiges Netz", jedes Mitlesen im selben Netzsegment
(kompromittiertes Gerät, offenes WLAN, o. Ä.) betrifft echte Gesundheits-
und Bewerbungsdaten. Zwei gleichwertige Wege, je nachdem ob eine Domain
existiert:

### Variante A: echte Domain (öffentlich erreichbar)

Automatisches Let's-Encrypt-Zertifikat, Caddy übernimmt Ausstellung und
Erneuerung selbständig – kein manuelles Zertifikats-Handling nötig:

1. Domain per DNS-A-Record auf die öffentliche IP dieses Hosts zeigen
   lassen
2. `caddy/Caddyfile.domain-example` nach `caddy/Caddyfile` kopieren, darin
   die Platzhalter-Domain durch die echte ersetzen
3. In `compose.yaml` beim `caddy`-Service den `ports`-Eintrag von
   `${APP_PORT:-8080}:80` auf `80:80` **und** `443:443` ändern (Port 80
   wird für die Zertifikatsausstellung gebraucht, nicht nur zum Umleiten)
4. In `.env` `SESSION_COOKIE_SECURE=true` setzen (siehe `.env.example`) -
   sorgt dafür, dass das Login-Cookie das Secure-Flag bekommt
5. `docker compose up -d --build`

### Variante B: rein internes Netz, keine Domain

Für einen Server, der nur intern erreichbar ist (z. B. LAN/VPN ohne
öffentliche IP oder DNS-Eintrag) – Caddy erzeugt eine eigene, lokale CA und
stellt sich selbst ein Zertifikat aus, funktioniert per nackter IP
(`https://<server-ip>:8443`), kein DNS-Eintrag nötig. Einziger Unterschied
zu Variante A für Nutzer:innen: Browser zeigen beim ersten Aufruf **pro
Gerät einmalig** eine Zertifikatswarnung (unbekannte CA, nicht öffentlich
vertrauenswürdig) – "Erweitert -> Trotzdem fortfahren" bestätigen, danach
funktioniert die Seite wie gewohnt. Ausdrücklich für ein wirklich internes
Netz gedacht – diesen Port nicht zusätzlich per Portweiterleitung ins
Internet öffnen (siehe Warnhinweis in `caddy/Caddyfile.internal-tls-example`
zu ungeschütztem On-Demand-TLS).

1. `caddy/Caddyfile.internal-tls-example` nach `caddy/Caddyfile` kopieren
   (keine Anpassung nötig - kein Domain-Platzhalter enthalten)
2. In `compose.yaml` beim `caddy`-Service den `ports`-Eintrag von
   `${APP_PORT:-8080}:80` auf `${APP_HTTPS_PORT:-8443}:8443` ändern
3. In `.env` `SESSION_COOKIE_SECURE=true` setzen
4. `docker compose up -d --build`
5. Aufrufen über `https://<server-ip>:8443`

Funktioniert auch für SSO/Authentik (siehe unten) – Authentik prüft beim
Redirect nur, dass die Redirect-URI mit `https://` beginnt, nicht ob das
Zertifikat öffentlich vertrauenswürdig ist. Einzige Einschränkung:
Authentik selbst braucht ebenfalls HTTPS (egal ob Variante A oder B), sonst
lehnt es die Redirect-URI unter Umständen ab.

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
Produktivbetrieb.

> 📋 **Vollständige Liste mit Schweregrad, Begründung und Reihenfolge:**
> [`tasks/produktivreife/README.md`](tasks/produktivreife/README.md)

Die wichtigsten Punkte in Kürze:

- **Kein Backup** (PR-001) – Datenbank und Uploads liegen ausschließlich in
  Docker-Volumes, ohne Dump, Wiederherstellungs-Prozedur oder Restore-Test.
  Das einzige Risiko auf der Liste, bei dem hinterher nichts mehr zu retten
  ist – deshalb zuerst angehen.
- **Migrationen ohne echten Postgres-Testlauf** (PR-002) – die Kette wird
  seit 0.1.43 statisch geprüft (`tests/test_migrationen.py`), aber nie
  tatsächlich ausgeführt. Die beiden jüngsten Migrationen sind noch nie
  gegen PostgreSQL gelaufen.
- **Virenscan/Content-Prüfung** von Uploads (PR-003) – es gibt Endungs-,
  Größen- und Magic-Byte-Prüfung (`app/core/uploads.py`), aber keinen Scan
  auf Schadinhalte.
- **Key-Rotation** für die Feldverschlüsselung (PR-004).
- **Vollständige Konto-Löschung** (PR-005) – aktuell nur Inhaltsdaten
  löschbar, siehe oben.
- **DSGVO-Dokumentation und rechtliche Prüfung** (PR-008) – organisatorisch,
  aber echter Blocker bei Art.-9-Daten.
- **TLS im Standard-Setup** – Caddy läuft ohne eigene Domain auf Port 8080
  ohne Verschlüsselung (nur für lokale Bewertung, nicht so deployen). Sowohl
  echte Domain mit automatischem HTTPS als auch selbstsigniertes HTTPS
  fürs rein interne Netz sind bereits vorbereitet, aber ein bewusster
  manueller Schritt – siehe Abschnitt "TLS (Produktivbetrieb)" unten.

Erledigt seit 0.1.42: Berechtigungs- und Löschtests laut
CLAUDE.md-Review-Checkliste (31 Tests, siehe
[`tasks/codebase-audit/README.md`](tasks/codebase-audit/README.md)).

Diese Punkte sind kein Versehen, sondern bewusst auf spätere Phasen
verschoben, um zuerst die Kernfunktionalität bewerten zu können – siehe
Roadmap in [docs/KONZEPT.md](docs/KONZEPT.md#5-phasen--roadmap).
