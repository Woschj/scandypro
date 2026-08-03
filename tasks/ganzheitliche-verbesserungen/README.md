# ScandyPro – Ganzheitliche Verbesserungsliste (Accountverwaltung, Mein Tag, alle Module)

**Methode:** Vollständige Durchsicht aller Router, Models, Templates und
Kern-Module (`app/core/*`) für alle fünf Rollen (Teilnehmer, Berufstrainer,
Psychosoziale Mitarbeit, Einrichtungs-Admin), bewertet aus zwei Perspektiven:
(1) Projektmanagement-Werkzeug (Kanban, Wochenberichte, Bewerbungen), (2)
Alltagshilfe im sozial-beruflichen Reha-Kontext (Struktur, Erinnerungen,
emotionale Sicherheit gemäß CLAUDE.md §24). Ergänzt das bestehende
[`tasks/uiux-audit/`](../uiux-audit/README.md), das primär visuelle/formale
UI-Befunde behandelt.

**Hinweis zu UI-001:** Der dort dokumentierte Fund (Klartext-Passwortfeld)
ist im aktuellen Stand bereits behoben (`type="password"` in beiden
Templates) – UI-001 gilt als erledigt.

---

## Reihenfolge / Priorität

| ID | Titel | Schweregrad | Rollen | Status |
|---|---|---|---|---|
| [VB-001](VB-001.md) | Private Kanban-Karten nicht durchgängig geschützt (IDOR) | Critical | T, BT | ✅ behoben |
| [VB-002](VB-002.md) | Kein "Ich brauche jetzt Unterstützung"-Button in Mein Tag | Critical | T | ✅ behoben |
| [VB-003](VB-003.md) | Kein Rate-Limiting/Brute-Force-Schutz beim Login | High | alle | ✅ behoben |
| [VB-004](VB-004.md) | `/konto` ohne Freigaben-Übersicht, keine Selbstlöschung (DSGVO) | High | T, BT, PSM | 🟡 teilweise (siehe VB-004.md) |
| [VB-005](VB-005.md) | Keine "Heute/diese Woche fällig"-Übersicht im Dashboard | High | T, BT | ✅ behoben |
| [VB-006](VB-006.md) | Mein-Tag-Minispiel-Pool auf ≥10 Übungen erweitern | High | T | 🟡 umgesetzt, aber UX-Qualität ungenügend - siehe [VB-018](VB-018.md) |
| [VB-007](VB-007.md) | Kanban-Drag&Drop vermutlich nicht touch-fähig (Mobile) | High | T, BT | ✅ bereits gelöst (Dropdown-Alternative existiert) |
| [VB-008](VB-008.md) | Board-Freigaben nicht in zentraler `/freigaben`-Übersicht | Medium | T | ✅ behoben |
| [VB-009](VB-009.md) | Bewerbungstermine ohne Uhrzeit/Ort, keine Erinnerungen | Medium | T, BT | ✅ behoben |
| [VB-010](VB-010.md) | Bewerbungs-Statuswechsel ohne emotionale Auffang-UX | Medium | T | ✅ behoben |
| [VB-011](VB-011.md) | Keine Verzahnung Kanban ↔ Wochenbericht (Doppel-Erfassung) | Medium | T | ✅ behoben |
| [VB-012](VB-012.md) | Admin-UX: keine Account-Deaktivierung, kein "zuletzt angemeldet" | Medium | A | ✅ behoben |
| [VB-013](VB-013.md) | PSM/Admin ohne Bottom-Tab-Bar auf Mobile | Medium | PSM, A | ✅ behoben |
| [VB-014](VB-014.md) | Upload-Validierung nur über Dateiendung (kein Magic-Byte-Check) | Medium | T | ✅ behoben |
| [VB-015](VB-015.md) | Demo-Logins hart codiert unabhängig von `SEED_DEMO_DATA` | Low | alle | ✅ behoben |
| [VB-016](VB-016.md) | Kaskadierendes Löschen im Kanban dupliziert statt zentral | Low | – | ✅ behoben |
| [VB-017](VB-017.md) | Bewerbungs-/Wochenbericht-Formulare stark dupliziert | Low | – | ✅ behoben (Wochenbericht) |
| [VB-018](VB-018.md) | **Komplettes Rework der Mein-Tag-Minispiele** (Nutzer: "aktuell eine Katastrophe") | High | T | 📋 Plan steht, Umsetzung offen |

Legende Rollen: T = Teilnehmer, BT = Berufstrainer, PSM = Psychosoziale
Mitarbeit, A = Einrichtungs-Admin.

## Status: abgearbeitet (2026-08-03)

Alle 17 Punkte sind bearbeitet - 15 vollständig umgesetzt, einer (VB-007)
als bereits gelöst verifiziert, einer (VB-004) bewusst nur teilweise wegen
eines echten Schema-Blockers (siehe dort). Siehe CHANGELOG.md [0.1.9] und
[0.1.10] für die vollständige Zusammenfassung, `app/version.py` steht auf
0.1.10.

**Wichtige Einschränkung:** In dieser Sandbox stand weder Docker noch
PostgreSQL zur Verfügung. Verifiziert wurde durchgängig mit `py_compile`,
Jinja2-Template-Parsing und manuellem Code-Review gegen die bestehenden
Konventionen - **nicht** mit einem laufenden Server oder echten
Datenbank-Migrationen. Vor dem produktiven Einsatz unbedingt:
1. `alembic upgrade head` gegen eine Testdatenbank laufen lassen (3 neue
   Migrationen: `c3d4e5f6a7b8`, `d5e6f7a8b9c0`, `e6f7a8b9c0d1`)
2. Alle fünf Demo-Rollen einmal durchklicken, insbesondere die neuen
   Mein-Tag-Übungstypen (VB-006) und den Foto-Upload (multipart-Formular)
3. `ruff check .` laufen lassen (in dieser Sandbox nicht verfügbar)

Abgearbeitet wird strikt in obiger Reihenfolge; Status wird hier und in der
jeweiligen VB-XXX.md-Datei aktuell gehalten.
