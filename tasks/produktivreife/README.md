# ScandyPro – Was einem Produktiveinsatz im Weg steht

**Stand:** 0.1.45 (2026-08-12)
**Frage:** Was fehlt noch, bevor die App mit echten Teilnehmerdaten laufen kann?

**Methode:** Durchsicht von Deployment (`compose.yaml`, `Dockerfile`,
`install.sh`, `proxmox/`), Konfiguration (`.env.example`, Installer-Skripte),
Verschlüsselung, Upload-Pfad, Migrationskette und der bereits dokumentierten
Lücken in [`README.md`](../../README.md) und
[`docs/DATENSCHUTZ_UND_BERECHTIGUNGEN.md`](../../docs/DATENSCHUTZ_UND_BERECHTIGUNGEN.md).

Ergänzt den [Codebase-Audit](../codebase-audit/README.md) (Codequalität) um
die Betriebs- und Compliance-Sicht.

---

## Übersicht

| ID | Titel | Schwere | Aufwand | Status |
|---|---|---|---|---|
| [PR-001](#pr-001) | Kein Backup – Totalverlust-Risiko | **Kritisch** | M | ✅ behoben (Restore geprobt) |
| [PR-002](#pr-002) | Migrationen laufen in keinem Test | **Hoch** | M | ✅ behoben (2 Fehler gefunden) |
| [PR-003](#pr-003) | Kein Virenscan bei Uploads | **Hoch** | M | ✅ behoben (opt-in, fail closed) |
| [PR-004](#pr-004) | Keine Schlüsselrotation | Mittel | L | ✅ behoben (live geprobt) |
| [PR-005](#pr-005) | Kontolöschung unvollständig (Art. 17) | Mittel | L | ✅ behoben (live geprobt) |
| [PR-006](#pr-006) | Router ohne eigene Tests | Mittel | M | ✅ behoben (48 Tests) |
| [PR-007](#pr-007) | Kein Monitoring, keine Redundanz | Niedrig | M | offen |
| [PR-008](#pr-008) | DSGVO-Dokumentation und rechtliche Prüfung | **Blocker** | – | organisatorisch |
| [PR-009](#pr-009) | 2FA für Betreuer-/Admin-Rollen | Offen | M | ⚪ entschieden: nicht umsetzen |

---

## Was bereits sauber ist

Damit nicht an der falschen Stelle gesucht wird – das ist geprüft und in
Ordnung:

- **Secrets:** Der Proxmox-Installer (`proxmox/install/scandypro-install.sh`)
  erzeugt `SECRET_KEY` und `FIELD_ENCRYPTION_KEY` per `openssl rand`, setzt
  `SEED_DEMO_DATA=false` und `SESSION_COOKIE_SECURE=true`. Die
  Demo-Zugänge aus `.env.example` landen also nicht im Produktivsystem.
- **TLS:** Sowohl echte Domain mit automatischem HTTPS als auch
  selbstsigniertes HTTPS fürs interne Netz sind vorbereitet
  (`caddy/Caddyfile.domain-example`, `caddy/Caddyfile.internal-tls-example`).
- **Anwendungssicherheit:** Feldweise Verschlüsselung, CSRF-Schutz mit
  stabilem Session-Secret, Rate-Limiting auf Login *und* Passwortwechsel,
  Upload-Prüfung per Magic Bytes, Audit-Logs, zentrale Zugriffsschicht –
  seit 0.1.42 mit 31 Berechtigungs- und Löschtests abgesichert.
- **Container:** non-root, Healthcheck, reproduzierbarer Build.

---

## PR-001 – Kein Backup {#pr-001}

**Schwere: Kritisch · Aufwand: M · Status: behoben (0.1.44)**

> ✅ **Umgesetzt.** `scripts/backup.sh` und `scripts/restore.sh`,
> dokumentiert in [`docs/BACKUP.md`](../../docs/BACKUP.md). Beide
> Betriebsarten (Docker Compose und die direkte Proxmox-LXC-Installation)
> werden automatisch erkannt.
>
> Das Archiv wird mit `openssl enc -aes-256-cbc -pbkdf2` verschlüsselt;
> ohne gesetzte `BACKUP_PASSPHRASE` bricht das Skript ab, statt still einen
> ungeschützten Dump abzulegen. Rotation: 7 täglich / 4 wöchentlich /
> 6 monatlich, getrennt gezählt, Wochen- und Monatsstände als Hardlink.
>
> **Der Restore wurde tatsächlich geprobt**, nicht nur geschrieben:
> Ausgangszustand festgehalten → Backup → eine Testmarke in die DB
> geschrieben, die im Backup nicht enthalten war → Restore → alle
> Zeilenzahlen wieder identisch (145 Nutzende, 282 Karten, 8174
> Tagebucheinträge, 378 Bewerbungen), Testmarke verschwunden, und – der
> eigentlich wichtige Teil – die Fernet-verschlüsselten Felder ließen sich
> danach korrekt entschlüsseln. Der Ablauf steht als Checkliste in
> `docs/BACKUP.md` und sollte nach jeder Schema-Änderung wiederholt werden.
>
> Offen bleibt organisatorisch: Auslagerung des `BACKUP_DIR` vom Host weg
> und eine Benachrichtigung bei stillem Ausfall (hängt an PR-007).

Ursprünglicher Befund:

Es existiert **kein Backup-Mechanismus**. Datenbank und Uploads liegen in
Docker-Volumes (`scandypro_db_data`, `scandypro_uploads`), es gibt keinen
Dump, keine Wiederherstellungs-Prozedur und keinen Restore-Test.

Bei Art.-9-Daten ist das der schwerwiegendste Punkt der ganzen Liste: ein
beschädigtes Volume, ein Fehlgriff beim Update oder ein fehlgeschlagenes
`docker compose down -v` – und Tagebücher, Bewerbungen und Wochenberichte
sind unwiederbringlich verloren. Das ist kein Feature-Mangel, sondern das
einzige Risiko auf dieser Liste, bei dem hinterher nichts mehr zu retten
ist.

**Vorschlag:**
- `pg_dump` + Archiv des Uploads-Volumes per Cron (täglich), verschlüsselt
  abgelegt (die Uploads sind bereits verschlüsselt, der DB-Dump **nicht** –
  er enthält u.a. die verschlüsselten Felder, aber auch Klartext-Stammdaten).
- Aufbewahrung mit Rotation (z.B. 7 täglich / 4 wöchentlich / 6 monatlich),
  Ablage **außerhalb** des Hosts.
- **Restore einmal wirklich proben** und die Prozedur dokumentieren – ein
  ungetestetes Backup ist kein Backup.
- Zusätzlich: Proxmox-eigene LXC-Snapshots decken den Host ab, ersetzen aber
  keinen anwendungskonsistenten DB-Dump.

---

## PR-002 – Migrationen laufen in keinem Test {#pr-002}

**Schwere: Hoch · Aufwand: M · Status: teilweise behoben**

Die Tests bauen ihr Schema über `SQLModel.metadata.create_all`
(`tests/conftest.py`) – **Alembic läuft dabei nie**. Die Migrationen werden
erst beim Start der echten App ausgeführt (`app/core/database.py:init_db`);
scheitert eine, startet die Anwendung gar nicht.

**Das ist bereits passiert:** eine neue Migration bekam versehentlich
dieselbe Revision-ID wie eine ältere, Alembic fand zwei Heads und brach ab –
aufgefallen erst auf dem Server.

**Bereits umgesetzt** (`tests/test_migrationen.py`, 5 Tests): statische
Prüfung der Kette ohne Datenbank – keine doppelten Revision-IDs, genau ein
Head (per Regex *und* per Alembics eigenem Parser), genau eine Wurzel,
lückenlose Kette, grober Drift-Check gegen die Modellfelder. Per Gegenprobe
verifiziert: mit künstlich wiederhergestellter ID-Kollision schlagen vier der
fünf Tests fehl.

**Was weiterhin fehlt:** ein echter `alembic upgrade head` gegen
PostgreSQL. In der Entwicklungsumgebung ist weder ein Docker-Daemon noch ein
lokales Postgres verfügbar, und die Kette lässt sich nicht auf SQLite
ausführen (ältere Migrationen nutzen ungeschütztes Postgres-SQL, z.B.
`ALTER TABLE ... ALTER COLUMN ... TYPE ... USING` in `a1b2c3d4e5f6`).

> ✅ **Erledigt (0.1.44):** Die beiden Migrationen aus 0.1.40/0.1.41
> (`c4d5e6f7a8b9`, `d5e6f7a8b9c1`) sind inzwischen **gegen PostgreSQL 16
> gelaufen** – beim Rebuild in der Docker-Umgebung, sauber durch:
>
> ```
> Running upgrade f1a2b3c4d5e6 -> c4d5e6f7a8b9, tagebucheintrag: generische Uebungs-Ergebnisfelder
> Running upgrade c4d5e6f7a8b9 -> d5e6f7a8b9c1, auditaktion/auditzieltyp: Wochenbericht-Zugriff und Datenexport
> ```
>
> Das befürchtete Problem mit `ALTER TYPE ... ADD VALUE` und explizitem
> `COMMIT` ist auf Postgres 16 nicht aufgetreten. Zusätzlich abgesichert:
> der Restore-Probelauf aus PR-001 spielt einen `pg_dump` zurück und lässt
> die App danach `alembic upgrade head` fahren – damit ist auch der Pfad
> „altes Backup, neuerer Code" einmal real durchlaufen.

> ✅ **Automatisierter Test ergänzt (0.1.45):**
> `tests/test_migrationen_postgres.py` legt eine Wegwerf-Datenbank an,
> fährt die Kette dagegen und räumt wieder auf. Vier Fälle: `upgrade head`,
> Schema-Abgleich gegen die SQLModel-Modelle (Drift), Rundlauf
> `head → base → head`, sowie jede Revision einzeln statt in einem Rutsch.
> Ohne `TEST_POSTGRES_URL` werden sie übersprungen, damit der normale
> Testlauf keine Datenbank voraussetzt.
>
> **Der Test hat sofort zwei echte Fehler gefunden:**
>
> 1. **Der Rückweg war versperrt.** `downgrade base` ließ elf
>    Postgres-ENUM-Typen stehen (`roleenum`, `auditaktion`, …), weil
>    Alembics Autogenerate zwar Tabellen löscht, aber keine Typen – daher
>    auch das `please adjust!` im generierten Code, das nie umgesetzt
>    wurde. Ein anschließendes `upgrade head` scheiterte an
>    `type "roleenum" already exists`. Nach einem misslungenen Deploy wäre
>    genau der Rückweg blockiert gewesen, den man dann braucht. Behoben in
>    `ff957f57f077` (nur `downgrade()`, `upgrade()` unverändert – für
>    bestehende Installationen folgenlos).
> 2. **Modell und Datenbank wichen auseinander.**
>    `BewerbungsNotiz.text` ist in der Datenbank `NOT NULL`, im Modell aber
>    nullable: bei `sa_column=Column(...)` übernimmt SQLModel die
>    Nullability nicht aus der Annotation, und `Column()` defaultet auf
>    nullable. Weil die Tests ihr Schema per `create_all` aus den Modellen
>    bauen, war die Spalte dort nullable – ein Test hätte `NULL` einfügen
>    und bestehen können, während dieselbe Operation gegen die echte
>    Datenbank scheitert. Behoben am Modell, keine Migration nötig.
>
> Genau dafür war der Punkt gedacht: beides wäre sonst erst im Ernstfall
> aufgefallen.

**Vorschlag:** Postgres-Container in der Testumgebung (oder CI), ein
Smoke-Test `upgrade head` → `downgrade base` → `upgrade head`, plus ein
Abgleich des erzeugten Schemas gegen `SQLModel.metadata`.

---

## PR-003 – Kein Virenscan bei Uploads {#pr-003}

**Schwere: Hoch · Aufwand: M · Status: behoben (0.1.44)**

> ✅ **Umgesetzt.** `app/core/virenscan.py`, aufgerufen aus
> `app/core/uploads.py` **vor** dem Verschlüsseln und Schreiben – eine
> erkannte Datei erreicht die Platte gar nicht erst (danach wäre sie
> verschlüsselt und für einen dateibasierten Scan unsichtbar).
>
> clamd wird direkt über sein INSTREAM-Protokoll angesprochen (asyncio-
> Socket, keine neue Abhängigkeit; die verfügbaren Python-Pakete sind
> synchron und würden den Event-Loop blockieren). ClamAV liegt als
> optionaler Compose-Dienst hinter dem Profil `virenscan`, weil das Image
> ~1 GB Signaturen lädt und für die reine Funktionsbewertung nicht nötig
> ist.
>
> **Schaltlogik bewusst so:** ohne `CLAMAV_HOST` ist die Prüfung aus
> (Prototyp-Standard). Sobald der Host gesetzt ist, ist sie *verbindlich* –
> ein nicht erreichbarer Scanner oder ein Timeout führt zur **Ablehnung**
> des Uploads, nicht zum stillen Überspringen. Ein Scanner, der im
> Fehlerfall durchwinkt, ist gefährlicher als gar keiner, weil er Schutz
> vortäuscht.
>
> **Gegen einen echten clamd verifiziert**, nicht nur gegen den Test-Fake:
> saubere Datei durch, EICAR-Testsignatur abgelehnt, EICAR eingebettet in
> 10 KB Beiwerk ebenfalls abgelehnt (belegt, dass wirklich der Inhalt
> gescannt wird und nicht nur ein Hash), 2 MB über mehrere INSTREAM-Chunks
> korrekt übertragen, leere Datei ohne Fehler. Zusätzlich 9 Unit-Tests
> (`tests/test_virenscan.py`) inkl. Gegenprobe: ohne den Scan-Aufruf in
> `uploads.py` schlägt genau der Test fehl, der prüft, dass eine infizierte
> Datei nicht auf der Platte landet.
>
> Die Fehlermeldung ist bewusst neutral formuliert – sie erscheint Menschen
> in beruflicher Reha, die die Datei meist nur weiterreichen und nichts
> falsch gemacht haben (CLAUDE.md §24). Im Log landet nur die Signatur,
> nie der Dateiname: der ist häufig personenbezogen
> („Lebenslauf Maria Muster.pdf", CLAUDE.md §13).
>
> **Offen:** Die Einrichtung muss den Dienst aktivieren und für aktuelle
> Signaturen sorgen (freshclam läuft im Container mit). Auf arm64 gibt es
> kein offizielles ClamAV-Image – für die üblichen x86-Server irrelevant,
> auf Apple-Silicon-Entwicklungsmaschinen bleibt die Prüfung praktisch aus.

Ursprünglicher Befund:

`app/core/uploads.py` prüft Endung, Größe (10 MB) und Magic Bytes. Die
Magic-Byte-Prüfung stellt sicher, *dass* die Datei ein PDF/PNG/JPEG/Word-
Dokument ist – nicht, dass ihr Inhalt harmlos ist.

Relevant ist das, weil Dateien zwischen Nutzenden wandern:
Teilnehmer:innen laden Bewerbungsunterlagen hoch, Berufstrainer:innen laden
sie herunter und öffnen sie lokal. Ein präpariertes PDF ist damit ein
Verbreitungsweg innerhalb der Einrichtung.

---

## PR-004 – Keine Schlüsselrotation {#pr-004}

**Schwere: Mittel · Aufwand: L · Status: behoben (0.1.45)**

> ✅ **Umgesetzt.** `FIELD_ENCRYPTION_KEY` nimmt jetzt mehrere
> kommagetrennte Schlüssel (neuester zuerst, `MultiFernet`): verschlüsselt
> wird mit dem ersten, entschlüsselt mit jedem. Ein einzelner Schlüssel –
> der Normalfall und alle bestehenden Installationen – verhält sich
> unverändert. Dazu `scripts/reencrypt.py` für die Bestandsdaten
> (Datenbank **und** Uploads), Ablauf in
> [`docs/BACKUP.md`](../../docs/BACKUP.md#schlüsselrotation-und-backups).
>
> Der Prüfmodus ist der eigentliche Schutz: Er meldet, ob noch etwas am
> alten Schlüssel hängt, und beendet sich mit Exit-Code 1, solange das so
> ist. Wer den alten Schlüssel vorher entfernt, verliert die Daten
> endgültig – auch aus dem Backup heraus, weil dort derselbe Ciphertext
> liegt. Genau dieser Schadensfall ist als Test festgehalten.
>
> **Gegen die echte Datenbank geprobt** (44.616 verschlüsselte Werte,
> 4 Upload-Dateien): Rotation auf einen neuen Schlüssel, Prüfmodus meldet
> 0 offene, Rückrotation auf den alten, anschließend liest die App wieder
> alles im Klartext – Tagebucheinträge, Bewerbungsnotizen und eine echte
> PDF-Datei. Dabei zwei Fehler gefunden und behoben:
>
> 1. Das Skript las über SQLAlchemy und bekam dadurch vom TypeDecorator
>    bereits *entschlüsselten* Klartext – der Rotationsversuch scheiterte
>    still an jedem einzelnen Wert, und der Prüfmodus hätte nie grünes
>    Licht gegeben. Jetzt rohes SQL.
> 2. 44.616 Einzel-UPDATEs brauchten über zehn Minuten und liefen in einen
>    Timeout. Gebündelt sind es zwei Sekunden. Eine Rotation, die scheinbar
>    hängt, wird abgebrochen – und ein halb rotierter Bestand ist genau der
>    Zustand, den niemand will.
>
> **Wichtig für den Betrieb:** Alte Schlüssel dürfen erst weg, wenn auch
> das letzte Backup aus ihrer Zeit ausgelaufen ist (bei 6 Monatsständen
> also ein halbes Jahr) – sonst ist das Archiv da, aber nicht lesbar.
> Steht als Tabelle in docs/BACKUP.md.

Ursprünglicher Befund:

`FIELD_ENCRYPTION_KEY` ist über die Lebensdauer der Installation
unveränderlich (`app/core/crypto.py` nennt das selbst als bewusste
Auslassung). Wird der Schlüssel kompromittiert – Backup entwendet,
`.env` versehentlich geteilt –, gibt es keinen Mechanismus außer manueller
Neuverschlüsselung aller Bestandsdaten.

**Vorschlag:** `MultiFernet` mit Schlüsselliste (neuester zum Schreiben,
alle zum Lesen) plus ein Re-Encrypt-Kommando, das Bestandsdaten schrittweise
auf den neuen Schlüssel zieht. Damit wird Rotation zu einem geplanten
Vorgang statt zu einem Notfall.

---

## PR-005 – Kontolöschung unvollständig (Art. 17 DSGVO) {#pr-005}

**Schwere: Mittel · Aufwand: L · Status: behoben (0.1.45)**

> ✅ **Umgesetzt.** `app/core/deletion.py:loesche_konto_vollstaendig`, in der
> Benutzerverwaltung erreichbar (Bestätigungswort „KONTO LÖSCHEN“).
> Migration `e6f7a8b9c1d2` macht die dafür nötigen Spalten nullbar.
>
> **Die Produktentscheidung** (vom Auftraggeber): Karten auf Team-Boards
> bleiben bestehen, damit die Berufstrainer:innen sie manuell löschen oder
> neu zuweisen können. Daraus folgt eine Dreiteilung, die den ganzen Kern
> ausmacht:
>
> | Art des Bezugs | Behandlung | Begründung |
> |---|---|---|
> | Eigene Inhalte (Tagebuch, Bewerbungen, Wochenberichte, persönliches Board) | gelöscht | gehören ausschließlich dieser Person |
> | Zugehörigkeiten (Kartenzuweisungen, Mitgliedschaften, PSM-/Trainer-Zuordnungen) | Zeilen entfernt | eine Zuweisung an jemanden, den es nicht mehr gibt, hat keine Bedeutung – und die Karte fällt dadurch als unzugewiesen auf, was genau das Signal für die Leitung ist |
> | Urheberschaft auf Team-Inhalten (Karte/Board angelegt, Karte bewegt) | auf NULL gesetzt, Inhalt bleibt | auf Team-Boards arbeiten andere weiter |
> | Audit-Log | bleibt vollständig | CLAUDE.md §9: pseudonymisierte Löschung, nicht Verschwinden – `akteur_id` hat dafür keinen Fremdschlüssel mehr |
>
> Nach der Löschung meldet die Oberfläche, wie viele Team-Karten jetzt ohne
> Zuständige dastehen und wie viele Handlungsfelder ohne Leitung sind – ein
> Löschverlangen wird deswegen nicht verweigert (das Betroffenenrecht wiegt
> schwerer), aber die Verwaltung erfährt davon.
>
> **Live geprobt:** Testkonto mit Karte auf dem Demo-Team-Board angelegt und
> über die Oberfläche gelöscht. Ergebnis: Konto weg, Karte steht weiter auf
> dem Board – sichtbar ohne Avatar, während alle Nachbarkarten Zuständige
> zeigen. `ersteller_id` ist NULL, die Zuweisung entfernt, das Board intakt.
> Dazu 12 Tests, die tabellenweise prüfen, dass nichts von der Person
> übrig bleibt und zugleich fremde Arbeit unangetastet ist.

Ursprünglicher Befund (siehe auch VB-004):

Löschbar sind aktuell nur die Inhaltsdaten (Wohlbefinden, Bewerbungen,
persönliches Kanban-Board – seit 0.1.42 mit Löschtests abgesichert). Der
Account selbst bleibt bestehen, weil Karten auf *Team*-Boards
`ersteller_id`, `KartenZuweisung.teilnehmer_id` und
`KartenBewegung.bewegt_von_id` nicht-nullbar referenzieren; ein Hard-Delete
liefe gegen die Fremdschlüssel oder risse für andere freigegebene Boards
mit.

Ein vollständiges Löschverlangen kann damit heute nicht erfüllt werden.

**Vorschlag:** Schema-Änderung auf nullbare Referenzen plus Anzeige als
„gelöschte:r Nutzer:in", danach echte Konto-Löschung. Braucht eine
Migration und eine bewusste Entscheidung, was mit gemeinsamen Team-Inhalten
passieren soll.

---

## PR-006 – Router ohne eigene Tests {#pr-006}

**Schwere: Mittel · Aufwand: M · Status: behoben (0.1.44/0.1.45)**

Die Zugriffs*schicht* ist seit 0.1.42 abgesichert (24 Berechtigungstests),
die Routen darüber teilweise noch nicht:

| Router | Routen | eigene Testdatei |
|---|---|---|
| `admin.py` | 19 | ✅ `tests/test_admin.py` (21 Tests) |
| `bewerbungen.py` | 18 | ✅ `tests/test_bewerbungen.py` (15 Tests) |
| `wochenberichte.py` | 7 | ✅ `tests/test_wochenberichte.py` (12 Tests) |
| `oidc.py` | 2 | nein |

`admin.py` war dabei der heikelste: dort werden Rollen zugewiesen,
Accounts freigeschaltet und Passwörter zurückgesetzt. Ein Fehler dort
vergibt Zugriff auf Gesundheits- und Bewerbungsdaten, ohne dass je eine
Freigabe erteilt wurde – die getestete Zugriffsschicht hilft dann nicht
mehr, weil sie die Rolle als gegeben hinnimmt.

Abgedeckt sind vor allem die Fälle, die *nicht* passieren dürfen:
Teilnehmer:innen und Trainer:innen kommen auf keine Verwaltungsseite und
können weder Accounts anlegen noch sich selbst befördern noch fremde
Passwörter zurücksetzen; niemand ändert die eigene Rolle oder sperrt sich
selbst aus; ein gesperrtes Konto kommt weder durch den Login noch mit
bestehender Sitzung ans Dashboard (der Fehler aus 0.1.42); E-Mails werden
vor der Dublettenprüfung normalisiert, sonst entstünden zwei Accounts mit
derselben Adresse in unterschiedlicher Schreibweise.

**Gegenprobe durchgeführt:** mit entfernter Rollenprüfung in
`benutzer_erstellen` bzw. entferntem Selbstsperr-Schutz schlagen genau die
zuständigen Tests fehl – die Tests laufen also nicht bloß mit.

Für `bewerbungen.py` liegt der Schwerpunkt auf IDOR: jede Route, die eine
ID aus der URL nimmt, wird mit einer fremden Teilnehmer:in durchprobiert.
Zusätzlich festgeschrieben ist die dokumentierte Grenze, dass
Berufstrainer:innen auch **mit** Freigabe keine Dateien herunterladen
können - eine stille Ausweitung wäre eine Datenschutz-Änderung und soll
auffallen.

Bei `wochenberichte.py` geht es um die statusabhängige Sichtbarkeit: Ein
Entwurf gehört ausschließlich der schreibenden Person, erst das Abgeben
öffnet ihn für die Leitung des eigenen Handlungsfelds, das Zurückziehen
schließt ihn wieder. Das ist eine Zusage an die Teilnehmer:innen
("solange du daran arbeitest, liest niemand mit"), deren Bruch von außen
niemandem auffallen würde.

**Gegenproben:** ohne `require_owner` im Datei-Download fallen beide
Datei-Tests; ohne die Statuskopplung in der Wochenbericht-Übersicht fallen
genau die zwei Sichtbarkeits-Tests.

Offen bleibt `oidc.py` (2 Routen).

---

## PR-007 – Kein Monitoring, keine Redundanz {#pr-007}

**Schwere: Niedrig · Aufwand: M**

Die App läuft als **ein** Uvicorn-Prozess ohne Worker-Vervielfachung. Für
ein Single-Tenant-Deployment ist das vertretbar – das In-Memory-Rate-Limiting
(`app/core/rate_limit.py`) setzt sogar genau einen Prozess voraus –, aber:

- Ein Neustart oder Absturz bedeutet Ausfall ohne Übernahme.
- Es gibt kein Monitoring, keine Alarmierung, keine Log-Aggregation. Ein
  Ausfall fällt auf, wenn jemand anruft.
- Der Docker-Healthcheck startet den Container neu, meldet aber niemandem
  etwas.

**Hinweis:** Sollte später auf mehrere Worker umgestellt werden, muss das
Rate-Limiting vorher aus dem Prozessspeicher heraus (Redis o.ä.) – sonst
vervielfacht sich die erlaubte Versuchszahl still.

---

## PR-008 – DSGVO-Dokumentation und rechtliche Prüfung {#pr-008}

**Blocker · organisatorisch, kein Code**

Bei Gesundheitsdaten (Art. 9) im Beschäftigten-/Reha-Kontext reicht eine
technisch saubere Anwendung nicht aus. Vor dem Einsatz mit echten Daten
braucht die Einrichtung:

- **Verzeichnis von Verarbeitungstätigkeiten** (Art. 30)
- **Dokumentation der technischen und organisatorischen Maßnahmen** (Art. 32)
  – das Datenschutzkonzept liefert dafür die Grundlage, ist aber kein
  TOM-Dokument
- **Auftragsverarbeitungsvertrag** mit dem Hoster/Betreiber (Art. 28), falls
  nicht selbst gehostet
- **Datenschutz-Folgenabschätzung** (Art. 35) – bei besonderen Kategorien
  personenbezogener Daten und Beschäftigtenkontext realistisch erforderlich
- **Konkrete Aufbewahrungsfristen** für Audit-Logs (im Konzept selbst als
  offen markiert)
- **Definierter Prozess für Betroffenenrechte** (Auskunft, Berichtigung,
  Löschung) – die technische Seite existiert teilweise (Export ja, Löschung
  siehe PR-005), der organisatorische Ablauf nicht

Das Datenschutzkonzept nennt „Rechtliche Prüfung durch die jeweilige
Einrichtung vor Produktivbetrieb" selbst als offenen Punkt (Abschnitt 8).

---

## PR-009 – 2FA für Betreuer-/Admin-Rollen {#pr-009}

**Status: entschieden – wird nicht umgesetzt (0.1.45)**

> ⚪ **Entscheidung des Auftraggebers:** 2FA ist in der Praxis nicht
> nutzbar, weil Teilnehmer:innen den zweiten Faktor auf **privaten Geräten**
> erzeugen müssten. Ein verpflichtendes Sicherheitsmerkmal, das ein privates
> Smartphone voraussetzt, schließt genau die Menschen aus, die keines haben
> oder es nicht einsetzen wollen – im Reha-Kontext keine tragfähige
> Grundlage. In ScandyPro wird deshalb keine 2FA gebaut.
>
> **Zur Genauigkeit des Protokolls:** Die ursprüngliche Frage betraf nur die
> *Betreuer- und Admin-Rollen*, nicht die Teilnehmer:innen. Für Beschäftigte
> mit Dienstgerät greift der Einwand mit dem Privatgerät nicht unbedingt.
> Diese Unterscheidung ist hier festgehalten, damit sie bei einer späteren
> Neubewertung nicht verlorengeht – die Entscheidung „keine 2FA in
> ScandyPro" bleibt davon unberührt, weil eine Eigenlösung ohnehin nicht der
> richtige Ort dafür wäre.
>
> **Wenn eine Einrichtung 2FA für ihre Beschäftigten doch will**, gehört sie
> in den Identity-Provider: Läuft SSO über Authentik (siehe
> [`SSO_AUTHENTIK.md`](../../SSO_AUTHENTIK.md)), lässt sich dort ein zweiter
> Faktor rollenabhängig erzwingen, ohne dass ScandyPro etwas davon wissen
> muss – und ohne Teilnehmer:innen zu betreffen, die sich weiterhin lokal
> mit E-Mail und Passwort anmelden.

Ursprünglicher Befund:

Im Datenschutzkonzept (Abschnitt 8) als offene Frage vermerkt: Sollen
Berufstrainer:innen, psychosoziale Mitarbeit und Einrichtungs-Admins einen
zweiten Faktor benötigen? Diese Rollen sehen freigegebene Gesundheits- und
Bewerbungsdaten; ein übernommener Account wiegt dort deutlich schwerer als
bei Teilnehmer:innen.

---

## Empfohlene Reihenfolge

1. ~~**PR-001 (Backup)**~~ – ✅ erledigt in 0.1.44, Restore geprobt.
2. ~~**PR-002 (Migrationen testen)**~~ – ✅ erledigt in 0.1.45, inkl.
   automatisiertem Test gegen PostgreSQL. Zwei echte Fehler dabei gefunden
   und behoben.
3. **PR-008 (DSGVO-Papierlage)** – läuft organisatorisch parallel und hat
   Vorlauf; ohne das darf ohnehin nicht produktiv gestartet werden.
4. ~~**PR-003 (Virenscan)**~~ – ✅ erledigt in 0.1.44. Die Einrichtung muss
   den Dienst nur noch aktivieren (`--profile virenscan` + `CLAMAV_HOST`).
5. ~~**PR-006 (Router-Tests)**~~ – ✅ erledigt in 0.1.44/0.1.45: `admin.py`
   (21), `bewerbungen.py` (15), `wochenberichte.py` (12), jeweils mit
   Gegenprobe. Nur `oidc.py` bleibt offen.
6. ~~**PR-004 (Schlüsselrotation)**~~ – ✅ erledigt in 0.1.45, gegen die
   echte Datenbank geprobt.
7. ~~**PR-005 (Konto-Löschung)**~~ – ✅ erledigt in 0.1.45, live geprobt.
8. ~~**PR-009 (2FA)**~~ – ⚪ entschieden: nicht umsetzen (Begründung unten).
9. **PR-007 (Monitoring)** – die Backup-Ausfall-Meldung ist umgesetzt,
   Monitoring der Anwendung selbst bleibt offen. Kein Startblocker.

Acht der neun Punkte sind damit abgeschlossen oder bewusst entschieden,
darunter der kritische (PR-001). Der verbleibende echte Startblocker ist **PR-008**
(organisatorisch, kein Code).
