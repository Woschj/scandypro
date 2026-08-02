# ScandyPro – Produkt- und technisches Konzept

> Konkretisierung von [../CLAUDE.md](../CLAUDE.md) und
> [DATENSCHUTZ_UND_BERECHTIGUNGEN.md](DATENSCHUTZ_UND_BERECHTIGUNGEN.md).
> Dieses Dokument beschreibt Features, Datenmodell, Architektur und Phasen.
> Es ist der Ausgangspunkt für die Implementierung, kein starres Lastenheft –
> wird bei wesentlichen Entscheidungen nachgezogen.

---

## 1. Zielgruppe & Nutzungskontext

- **Träger**: Einrichtungen der beruflichen Rehabilitation (z. B.
  Berufsförderungswerke, Berufsbildungswerke, RPK, Integrationsfachdienste).
- **Betrieb**: eine ScandyPro-Instanz pro Einrichtung, self-hosted, analog
  Scandy-Lite (Docker Compose, PostgreSQL, Caddy).
- **Primäre Endnutzer**: Reha-Teilnehmer:innen – oft mit eingeschränkter
  Belastbarkeit, teils wenig Erfahrung mit Verwaltungssoftware. UI muss
  einfach, ruhig, wenig überfordernd sein (siehe Abschnitt 7).
- **Sekundäre Nutzer**: Berufstrainer:innen, psychosoziale Mitarbeitende,
  Einrichtungs-Admins (siehe Rollenmodell in
  [DATENSCHUTZ_UND_BERECHTIGUNGEN.md](DATENSCHUTZ_UND_BERECHTIGUNGEN.md)).

---

## 2. Modul-Übersicht & Kernfeatures

### 2.1 Kanban / Ticket-System (Maßnahmen & interne Projekte)

Zweck: Aufgaben und Maßnahmen der Reha-Maßnahme organisieren – vergleichbar
mit einem einfachen Trello/Jira, aber schlank.

Die Einrichtung gliedert sich in feste **Abteilungen** (z. B. Medien &
Digital, Technik, Service, Kaufmännisches, Name über die
Admin-Verwaltung änderbar) und darunter in **Handlungsfelder** – die
eigentlichen operativen Arbeitsgruppen (z. B. "Video-Projekte" innerhalb
Medien & Digital), angelehnt an das gleichnamige Konzept in Scandy2. Ein
Handlungsfeld hat eine oder mehrere **Leitungen** (Berufstrainer:innen).
Boards sind keine Einzelpersonen-Boards mehr, sondern Projekte eines
Handlungsfelds, an denen mehrere Teilnehmer:innen gemeinsam arbeiten:

- **Board = Projekt eines Handlungsfelds.** Angelegt nur von dessen
  Leitung(en), nicht von Teilnehmer:innen selbst und nicht von
  Berufstrainer:innen ohne Leitungsfunktion dort.
- **Teilnehmergruppen**: Die Leitung eines Handlungsfelds bildet Gruppen
  aus Teilnehmer:innen der zugehörigen Abteilung (z. B. "Projektteam
  Video"). Ein Board wird für eine oder mehrere Teilnehmergruppen
  freigegeben statt für einzelne Personen.
- Spalten frei konfigurierbar (Standard-Vorlage: `Offen → In Arbeit →
  Wartet → Erledigt`), **außer der letzten Spalte**: Jedes Board hat genau
  eine strukturell fixierte "Erledigt"-Spalte (`Spalte.ist_system_erledigt`)
  – immer die letzte, kann nicht gelöscht werden, neue Spalten werden immer
  davor eingefügt. Karten darin gelten als abgeschlossen und sind
  schreibgeschützt (Inhalte/Zuweisungen/Unteraufgaben bleiben sichtbar wie
  ein "Trophäenregal", nur das Zurückziehen in eine andere Spalte hebt die
  Sperre wieder auf).
- Karten mit: Titel, Beschreibung, Fälligkeitsdatum, Checkliste,
  Kommentare, Anhänge
- Fortschrittsanzeige pro Board (erledigt/gesamt)
- Erinnerungen bei nahender Fälligkeit
- **Positives Feedback statt Gamification** (siehe CLAUDE.md Abschnitt 25):
  eine Karte in die Erledigt-Spalte zu ziehen löst einen ruhigen visuellen
  Impuls aus (warmer Glow + kurzer Stempel-Haken, kein Konfetti/Punkte/
  Bestenliste). Für Teilnehmer:innen ergänzt ein privates, nie negativ
  formuliertes Wochen-Fortschritts-Signal auf dem Dashboard ("In den
  letzten 7 Tagen X Schritte geschafft", gezählt aus abgeschlossenen
  Karten/Unteraufgaben, `app/core/fortschritt.py`) – bei 0 eine einladende
  neutrale Zeile statt einer Zahl, nur für die Person selbst sichtbar.

Datenklassifikation: **normal** (nicht Art.-9-sensibel), Soft-Delete
zulässig. Zugriff: nur die Leitung(en) eines Handlungsfelds verwalten
dessen Boards; Teilnehmer:innen nur über Mitgliedschaft in einer
freigegebenen Teilnehmergruppe (siehe
[DATENSCHUTZ_UND_BERECHTIGUNGEN.md](DATENSCHUTZ_UND_BERECHTIGUNGEN.md)).

### 2.1a Wochenberichte

Teilnehmer:innen dokumentieren wöchentlich ihre Tätigkeiten mit einem
Eintrag pro Werktag (Mo-Fr: Beginn, Ende, Tätigkeiten; angelehnt an das
Wochenprotokoll-Konzept aus Scandy2) und geben den Bericht bei ihren
Berufstrainer:innen ab. Solange ein Bericht Entwurf ist, sieht ihn nur die
oder der Teilnehmer:in selbst; nach dem Abgeben wird er für die Leitung(en)
jedes Handlungsfelds sichtbar, dessen Teilnehmergruppe die Person angehört
– abgeleitet aus der bestehenden Handlungsfeld-/Gruppenstruktur, ohne
weitere Zuordnungstabelle. Abgegebene Berichte sind nicht löschbar
(Nachweischarakter), Entwürfe schon.

**Word-Export**: Die Einrichtung nutzt für Wochenberichte ein bestehendes,
unterschriftsfähiges Word-Formular ("Wochenprotokoll/Tätigkeitsnachweis"
mit Unterschriftsfeldern für Teilnehmer:in und Berufstrainer:in). ScandyPro
befüllt dieses Formular automatisch aus den erfassten Daten
(`app/assets/wochenbericht_vorlage.docx`, gerendert mit `docxtpl` in
`app/core/wochenbericht_export.py`) statt ein eigenes Layout zu erfinden –
Layout und Feldnamen sind extern durch die Einrichtung vorgegeben. Download
steht Teilnehmer:in (jederzeit) und der Handlungsfeld-Leitung (nur bei
Status "abgegeben") zur Verfügung.

### 2.1b PSM-Zuordnung

Psychosoziale Mitarbeit unterstützt Teilnehmer:innen mental. Die
Zuordnung, wer wen betreut, verwaltet die Einrichtungs-Verwaltung
organisatorisch (rein informativ, "das ist deine PSM-Kontaktperson").
Sie gewährt **keinen** automatischen Zugriff auf Wohlbefinden-Daten – der
bleibt ausschließlich über die Freigabe-Funktion der/des Teilnehmer:in
selbst möglich (siehe [DATENSCHUTZ_UND_BERECHTIGUNGEN.md](DATENSCHUTZ_UND_BERECHTIGUNGEN.md)).

### 2.2 Wohlbefinden-Tracking

> Detailkonzept mit Nutzenhypothese: [WOHLBEFINDEN_KONZEPT.md](WOHLBEFINDEN_KONZEPT.md)

Zweck: niedrigschwellige Selbstbeobachtung, kein klinisches
Diagnoseinstrument, kein Ersatz für therapeutische Betreuung.

- Täglicher/wöchentlicher Kurz-Check-in: 2–4 einfache Skalen (z. B.
  Stimmung, Energie, Belastung, Schlaf) 1–5, ca. 30 Sekunden ausfüllbar
- Optionales Freitextfeld ("Was hat heute geholfen/belastet?")
- Optionale Tags/Auslöser (frei definierbar, z. B. "Bewerbungsgespräch",
  "Konflikt", "guter Tag") – Teilnehmer pflegt eigene Tag-Liste
- Verlaufsansicht: einfache Trendlinie über Zeit, nur für Teilnehmer
  selbst sichtbar
- Kein Score/Ampel-System, das ungefragt an Dritte kommuniziert wird
  (siehe Abschnitt "explizit vermieden" im Datenschutzkonzept)
- Freigabe-Funktion: Teilnehmer kann Verlauf oder einzelne Einträge für
  psychosoziale Mitarbeit zeitlich befristet freigeben (z. B. vor einem
  Gespräch: "letzte 2 Wochen zeigen")

Datenklassifikation: **hochsensibel** (Art. 9 DSGVO), verschlüsselt,
Hard-Delete, standardmäßig privat, kein automatischer Alarm.

### 2.3 Bewerbungs-Tracking

Zweck: Bewerbungsprozess strukturieren und mit Berufstrainer bei Bedarf
gemeinsam nachverfolgen.

- Bewerbungs-Einträge: Firma, Position, Kanal (online/Post/Initiativ),
  Datum, Status (Entwurf → Versendet → Rückmeldung offen → Eingeladen →
  Abgesagt/Zugesagt), nächste Frist/Termin
- **Dokumenten-Upload** (`app/core/uploads.py`), zwei Ebenen:
  - **Lebenslauf/Zeugnisse**: gehören der/dem Teilnehmer:in direkt (einmal
    hochladen, für alle Bewerbungen wiederverwendbar)
  - **Anschreiben**: gehört zu genau einer Bewerbung
  - Sicherheitsprinzip: zufälliger UUID-Dateiname auf der Platte, Original-
    Dateiname nur als Anzeige-Metadatum in der DB (kein Path-Traversal über
    Client-Dateinamen); Endungs-Whitelist (PDF/Word/Bild) + 10-MB-Limit;
    Download nur über authentifizierte, Owner-geprüfte Route, kein
    öffentlicher Static-Mount
  - **Gesamt-PDF-Export** (`app/core/pdf_merge.py`): führt Anschreiben +
    Lebenslauf + Zeugnisse einer Bewerbung zu einem PDF zusammen (PDF- und
    Bilddateien werden eingebettet; Word-Dateien werden mangels
    Konvertierung ohne externe Abhängigkeit wie LibreOffice übersprungen
    und müssen separat angehängt werden)
- Notizen pro Bewerbung (z. B. Gesprächsvorbereitung, Feedback)
- Erinnerungen für Nachfass-Termine
- Einfache Übersicht/Statistik für Teilnehmer selbst (Anzahl Bewerbungen,
  Rücklaufquote) – **nicht** als Leistungskennzahl an Dritte exponiert
- Freigabe-Funktion analog Wohlbefinden: granular pro Bewerbung oder
  gesamt, widerrufbar, an Berufstrainer

Datenklassifikation: **sensibel** (potenziell diskriminierungsrelevant,
kein Art.-9-Kern, aber vergleichbar strikt zu behandeln), verschlüsselt,
Hard-Delete, standardmäßig privat.

### 2.4 Freigabe- & Rollenverwaltung

- Zentrale "Meine Freigaben"-Seite für Teilnehmer: Liste aller aktiven
  Freigaben (wer, was, seit wann, bis wann), mit Sofort-Widerruf
- Einrichtungs-Admin verwaltet Accounts/Rollen, Zuordnung
  Teilnehmer↔Berufstrainer/psychosoziale Mitarbeit (organisatorische
  Zuordnung, kein automatischer Inhaltszugriff)
- Audit-Log-Ansicht für Teilnehmer: "Wer hat wann auf meine Daten
  zugegriffen"

---

## 3. Datenmodell (konzeptionell)

Vereinfachte Entitäten, keine finalen Spaltennamen. `🔒` = verschlüsselt zu
speichern, `Hard` = Hard-Delete-Pflicht, `Soft` = Soft-Delete zulässig.

### User & Struktur

- **User**: id, name, email, password_hash, rollen[], abteilung_id
  (bei Teilnehmer:innen), aktiv, erstellt_am
- **Rolle**: `teilnehmer` | `berufstrainer` | `psychosoziale_mitarbeit` |
  `einrichtungs_admin`
- **Abteilung**: id, name (umbenennbar durch Einrichtungs-Admin)
- **Handlungsfeld**: id, name, abteilung_id – operative Arbeitsgruppe
  innerhalb einer Abteilung, von der Einrichtungs-Verwaltung angelegt
- **HandlungsfeldLeitung** (Handlungsfeld↔Berufstrainer, m:n):
  handlungsfeld_id, berufstrainer_id
- **Teilnehmergruppe**: id, name, handlungsfeld_id, erstellt_von (Leitung)
- **TeilnehmergruppeMitglied** (Gruppe↔Teilnehmer): gruppe_id, teilnehmer_id
- **PsmZuordnung** (PSM↔Teilnehmer, organisatorisch, kein Datenzugriff):
  psm_id, teilnehmer_id, erstellt_am

### Kanban (Soft)

- **Board**: id, titel, handlungsfeld_id, ersteller_id (Handlungsfeld-Leitung), erstellt_am
- **BoardFreigabe** (Board↔Teilnehmergruppe): board_id, gruppe_id,
  freigegeben_am – ersetzt eine 1:1-Zuordnung, damit ganze Gruppen
  gemeinsam an einem Board arbeiten
- **Spalte**: id, board_id, name, reihenfolge
- **Karte**: id, spalte_id, titel, beschreibung, faelligkeit,
  erstellt_von, erstellt_am
- **Kommentar**: id, karte_id, autor_id, text, erstellt_am
- **Anhang**: id, karte_id, dateiname, storage_pfad

### Wochenberichte (Soft für Entwürfe, abgegebene Berichte unveränderlich)

- **Wochenbericht**: id, teilnehmer_id, kw_jahr, kw_nummer, taetigkeiten,
  besonderheiten, status (`entwurf` | `abgegeben`), abgegeben_am,
  erstellt_am. Sichtbarkeit für Berufstrainer:innen ergibt sich aus
  Handlungsfeld-Leitung + Teilnehmergruppen-Mitgliedschaft.

### Wohlbefinden / 5-Minuten-Tagebuch (Hard, 🔒)

- **TagebuchEintrag**: id, teilnehmer_id, datum (eindeutig je Person+Tag),
  🔒 dankbarkeit_1/2/3, morgen_impuls_frage, 🔒 morgen_impuls_antwort,
  morgen_ausgefuellt_am, 🔒 highlight_1/2/3, abend_impuls_frage,
  🔒 abend_impuls_antwort, abend_ausgefuellt_am, erstellt_am. Je Tageszeit
  ein fester Kernimpuls + ein deterministisch rotierender Zusatzimpuls
  (siehe app/core/tagebuch_prompts.py, docs/WOHLBEFINDEN_KONZEPT.md).
- **WohlbefindenFreigabe**: id, teilnehmer_id, empfaenger_id,
  umfang (alle | zeitraum | einzelne_ids), gueltig_von, gueltig_bis,
  widerrufen_am (nullable)

### Bewerbungen (Hard, 🔒)

- **Bewerbung**: id, teilnehmer_id, firma, position, kanal, status,
  beworben_am, naechster_termin, 🔒 notizen
- **BewerbungsDokument**: id, bewerbung_id, typ (anschreiben|cv|sonstiges),
  dateiname, 🔒 storage_pfad_verschluesselt, version, hochgeladen_am
- **BewerbungsFreigabe**: id, teilnehmer_id, empfaenger_id,
  umfang (alle | einzelne_ids), gueltig_von, gueltig_bis, widerrufen_am

### Übergreifend

- **AuditLogEintrag**: id, zeitpunkt, akteur_id, aktion, zieltyp
  (wohlbefinden|bewerbung), ziel_id, grundlage (freigabe_id|break_glass),
  begruendung (bei break_glass Pflichtfeld) – **keine Inhalte**, nur
  Metadaten
- **LoeschAuftrag**: id, teilnehmer_id, angefordert_am, umfang
  (konto_komplett|nur_wohlbefinden|nur_bewerbungen), status,
  abgeschlossen_am – Nachweis, dass Löschung durchgeführt wurde, selbst ohne
  Personenbezug zum gelöschten Inhalt

---

## 4. Architektur

Analog Scandy-Lite, eigene Domäne:

```
┌─────────────────────────────────────────────┐
│                Caddy (TLS, Reverse Proxy)     │
└───────────────────────┬───────────────────────┘
                         │
┌───────────────────────▼───────────────────────┐
│  FastAPI App                                   │
│  ├─ app/routers/kanban                         │
│  ├─ app/routers/wohlbefinden                   │
│  ├─ app/routers/bewerbungen                    │
│  ├─ app/routers/freigaben                      │
│  ├─ app/routers/admin                          │
│  ├─ app/core/access.py      (zentrale AuthZ)   │
│  ├─ app/core/crypto.py      (Feldverschlüss.)  │
│  ├─ app/core/audit.py       (Audit-Logging)    │
│  ├─ app/core/deletion.py    (Löschroutinen)    │
│  └─ app/models/*            (SQLModel)         │
└───────────────────────┬───────────────────────┘
                         │
                ┌────────▼────────┐
                │  PostgreSQL 16   │
                └──────────────────┘
```

- `app/core/access.py`: einzige Stelle, die Rolle + Ownership + Freigabe
  prüft; alle Router rufen diese Schicht auf, keine eigene Logik.
- `app/core/crypto.py`: Fernet-basierte Verschlüsselung für `🔒`-Felder,
  Key aus ENV/Secret-Store.
- `app/core/audit.py`: schreibt AuditLogEintrag bei jedem Fremdzugriff auf
  sensible Daten.
- `app/core/deletion.py`: kapselt kaskadierende Hard-Delete-Logik pro
  Domäne, inkl. Datei-Storage.
- Datei-Uploads (Bewerbungsdokumente, Kanban-Anhänge) im Dateisystem/Volume,
  verschlüsselt bzw. mit restriktiven Zugriffsrechten, referenziert per
  Pfad in der DB.

---

## 5. Phasen / Roadmap

**Phase 0 – Fundament**
- Projekt-Grundgerüst (FastAPI, SQLModel, Alembic, Docker Compose, Caddy)
- User/Rollen/Auth (lokal, bcrypt), zentrale `access.py`
- Audit-Log-Grundgerüst, Verschlüsselungs-Baustein (`crypto.py`)

**Phase 1 – MVP**
- Kanban: Boards/Spalten/Karten (Basisfunktionen)
- Wohlbefinden: Check-in + eigene Verlaufsansicht (noch ohne Freigaben)
- Bewerbungen: CRUD + Statusverfolgung (noch ohne Freigaben)
- Löschfunktion: Konto komplett löschen (Hard-Delete, kaskadierend)

**Phase 2 – Zusammenarbeit**
- Freigabe-Mechanismus (Wohlbefinden + Bewerbungen), granular, widerrufbar
- "Meine Freigaben"-Übersicht inkl. Audit-Log-Einsicht für Teilnehmer
- Zuordnung Teilnehmer↔Berufstrainer/psychosoziale Mitarbeit durch Admin

**Phase 3 – Ausbau**
- Datenexport (Art. 20 DSGVO), Erinnerungen/Benachrichtigungen
- OIDC/SSO-Anbindung (analog Scandy-Lite)
- 2FA für Betreuer-/Admin-Rollen
- Statistiken/Trends (nur eigene Daten des Teilnehmers)

**Bewusst zurückgestellt / nur nach expliziter Diskussion**
- Automatische Eskalation bei kritischen Wohlbefinden-Werten
- Aggregierte Auswertungen über mehrere Teilnehmer (auch anonymisiert nur
  mit klar geprüftem Zweck)

---

## 6. Offene Design-Entscheidungen

- Bezeichnung der Rollen im UI (kann von internen Rollen-Slugs abweichen,
  z. B. "Coach" statt "Berufstrainer" je nach Einrichtung – ggf.
  konfigurierbar)
- Granularität der Freigabe: reicht Zeitraum-basiert, oder wird
  Einzel-Eintrags-Freigabe von Anfang an gebraucht?
- Umgang mit Krisensituationen (siehe Abschnitt 8 im Datenschutzkonzept) –
  separat und sorgfältig zu konzipieren, nicht Teil des MVP
- Mobile Nutzung: reines responsives Web reicht vermutlich, PWA als
  spätere Option

---

## 7. UX-Leitlinien (kurz)

- Ruhige, klare Sprache, kein Behörden-/Klinik-Jargon
- Wohlbefinden-Check-in muss in unter 30 Sekunden erledigbar sein
- Bei jedem sensiblen Eintrag sichtbar: "Nur für dich sichtbar" bzw. "Auch
  sichtbar für: …" – Transparenz statt Kleingedrucktes
- Keine roten Ampeln/Alarme bei niedrigen Wohlbefinden-Werten – neutrale,
  nicht wertende Darstellung
