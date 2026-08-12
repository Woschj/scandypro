# ScandyPro – Codebase-Audit (Stand 0.1.40, 2026-08-04)

**Methode:** Vollständiger Durchlauf über `app/`, `tests/`, `alembic/` mit
statischer Analyse (AST-Auswertung aller Router-Funktionen auf
Berechtigungsprüfungen, Funktionslängen, tote CSS-Klassen/JS-Dateien/
Modellfelder), `ruff`, vollständigem `pytest`-Lauf und manuellem Review
gegen die Vorgaben aus [`CLAUDE.md`](../../CLAUDE.md).

**Gesamteindruck:** Die Architektur trägt. Autorisierung ist konsequent
zentralisiert, Uploads sind inhaltlich geprüft, Verschlüsselung und
Hard-Delete sind durchgängig umgesetzt. Die Probleme liegen nicht in der
Substanz, sondern in **fehlender Testabsicherung** und **Altlasten aus
mehrfach umgebauten Features**.

---

## Was ausdrücklich in Ordnung ist

Damit die Liste unten nicht den falschen Eindruck erweckt – geprüft und
sauber befunden:

- **Keine Autorisierungslücke gefunden.** Alle 103 Routen wurden per AST
  gegen bekannte Schutz-Aufrufe geprüft. Die 24 zunächst auffälligen
  Treffer sind durchweg Delegationen an Helfer (`_require_admin`,
  `_hole_eigene_gruppe`, `_stammunterlage_verschieben`) oder bewusst
  öffentliche Routen (Login/OIDC).
- **Upload-Validierung** prüft Endung *und* Magic Bytes (`_signatur_passt`).
- **Keine toten Modellfelder** – jedes Feld wird gelesen und geschrieben.
- **Migrationskette** ist linear, genau ein Head (`c4d5e6f7a8b9`).
- **Keine TODO/FIXME/HACK-Marker** im Produktivcode.
- **Keine verwaisten Templates.**

---

## Befunde nach Priorität

| ID | Titel | Schwere | Status |
|---|---|---|---|
| [CA-001](#ca-001) | Zentrale Zugriffsschicht `access.py` ohne einen einzigen Test | **Hoch** | ✅ behoben (24 Tests) |
| [CA-002](#ca-002) | Audit-Log fehlt bei Wochenbericht-Zugriff und Datenexport | **Hoch** | ✅ behoben |
| [CA-003](#ca-003) | Hard-Delete-Pfade (`deletion.py`) ungetestet | **Hoch** | ✅ behoben (7 Tests) |
| [CA-004](#ca-004) | Toter Code: `heatmap.js` + ~30 CSS-Klassen der entfernten Skala | Mittel | ✅ behoben |
| [CA-005](#ca-005) | `TagebuchEintrag`: zwei parallele Speicherschemata, 49 Spalten | Mittel | ⚠️ **Befund korrigiert – bewusst nicht umgesetzt** |
| [CA-006](#ca-006) | Verlauf-Rendering doppelt gepflegt (driftete bereits auseinander) | Mittel | ✅ behoben |
| [CA-007](#ca-007) | 211 Deprecation-Warnungen pro Testlauf verdecken echte Warnungen | Mittel | ✅ behoben (0 Warnungen) |
| [CA-008](#ca-008) | Rate-Limiting nur beim Login | Niedrig | ✅ behoben |
| [CA-009](#ca-009) | 28 Funktionen > 40 Zeilen, 6 Dateien > 500 Zeilen | Niedrig | 🟡 teilweise (die zwei schlimmsten) |
| [CA-010](#ca-010) | `ruff`-Verstoß in bereits angewendeter Initial-Migration | Niedrig | ✅ behoben |

**Zusätzlich bei der Umsetzung gefunden** (beides in den jeweiligen Commits
behoben): `get_current_user_optional` prüfte `aktiv` nicht – ausgerechnet
das Dashboard nutzt diese Variante, ein deaktivierter Account behielt damit
vollen Zugriff auf die Startseite. Und die PSM-Ansicht zeigte die
Antworten der neuen Übungstypen nicht, ein freigegebener Tag kam
unvollständig an.

---

### CA-001 – Zentrale Zugriffsschicht ohne Tests {#ca-001}

**Schwere: Hoch · Aufwand: L**

`app/core/access.py` (378 Zeilen) entscheidet für *alle* Module, wer was
sehen darf – und hat **keinen einzigen Test**. Ebenso ungetestet:
`audit.py`, `rate_limit.py`, `datenexport.py`, `faellige_karten.py`,
`pdf_merge.py`, `wochenbericht_export.py`, `static_cache.py`, `oidc.py`.

Insgesamt stehen **103 Routen 6 Testdateien** gegenüber; ganz ohne eigene
Tests sind `admin.py` (19 Routen), `bewerbungen.py` (18), `wochenberichte.py`
(7), `freigaben.py` (4), `oidc.py` (2).

Das widerspricht CLAUDE.md §20 direkt, wo Berechtigungs-, Ownership- und
Löschtests als **Pflicht** stehen. Der aktuelle Schutz beruht allein auf
Review – jede Umstellung an `access.py` kann still eine Rolle zu viel
freischalten, ohne dass ein Test anschlägt.

**Empfehlung:** Pro Rollenpaar (Teilnehmer↔fremder Teilnehmer, PSM ohne/mit
Freigabe, Trainer ohne/mit Zuordnung, Admin) je ein Test gegen die
sensiblen Leserouten. Priorität auf `hat_wohlbefinden_freigabe`,
`sichtbare_wohlbefinden_tage`, `hat_bewerbungs_freigabe`,
`require_kanban_access`, `sichtbare_karten_filter`.

---

### CA-002 – Fehlende Audit-Logs {#ca-002}

**Schwere: Hoch · Aufwand: S**

CLAUDE.md §4 verlangt: *„Jeder Zugriff auf sensible Daten wird
protokolliert."* Tatsächlich existieren im gesamten Code nur **zwei**
`protokolliere(...)`-Aufrufe (Bewerbungen- und Wohlbefinden-Fremdansicht).

Nicht protokolliert werden:
- **Wochenberichte:** Berufstrainer:innen lesen fremde Berichte über
  `app/routers/wochenberichte.py` ohne jeden Log-Eintrag – Wochenberichte
  enthalten Freitext zum Arbeitsalltag und sind damit personenbezogen.
- **Datenexport** (`app/core/datenexport.py`): Ein vollständiger Export
  aller eigenen Daten erzeugt keinen Audit-Eintrag. Für Selbstauskünfte
  ist das der belegrelevanteste Vorgang überhaupt.

**Empfehlung:** In beiden Pfaden `protokolliere(...)` ergänzen und
`AuditAktion` um die zwei fehlenden Werte erweitern (additive Migration).

---

### CA-003 – Hard-Delete-Pfade ungetestet {#ca-003}

**Schwere: Hoch · Aufwand: M**

`app/core/deletion.py` (190 Zeilen) implementiert das Löschkonzept aus
CLAUDE.md §10 inklusive kaskadierender Löschung von Uploads, Freigaben,
Karten und Gruppen – ohne Test. Genau hier ist ein stiller Fehler am
teuersten: Übrig bleibende, verschlüsselte Dateien oder Freigabe-Zeilen
fallen im Betrieb nicht auf, sind aber ein DSGVO-Verstoß.

Verschärfend: Die Pfade wurden zuletzt bei jedem neuen Upload-Feld
angefasst (Zeichnung → Dankbarkeitsfoto → generische Übungsdatei). Jede
neue Datei-Spalte muss an **zwei** Stellen nachgetragen werden
(`wohlbefinden.py:tag_loeschen` und `deletion.py`) – ohne Test bleibt ein
Vergessen unbemerkt.

**Empfehlung:** Test, der einen Tagebucheintrag mit *allen* vier
Dateifeldern anlegt, löscht und prüft, dass weder DB-Zeile noch Datei auf
der Platte übrig bleibt. Analog für `loesche_alle_bewerbungsdaten` und
`loesche_persoenliches_kanban_board`.

---

### CA-004 – Toter Code aus entfernten Features {#ca-004}

**Schwere: Mittel · Aufwand: S**

- **`app/static/js/heatmap.js`** (30 Zeilen) wird in `base.html` an *jede*
  Teilnehmer:innen-Seite ausgeliefert, obwohl die Mood-Heatmap seit dem
  Tagebuch-Umbau nicht mehr existiert. Kein Template enthält noch
  `heatmap`-Klassen – das Skript findet nie ein Element.
- **~30 tote CSS-Klassen** in `style.css` (1482 Zeilen), Reste der
  entfernten Stimmungs-Skala: `emoji-picker*`, `emoji-slider*`,
  `heatmap-*`, `auswertung-*`, `trend-auf/ab/gleich`, `scale-input`,
  `tag-kommentar-btn*`, `kommentar-panel*`, `tage-widget`, `wochen-nav`,
  `fortschritt-signal`, `zeitlinie-toast`, `chip-danger`.
  *(Nicht tot, nur dynamisch erzeugt: `avatar-0`…`avatar-4`.)*

**Empfehlung:** `heatmap.js` samt `<script>`-Zeile löschen, die genannten
CSS-Blöcke entfernen. Rein additiv rückbaubar, kein Verhaltensrisiko.

---

### CA-005 – Zwei parallele Speicherschemata im Tagebuch {#ca-005}

**Schwere: Mittel · Aufwand: L**

`TagebuchEintrag` hat **49 Felder** und speichert Übungsergebnisse auf
zwei verschiedene Arten:

1. **Alt (typ-spezifisch):** `koerperscan_erledigt_am`,
   `grounding_erledigt_am`, `wort_des_tages`, `staerken_karte_*`,
   `mandala_erledigt_am`, `ruhe_ort_*`, `gedanke_*`,
   `sorgen_los_erledigt_am`, `dankbarkeitsfoto_pfad`, `mini_ziel_*` –
   je Übungstyp eigene Spalten.
2. **Neu (generisch, seit 0.1.40):** `morgen_uebung_*` / `abend_uebung_*`
   (erledigt_am/frage/ergebnis/datei_pfad) für alle acht neuen Typen.

Das neue Schema ist der Grund, warum die Pool-Verdopplung ohne elf
weitere Spalten auskam. Solange beide nebeneinander bestehen, ist aber
bei jeder Änderung unklar, welches gilt.

### ⚠️ Korrektur dieses Befunds (bei der Umsetzung)

Die ursprüngliche Empfehlung – „alte Typen auf das generische Schema
migrieren, danach 20+ Spalten entfernen" – **war falsch und wird bewusst
nicht umgesetzt.** Beim Prüfen der tatsächlichen Datenformen zeigte sich:

| Übungstyp | Form des Ergebnisses | passt ins generische Schema? |
|---|---|---|
| Körper-Scan, Erdung, Mandala, Sorgen loslassen | nur `erledigt_am` | ja |
| Wort des Tages, Stärken-Karte | ein Text (+ Frage) | ja |
| Zeichnung, Dankbarkeits-Foto | eine Datei | ja |
| **Ruhe-Ort** | **drei** Texte (sehen/hören/spüren) | **nein** |
| **Gedanken-Waage** | **zwei** Texte (belastend/ausgewogen) | **nein** |
| **Mini-Ziel** | ein Text **+ ein Bool** | **nein** |

Drei der elf Typen passen nicht in ein einzelnes `ergebnis`-Feld. Sie
hineinzuzwingen hieße, mehrere Werte als JSON in ein verschlüsseltes Feld
zu kodieren – das macht die Daten **schwerer** lesbar statt leichter und
gibt die feldweise Verschlüsselungs-Granularität auf, die CLAUDE.md §3
gerade fordert.

Dazu kommt: es gibt produktive Daten, die Migration wäre also nicht
folgenlos, und der Gewinn wäre rein interne Aufgeräumtheit ohne jeden
Effekt für Nutzer:innen.

**Stattdessen als Konvention festgehalten:** Neue Übungstypen mit *einer*
Antwort nutzen das generische Schema (`morgen_uebung_*`/`abend_uebung_*`)
und brauchen dann gar keine Migration mehr – so sind die acht in 0.1.40
ergänzten Typen bereits gebaut. Typen mit mehrteiligem Ergebnis bekommen
weiterhin eigene, sprechende Spalten. Die 49 Spalten sind damit kein
Wildwuchs, sondern zwei bewusst unterschiedene Fälle.

---

### CA-006 – Verlauf-Rendering doppelt gepflegt {#ca-006}

**Schwere: Mittel · Aufwand: M**

`wohlbefinden/uebersicht.html` (eigene Ansicht) und
`wohlbefinden/teilnehmer_ansicht.html` (PSM-Ansicht) rendern denselben
Verlauf in zwei getrennten, von Hand synchron gehaltenen Blöcken.

**Das ist bereits schiefgegangen:** Bei der Pool-Erweiterung auf 20 Übungen
fehlten die neuen `*_uebung_ergebnis`-Felder in der PSM-Ansicht – ein
freigegebener Tag wäre dort unvollständig dargestellt worden. *(In diesem
Durchgang gefunden und behoben, siehe CHANGELOG 0.1.40.)*

**Empfehlung:** Gemeinsames Partial `wohlbefinden/_verlauf_eintrag.html`
mit einem Flag für die Owner-Extras (Löschen, Einzel-Freigabe, Energie).
Beseitigt die Fehlerquelle strukturell.

---

### CA-007 – 211 Deprecation-Warnungen pro Testlauf {#ca-007}

**Schwere: Mittel · Aufwand: M**

Jeder `pytest`-Lauf erzeugt 211 Warnungen aus zwei Quellen:
- **29×** `datetime.utcnow()` – in Python 3.12 deprecated, entfällt künftig.
- **166×** `session.execute(select(...))` – SQLModel empfiehlt `session.exec()`.

Beides funktioniert heute, aber die Warnungsflut macht die Testausgabe
unlesbar und würde eine *echte* neue Warnung zuverlässig verstecken.

**Empfehlung:** `datetime.utcnow()` → `datetime.now(UTC)` (mechanisch,
gut testbar). Für `session.execute()` entweder projektweit auf `exec()`
umstellen oder die Warnung bewusst in `pytest.ini` filtern – dann aber mit
Begründung, damit die Entscheidung dokumentiert ist.

---

### CA-008 – Rate-Limiting nur beim Login {#ca-008}

**Schwere: Niedrig · Aufwand: S**

`app/core/rate_limit.py` wird ausschließlich in `auth.py:login_submit`
verwendet. Nicht abgesichert sind u.a. `POST /konto/passwort`
(Passwortwechsel prüft das aktuelle Passwort – online bruteforcebar) und
die Upload-Routen (10 MB pro Request, unbegrenzt oft).

**Empfehlung:** Denselben Mechanismus auf den Passwortwechsel anwenden;
für Uploads ein einfaches Kontingent pro Nutzer:in und Stunde.

---

### CA-009 – Überlange Funktionen und Dateien {#ca-009}

**Schwere: Niedrig · Aufwand: L**

CLAUDE.md §12 nennt >40 Zeilen je Funktion und >500 Zeilen je Datei als zu
vermeiden. Aktuell: **28 Funktionen** über 40 Zeilen, **6 Dateien** über
500 Zeilen.

Spitzenreiter:

| Ort | Zeilen |
|---|---|
| `core/seed.py:seed_demo_data` | 228 |
| `main.py:dashboard` | 179 |
| `routers/wohlbefinden.py:uebersicht` | 121 |
| `routers/freigaben.py:meine_freigaben` | 110 |
| `routers/wohlbefinden.py:abend_speichern` | 100 |
| `routers/wohlbefinden.py:_eintrag_anzeige` | 98 (46 Keys) |

| Datei | Zeilen |
|---|---|
| `static/css/style.css` | 1482 |
| `routers/wohlbefinden.py` | 879 |
| `routers/kanban.py` | 843 |
| `templates/wohlbefinden/uebersicht.html` | 664 |
| `routers/bewerbungen.py` | 653 |
| `static/js/tagebuch-interaktiv.js` | 533 |

`_eintrag_anzeige` ist dabei der wartungskritischste Punkt: eine
Handkopie des Models mit 46 Schlüsseln, die bei **jedem** neuen Feld an
drei Stellen (Leer-Zweig, Voll-Zweig, `_hat_inhalt`) nachgezogen werden
muss. Löst sich weitgehend mit CA-005 auf.

**Empfehlung:** Nicht pauschal aufteilen. Gezielt: `seed_demo_data` in
Abschnitte je Domäne, `dashboard` in rollenweise Helfer, `style.css` in
Basis/Komponenten/Module.

### Stand nach der Umsetzung (teilweise)

Die beiden mit Abstand schlimmsten Fälle sind aufgeteilt:

- **`seed_demo_data` 228 → 37 Zeilen**, aufgeteilt in fünf Helfer je
  Domäne (`_lege_organisation_an`, `_lege_team_karten_an`,
  `_lege_persoenliches_board_an`, `_lege_wochenbericht_an`,
  `_lege_tagebuch_an`). Verifiziert durch einen echten Seed-Lauf gegen
  eine SQLite-DB: identische Datenmengen in allen 13 Tabellen.
- **`dashboard` 179 → 40 Zeilen**, aufgeteilt in sechs Helfer; die Route
  selbst enthält jetzt nur noch die Rollenverzweigung.
- **`style.css` 1482 → 1337 Zeilen** (über CA-004).

Bewusst *nicht* weiter zerlegt: drei der neuen Seed-Helfer liegen mit
42–63 Zeilen noch über der Richtlinie, bestehen aber fast vollständig aus
deklarativen Datenlisten (`karten_plan`, `demo_tagebuch`) ohne
Verzweigungen. Sie weiter aufzuteilen würde die Lesbarkeit verschlechtern,
nicht verbessern – die Richtlinie zielt auf schwer nachvollziehbare
Logik, nicht auf Datenliteral-Länge.

Offen bleiben die großen Router (`wohlbefinden.py` 879,
`kanban.py` 843, `bewerbungen.py` 653 Zeilen) und einzelne lange
Route-Funktionen darin. Die sind jetzt durch das Testnetz aus CA-001/003
abgesichert und können bei der nächsten inhaltlichen Berührung Stück für
Stück mitgezogen werden – ein Umbau „nur wegen der Zeilenzahl" hätte
Risiko ohne Gegenwert.

---

### CA-010 – `ruff`-Verstoß in Initial-Migration {#ca-010}

**Schwere: Niedrig · Aufwand: XS**

`alembic/versions/ff957f57f077_initial_schema.py:4` hat ein
Trailing-Whitespace (W291) – der einzige verbleibende `ruff`-Fund. Bewusst
unangetastet gelassen, weil angewendete Migrationen nicht nachträglich
geändert werden. Alternative: in `ruff.toml` gezielt für
`alembic/versions/*` ausnehmen, damit `ruff check .` grün ist und echte
neue Funde nicht untergehen.

---

## Ergebnis (abgearbeitet 2026-08-12)

Neun der zehn Befunde sind umgesetzt, einer (CA-005) nach genauerer
Prüfung bewusst verworfen und der Befund selbst korrigiert.

| Kennzahl | vorher | nachher |
|---|---|---|
| Tests | 32 | **63** |
| davon Berechtigungs-/Löschtests | 0 | **31** |
| Deprecation-Warnungen pro Lauf | 211 | **0** |
| `ruff check .` | 1 Fund | **sauber** |
| längste Funktion | 228 Zeilen | **121 Zeilen** |
| `style.css` | 1482 Zeilen | 1337 Zeilen |
| ausgelieferter toter JS-Code | 30 Zeilen | 0 |

Zwei echte Fehler wurden erst durch die neuen Tests bzw. beim Umbau
sichtbar – beide behoben:

1. **Deaktivierte Accounts behielten Dashboard-Zugriff.**
   `get_current_user_optional` prüfte `aktiv` nicht, und ausgerechnet die
   Startseite nutzt diese Variante. Die Kontosperre aus VB-012 war damit
   nur halb wirksam.
2. **Freigegebene Tagebuch-Tage kamen unvollständig bei der PSM an** –
   die Antworten der acht neuen Übungstypen fehlten in deren Ansicht.

## Was als Nächstes sinnvoll wäre

Nichts davon ist dringend – die Liste dient als Anknüpfungspunkt:

- **Testabdeckung weiter ausbauen:** `admin.py` (19 Routen) und
  `bewerbungen.py` (18 Routen) haben weiterhin keine eigenen Testdateien.
  Die Zugriffsschicht darunter ist jetzt abgesichert, die Routen selbst
  noch nicht.
- **Große Router entflechten** (CA-009, siehe dort) – beiläufig bei der
  nächsten inhaltlichen Änderung, nicht als Selbstzweck.
- **`_eintrag_anzeige`** (98 Zeilen, 46 Schlüssel) ist die letzte Stelle,
  an der ein neues Tagebuch-Feld an drei Orten nachgezogen werden muss.
  Ließe sich datengetrieben aus einer Feldliste erzeugen.
