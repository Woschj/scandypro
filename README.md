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

## Virenprüfung für Uploads

Standardmäßig **aus**. Vor dem ersten echten Bewerbungs-Upload aktivieren –
Dateien wandern zwischen Teilnehmenden und Berufstrainer:innen und werden
dort lokal geöffnet:

```bash
docker compose --profile virenscan up -d
```

Danach in der `.env` `CLAMAV_HOST=clamav` setzen und die App neu starten.
Der erste Start des ClamAV-Containers dauert einige Minuten (Signatur-
Download, ca. 1 GB).

Sobald `CLAMAV_HOST` gesetzt ist, ist die Prüfung **verbindlich**: Ist der
Scanner nicht erreichbar, lehnt ScandyPro den Upload ab, statt ihn
ungeprüft zu speichern. Gescannt wird vor dem Verschlüsseln – eine
erkannte Datei erreicht die Platte gar nicht erst.

## Backup

**Vor dem Einsatz mit echten Teilnehmerdaten einrichten.** Vollständige
Anleitung inkl. Restore-Probe: [docs/BACKUP.md](docs/BACKUP.md).

Zwei Werte in die `.env` – beide sind nötig, die Passphrase **und** ein
Ziel außerhalb des Hosts:

```bash
echo "BACKUP_PASSPHRASE=$(openssl rand -base64 48)" >> .env
echo "BACKUP_DIR=/mnt/backup/scandypro" >> .env    # Pfad anpassen!
./scripts/backup.sh
```

> ⚠️ **`BACKUP_DIR` wirklich setzen.** Ohne diese Zeile landen die Archive
> in `./backups`, also im Projektverzeichnis auf derselben Platte wie die
> Docker-Volumes – derselbe Hardwaredefekt nimmt dann Original *und*
> Sicherung mit. Sinnvoll ist ein Netzlaufwerk, ein zweiter Datenträger
> oder ein gemounteter Objektspeicher. Der Standardwert existiert nur,
> damit ein Probelauf ohne Vorbereitung funktioniert.

Sichert Datenbank (`pg_dump`) und Uploads in **ein** verschlüsseltes Archiv
und rotiert alte Stände (7 täglich / 4 wöchentlich / 6 monatlich). Erkennt
Docker-Compose- und LXC-Installation automatisch. Ohne
`BACKUP_PASSPHRASE` bricht das Skript bewusst ab – der Dump enthält neben
den verschlüsselten Art.-9-Feldern auch Klartext-Stammdaten und
Passwort-Hashes.

Täglich per Cron:

```cron
15 3 * * *  cd /opt/scandypro && ./scripts/backup.sh >> /var/log/scandypro-backup.log 2>&1
```

Zurückspielen (ersetzt Datenbank und Uploads vollständig):

```bash
./scripts/restore.sh --pruefen /mnt/backup/scandypro/scandypro-<zeitstempel>.tar.gz.enc   # nur prüfen
./scripts/restore.sh /mnt/backup/scandypro/scandypro-<zeitstempel>.tar.gz.enc            # echt
```

`BACKUP_PASSPHRASE` **und** `FIELD_ENCRYPTION_KEY` gehören getrennt vom
Backup aufbewahrt – ohne beide zusammen ist ein Archiv nicht
wiederherstellbar.

**Ein Backup, das nie zurückgespielt wurde, ist kein Backup.** Die
Restore-Probe steht als Checkliste in
[docs/BACKUP.md](docs/BACKUP.md#den-restore-proben) und sollte nach jeder
Schema-Änderung einmal durchlaufen werden.

## Datenschutz-Bausteine (v0.1)

- **Verschlüsselung**: Wohlbefinden-Kommentare, Bewerbungsnotizen und alle
  hochgeladenen Dateien (Lebenslauf/Zeugnisse/Anschreiben/Deckblatt) liegen
  Fernet-verschlüsselt in DB bzw. Upload-Volume (`app/core/crypto.py`).
  Schlüssel kommt aus `FIELD_ENCRYPTION_KEY` (ENV). Rotation wird
  unterstützt: mehrere kommagetrennte Schlüssel (neuester zuerst) plus
  `scripts/reencrypt.py` für die Bestandsdaten - Ablauf in
  [docs/BACKUP.md](docs/BACKUP.md#schlüsselrotation-und-backups).
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

### Was die Einrichtung selbst scharfschalten muss

Diese Punkte sind fertig implementiert, aber im Auslieferungszustand
**nicht aktiv**. Sie schützen erst, wenn sie eingerichtet werden:

| Was | Wie | Ohne das |
|---|---|---|
| **Backup** | `BACKUP_PASSPHRASE` + `BACKUP_DIR` in die `.env`, Cron-Eintrag – siehe [Backup](#backup) | Kein Backup. Bei Volume-Verlust sind Tagebücher, Bewerbungen und Wochenberichte weg. |
| **Backup-Ziel außerhalb des Hosts** | `BACKUP_DIR` auf Netzlaufwerk/zweiten Datenträger | Sicherung liegt neben dem Original und stirbt mit ihm. |
| **Virenscan** | `docker compose --profile virenscan up -d` + `CLAMAV_HOST=clamav` | Uploads werden nur auf Endung/Größe/Magic Bytes geprüft, nicht auf Inhalt. |
| **TLS** | siehe [TLS (Produktivbetrieb)](#tls-produktivbetrieb) | Login und Session-Cookie gehen unverschlüsselt über das Netz. |

Alle vier sind bewusst opt-in, damit ein Probelauf ohne Vorbereitung
funktioniert – für echte Teilnehmerdaten ist keines davon optional.

### Weiterhin offen

Die wichtigsten Punkte in Kürze:

- **Migrationstest läuft nicht automatisch mit** (PR-002) – seit 0.1.45
  gibt es `tests/test_migrationen_postgres.py` (echter `upgrade head`,
  Drift-Abgleich, Rundlauf), er wird ohne gesetztes `TEST_POSTGRES_URL`
  aber übersprungen. Vor einem Release bewusst mit laufender Datenbank
  ausführen – siehe Modul-Docstring.
- **Vollständige Konto-Löschung** (PR-005) – aktuell nur Inhaltsdaten
  löschbar, siehe oben.
- **Kein Monitoring** (PR-007) – ein stiller Ausfall, auch des Backups,
  fällt erst auf, wenn jemand anruft.
- **DSGVO-Dokumentation und rechtliche Prüfung** (PR-008) – organisatorisch,
  aber echter Blocker bei Art.-9-Daten.
- **2FA für Betreuer-/Admin-Rollen** (PR-009) – Entscheidung offen; über
  Authentik erzwingbar, ohne in ScandyPro selbst etwas zu bauen.
- Eigene Tests für `bewerbungen.py`, `wochenberichte.py` und `oidc.py`
  fehlen weiterhin (PR-006 ist nur für `admin.py` erledigt).

Erledigt seit 0.1.42: Berechtigungs- und Löschtests laut
CLAUDE.md-Review-Checkliste, Benutzerverwaltung und Virenscan – aktuell
**98 Tests** (siehe [`tasks/codebase-audit/README.md`](tasks/codebase-audit/README.md)
und [`tasks/produktivreife/README.md`](tasks/produktivreife/README.md)).
Backup inkl. geprobtem Restore seit 0.1.44.

Diese Punkte sind kein Versehen, sondern bewusst auf spätere Phasen
verschoben, um zuerst die Kernfunktionalität bewerten zu können – siehe
Roadmap in [docs/KONZEPT.md](docs/KONZEPT.md#5-phasen--roadmap).
