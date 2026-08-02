# ScandyPro – UI/UX Audit

**Methode:** Vollständige statische Durchsicht aller 27 Jinja2-Templates
(`app/templates/**`), des gesamten Design-Systems (`app/static/css/style.css`,
845 Zeilen), beider JS-Module (`kanban.js`, `wohlbefinden.js`) sowie
stichprobenartig der zugehörigen Router (`app/routers/*.py`), abgeglichen
gegen `CLAUDE.md`, `docs/KONZEPT.md` und `docs/DATENSCHUTZ_UND_BERECHTIGUNGEN.md`.

**Einschränkung:** In dieser Sandbox stehen weder Docker noch PostgreSQL zur
Verfügung, ein Live-Durchklicken mit echten Seed-Daten war daher nicht
möglich. Bei einer server-gerenderten Jinja2/HTMX-losen Anwendung ohne
Client-Routing lässt sich der tatsächliche Rendering-Output aus den
Templates jedoch mit hoher Zuverlässigkeit rekonstruieren; alle Befunde unten
sind an konkreten Code-Stellen festgemacht (Datei + Zeile), nicht spekulativ.
Empfehlung: vor Produktivsetzung zusätzlich einen Klick-Durchlauf mit allen
fünf Demo-Rollen (`teilnehmer`, `teilnehmer2`, `trainer`, `psycho`, `admin`)
durchführen, um Bildschirm-Screenshots als Ergänzung zu diesem Dokument zu
gewinnen.

---

## Executive Summary

ScandyPro hat ein ungewöhnlich gut durchdachtes *Fundament*: ein einziges
CSS-Custom-Property-System für Farben/Radius/Spacing, konsequente
"nur für dich sichtbar"-Hinweise auf jeder sensiblen Seite, ruhige
Leer-Zustände statt bedrohlicher Fehlermeldungen, und ein bewusst
zurückhaltendes Erfolgs-Feedback im Kanban (warmer Glow statt Konfetti) –
das ist im Reha-Kontext genau richtig und in dieser Form selten so
konsequent umgesetzt. Das Team hat CLAUDE.md Abschnitt 24 ("UX-Leitlinien
für Reha-Kontexte") sichtbar ernst genommen.

Gleichzeitig ist die Anwendung noch ein Prototyp mit mehreren Lücken, die
vor einem Produktiv-Release geschlossen werden sollten. Die gravierendsten:

1. **Ein Sicherheits-/Datenschutz-relevanter UI-Bug**: In der
   Benutzerverwaltung werden neue und zurückgesetzte Passwörter im
   Klartext-Textfeld (`type="text"`) statt maskiert angezeigt – bei einer
   Anwendung, deren eigenes Datenschutzkonzept "keine unsicheren Sessions"
   und Art.-32-Konformität fordert, ein klarer Widerspruch (UI-001).
2. **Kein Tastatur-Zugang zur zentralen Kanban-Interaktion**: Karten
   zwischen Spalten bewegen funktioniert ausschließlich per Maus-Drag&Drop
   (native HTML5-DnD). Für Tastatur- und Switch-Nutzer:innen – gerade im
   Reha-Kontext keine Randgruppe – ist der Kern-Workflow des Kanban-Moduls
   nicht bedienbar (UI-003, WCAG 2.1.1).
3. **Rohe Fehlerseiten statt der eigenen, sanften Sprache**: Validierungs-
   fehler (z. B. falscher Dateityp beim Upload, ungültige Freigabe-Auswahl)
   werden serverseitig als unbehandelte `HTTPException` geworfen und landen
   beim Nutzer als nackte FastAPI-JSON-Antwort – ein kompletter Bruch mit
   dem selbst auferlegten Grundsatz "sanfte Sprache, keine
   Behörden-/Klinik-Jargon" (UI-002).
4. **Tech-Stack-Abweichung mit UX-Konsequenz**: CLAUDE.md schreibt
   "Jinja2 + HTMX + Alpine.js" vor; tatsächlich enthält keines der 27
   Templates ein `hx-*`-Attribut. Jede Aktion außer Kanban-Drag&Drop und dem
   Stimmungs-Regler löst einen vollen Seiten-Reload aus – spürbar in
   Formularen mit vielen Feldern (Wochenbericht) und beim Umschalten von
   Kartenzuweisungen. Das kostet gefühlte Performance und Konsistenz zum
   eigenen Architekturdokument.

## UX-Reifegrad-Einschätzung

| Dimension | Einschätzung |
|---|---|
| Visuelles Design-System | **Solide** – ein Token-Set, konsequent genutzt |
| Emotionale Sicherheit (Reha-Kontext) | **Stark** – Vorbildlich für die Zielgruppe |
| Datenschutz-Transparenz im UI | **Stark** – Sichtbarkeits-Hinweise, Freigaben, Audit-Log |
| Barrierefreiheit | **Lückenhaft** – mehrere WCAG-AA-relevante Lücken |
| Interaktionsqualität/Feedback | **Prototyp-Niveau** – volle Reloads, keine Ladezustände |
| Konsistenz (Icons, Buttons, Bestätigungsmuster) | **Uneinheitlich** |
| Responsive/Mobile | **Grundsätzlich funktional**, mit konkreten Bugs |
| Tabellen/Listen | **Ausreichend für aktuelle Größenordnung** |

Insgesamt: **Prototyp mit gutem Fundament, noch nicht produktionsreif.**
Die größten Hebel liegen nicht im visuellen Feinschliff, sondern in
Fehlerbehandlung, Tastaturzugänglichkeit und Interaktions-Feedback.

## Größte Usability-Probleme

- Kein Tastaturzugang zu Kanban-Drag&Drop (UI-003)
- Unbehandelte Fehlerfälle zeigen rohe JSON-Antworten (UI-002)
- Kein Lade-/Deaktivierungs-Zustand auf Buttons während POST-Requests →
  Doppel-Submit-Risiko, z. B. doppelt angelegte Karten/Boards (UI-007)
- Lange, flach gerenderte Wochenbericht-Formulare ohne Fortschritts-
  Gliederung – widerspricht der eigenen "kognitive Entlastung"-Leitlinie
  (UI-014)

## Größte Design-Inkonsistenzen

- Destruktive Aktionen (Karte/Spalte/Board löschen, Freigabe entfernen,
  Unteraufgabe löschen) sehen optisch identisch aus wie harmlose Aktionen
  (alle `btn-ghost`) und nutzen zwei verschiedene Bestätigungsmuster
  (`confirm()` vs. "LÖSCHEN" eintippen) ohne erkennbare Logik, wann welches
  gilt (UI-005)
- Icon-Vokabular ist rohes Unicode (⋮ ✕ ▲ ▼ ‹ › 📅 🔒 💬 ✓) statt eines
  einheitlichen Icon-Sets – Rendering und Gewichtung variieren je
  Betriebssystem/Browser (UI-010)
- "Verwaltung"-Dropdown im Admin-Nav enthält 3 von 4 Verwaltungsseiten,
  "Abteilungen" liegt separat auf oberster Ebene (UI-017)

## Accessibility-Zusammenfassung (WCAG 2.2 AA, Stichproben)

| Kriterium | Befund |
|---|---|
| 2.1.1 Keyboard | **Verletzt** – Kanban-DnD ohne Tastaturalternative (UI-003) |
| 1.4.1 Use of Color | **Grenzwertig** – Mood-Heatmap fast ausschließlich farbcodiert, Tooltip nur per Hover (UI-012) |
| 4.1.2 Name, Role, Value | **Teilweise verletzt** – mehrere Icon-Only-Buttons ohne zugänglichen Namen (UI-011) |
| 4.1.3 Status Messages | **Verletzt** – Toasts/Speicher-Bestätigungen ohne `aria-live` (UI-008) |
| 1.4.3 Contrast | **Zu prüfen** – mehrere Chip-/Label-Texte bei 11–12px auf pastelligem Hintergrund (UI-019) |
| 2.4.7 Focus Visible | **Erfüllt** – globales `:focus-visible` mit Akzentfarbe |
| 2.5.5 Target Size | **Grenzwertig** – `.btn-sm` bei 32px unter dem 44px-Komfortmaß, für Zielgruppe mit ggf. eingeschränkter Feinmotorik relevant |

## Quick Wins (geringer Aufwand, hoher Nutzen)

- UI-001 Passwortfelder maskieren (`type="password"`) – **XS**
- UI-011 `aria-label` auf Icon-Only-Buttons ergänzen – **S**
- UI-006 `accept`-Attribut auf Datei-Inputs setzen – **XS**
- UI-017 "Abteilungen" ins Verwaltungs-Dropdown verschieben – **XS**
- UI-018 widersprüchlichen Copy-Text in `bewerbungen/kein_zugriff.html`
  korrigieren – **XS**

## Langfristige Verbesserungen

- UI-002 Einheitliche, sprachlich sanfte Fehlerseiten/-banner für alle
  `HTTPException`-Fälle (globaler Exception-Handler + Template)
- UI-003 Tastaturbedienbare Alternative zum Kanban-Drag&Drop (z. B. Aktions-
  Menü "Verschieben nach …" pro Karte)
- Schrittweise HTMX-Einführung gemäß eigenem Tech-Stack-Dokument, um volle
  Seiten-Reloads durch partielle Updates zu ersetzen
- Einheitliches Icon-Set anstelle roher Unicode-Glyphen
- Dark-Mode gemäß CLAUDE.md Abschnitt 19 (aktuell nicht vorhanden)

---

## Aufgabenliste

Siehe `UI-001.md` bis `UI-022.md` in diesem Verzeichnis. Jede Datei ist
eigenständig umsetzbar und enthält Titel, Schweregrad, Priorität, Kategorie,
Fundort, Problem, Begründung, erwartete Wirkung, Lösungsvorschlag, Aufwand,
Abhängigkeiten und Abnahmekriterien.

| ID | Titel | Schweregrad | Priorität | Aufwand |
|---|---|---|---|---|
| UI-001 | Passwortfelder im Klartext | Critical | P0 | XS |
| UI-002 | Rohe Fehlerantworten statt gestalteter Fehlerseiten | Critical | P0 | M |
| UI-003 | Kanban-Drag&Drop ohne Tastaturalternative | Critical | P0 | L |
| UI-004 | Kein Dark-Mode trotz Vorgabe | High | P1 | M |
| UI-005 | Destruktive Aktionen visuell/interaktiv inkonsistent | High | P1 | M |
| UI-006 | Datei-Uploads ohne `accept`/Client-Validierung | High | P1 | S |
| UI-007 | Kein Lade-/Disabled-Zustand bei Formular-Submits | High | P1 | M |
| UI-008 | Toasts ohne `aria-live` | High | P1 | S |
| UI-009 | Sticky-Topnav ohne Mobile-Kollaps | High | P1 | M |
| UI-010 | Uneinheitliches Icon-Vokabular | Medium | P2 | M |
| UI-011 | Icon-Only-Buttons ohne zugänglichen Namen | Medium | P2 | S |
| UI-012 | Mood-Heatmap farbcodiert ohne Touch-Alternative | Medium | P2 | S |
| UI-013 | Pervasive Inline-Styles unterlaufen Design-System | Medium | P2 | M |
| UI-014 | Wochenbericht-Formular kognitiv überladen | Medium | P2 | M |
| UI-015 | Toast-Position bricht bei mehrzeiliger Nav | Medium | P2 | S |
| UI-016 | Selects ohne Platzhalter-Option (stille Vorauswahl) | Medium | P2 | S |
| UI-017 | Inkonsistente Admin-Nav-Gruppierung | Medium | P2 | XS |
| UI-018 | Widersprüchlicher Copy-Text (Bewerbungs-Freigabe) | Medium | P2 | XS |
| UI-019 | Kleine Chip-/Label-Schrift, Kontrast ungeprüft | Medium | P2 | S |
| UI-020 | Keine Sortierung/Filter/Suche in Verwaltungstabellen | Low | P3 | S |
| UI-021 | Kein Autosave/Verlassen-Warnung bei langen Formularen | Medium | P2 | S |
| UI-022 | "Kein Zugriff"-Seiten sind Sackgassen | Low | P3 | XS |
