# ScandyPro – Was einem Produktiveinsatz im Weg steht

**Stand:** 0.1.42 (2026-08-12)
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
| [PR-001](#pr-001) | Kein Backup – Totalverlust-Risiko | **Kritisch** | M | offen |
| [PR-002](#pr-002) | Migrationen laufen in keinem Test | **Hoch** | M | 🟡 teilweise |
| [PR-003](#pr-003) | Kein Virenscan bei Uploads | **Hoch** | M | offen |
| [PR-004](#pr-004) | Keine Schlüsselrotation | Mittel | L | offen |
| [PR-005](#pr-005) | Kontolöschung unvollständig (Art. 17) | Mittel | L | offen |
| [PR-006](#pr-006) | `admin.py` und `bewerbungen.py` ohne Tests | Mittel | M | offen |
| [PR-007](#pr-007) | Kein Monitoring, keine Redundanz | Niedrig | M | offen |
| [PR-008](#pr-008) | DSGVO-Dokumentation und rechtliche Prüfung | **Blocker** | – | organisatorisch |
| [PR-009](#pr-009) | 2FA für Betreuer-/Admin-Rollen ungeklärt | Offen | M | Entscheidung nötig |

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

**Schwere: Kritisch · Aufwand: M · Das hier zuerst.**

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

> ⚠️ **Konkret offen:** Die beiden Migrationen aus 0.1.40/0.1.41
> (`c4d5e6f7a8b9`, `d5e6f7a8b9c1`) sind **noch nie gegen PostgreSQL
> gelaufen**. `d5e6f7a8b9c1` nutzt `ALTER TYPE ... ADD VALUE` mit explizitem
> `COMMIT` – das ist genau die Sorte Statement, die auf SQLite nicht und auf
> älteren Postgres-Versionen nur außerhalb einer Transaktion funktioniert.
> **Vor dem nächsten Deploy gegen eine Kopie der Produktions-DB testen.**

**Vorschlag:** Postgres-Container in der Testumgebung (oder CI), ein
Smoke-Test `upgrade head` → `downgrade base` → `upgrade head`, plus ein
Abgleich des erzeugten Schemas gegen `SQLModel.metadata`.

---

## PR-003 – Kein Virenscan bei Uploads {#pr-003}

**Schwere: Hoch · Aufwand: M**

`app/core/uploads.py` prüft Endung, Größe (10 MB) und Magic Bytes. Die
Magic-Byte-Prüfung stellt sicher, *dass* die Datei ein PDF/PNG/JPEG/Word-
Dokument ist – nicht, dass ihr Inhalt harmlos ist.

Relevant ist das, weil Dateien zwischen Nutzenden wandern:
Teilnehmer:innen laden Bewerbungsunterlagen hoch, Berufstrainer:innen laden
sie herunter und öffnen sie lokal. Ein präpariertes PDF ist damit ein
Verbreitungsweg innerhalb der Einrichtung.

**Vorschlag:** ClamAV als eigener Container, Scan beim Upload vor dem
Verschlüsseln; bei Fund ablehnen mit neutraler Fehlermeldung. Alternativ –
falls kein Scanner gewünscht ist – die Entscheidung bewusst dokumentieren
und die Einrichtung darüber informieren.

---

## PR-004 – Keine Schlüsselrotation {#pr-004}

**Schwere: Mittel · Aufwand: L**

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

**Schwere: Mittel · Aufwand: L · siehe auch VB-004**

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

**Schwere: Mittel · Aufwand: M**

Die Zugriffs*schicht* ist seit 0.1.42 abgesichert (24 Berechtigungstests),
die Routen darüber teilweise noch nicht:

| Router | Routen | eigene Testdatei |
|---|---|---|
| `admin.py` | 19 | nein |
| `bewerbungen.py` | 18 | nein (nur indirekt über Berechtigungstests) |
| `wochenberichte.py` | 7 | nein (nur indirekt) |
| `oidc.py` | 2 | nein |

`admin.py` ist dabei der heikelste: dort werden Rollen zugewiesen,
Accounts freigeschaltet und Passwörter zurückgesetzt.

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

**Entscheidung nötig**

Im Datenschutzkonzept (Abschnitt 8) als offene Frage vermerkt: Sollen
Berufstrainer:innen, psychosoziale Mitarbeit und Einrichtungs-Admins eine
zweite Faktor benötigen? Diese Rollen sehen freigegebene Gesundheits- und
Bewerbungsdaten; ein übernommener Account wiegt dort deutlich schwerer als
bei Teilnehmer:innen.

Falls SSO über Authentik läuft (siehe [`SSO_AUTHENTIK.md`](../../SSO_AUTHENTIK.md)),
lässt sich 2FA dort erzwingen, ohne in ScandyPro selbst etwas zu bauen –
das ist vermutlich der pragmatischste Weg und sollte vor einer Eigenlösung
geprüft werden.

---

## Empfohlene Reihenfolge

1. **PR-001 (Backup)** – überschaubarer Aufwand, deckt das einzige Risiko
   ab, bei dem hinterher nichts mehr zu retten ist.
2. **PR-002 (Migration gegen Postgres testen)** – speziell die zwei noch
   nie gelaufenen Migrationen, bevor das nächste Update deployt wird.
3. **PR-008 (DSGVO-Papierlage)** – läuft organisatorisch parallel und hat
   Vorlauf; ohne das darf ohnehin nicht produktiv gestartet werden.
4. **PR-003 (Virenscan)** – vor dem ersten echten Bewerbungs-Upload.
5. **PR-006 (Tests für admin.py)** – bevor mehrere Personen Accounts
   verwalten.
6. **PR-004, PR-005, PR-007, PR-009** – geplant nachziehen, kein
   Startblocker, aber keiner davon sollte dauerhaft offen bleiben.
