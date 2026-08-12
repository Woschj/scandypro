# Datenschutz- und Berechtigungskonzept (ScandyPro)

> Dieses Dokument ist verbindlich für alle Entscheidungen an Datenmodell,
> API und UI. Es wird bei jeder relevanten Änderung mit aktualisiert. Bei
> Widerspruch zwischen diesem Dokument und einer Anforderung gewinnt der
> Datenschutz – Rückfrage statt stillschweigender Abweichung.

Rechtlicher Rahmen: DSGVO, insbesondere Art. 5 (Grundsätze), Art. 6
(Rechtsgrundlage), Art. 9 (besondere Kategorien personenbezogener Daten –
Gesundheitsdaten), Art. 15–20 (Betroffenenrechte, u. a. Löschung,
Datenübertragbarkeit), Art. 25 (Privacy by Design/Default), Art. 32
(Sicherheit der Verarbeitung). ScandyPro ist kein juristisches, sondern ein
technisches Umsetzungsdokument – bei Einführung in einer echten Einrichtung
muss zusätzlich ein rechtlich geprüftes Datenschutzkonzept
(Verarbeitungsverzeichnis, ggf. DSFA) durch die Einrichtung selbst erstellt
werden. Dieses Dokument liefert dafür die technische Grundlage.

---

## 1. Grundprinzipien

- **Datensparsamkeit**: Nur erfassen, was für den jeweiligen Zweck nötig ist.
  Kein Feld "auf Vorrat".
- **Zweckbindung**: Wohlbefinden-Daten dienen der Selbstreflexion des
  Teilnehmers, nicht der Leistungsbeurteilung durch die Einrichtung.
  Bewerbungsdaten dienen der Unterstützung im Bewerbungsprozess.
  Vermischung der Zwecke ist zu vermeiden.
- **Selbstbestimmung vor Fürsorge**: Der Teilnehmer entscheidet, wer seine
  sensiblen Daten sieht – nicht die Einrichtung per Voreinstellung.
- **Privacy by Default**: Neue sensible Datentypen sind standardmäßig
  privat (nur für den Teilnehmer selbst sichtbar), niemals standardmäßig
  für Betreuer/Admins offen.
- **Nachvollziehbarkeit**: Jeder Zugriff auf sensible Daten durch eine
  andere Person als den Teilnehmer wird protokolliert.
- **Löschbarkeit**: Für jede Datenkategorie mit Personenbezug muss ein
  vollständiger, unwiderruflicher Löschweg existieren, bevor die
  Datenkategorie live geht.

---

## 2. Rollenmodell

| Rolle | Beschreibung |
|---|---|
| `teilnehmer` | Reha-Teilnehmer:in. Eigentümer:in aller eigenen Daten. |
| `berufstrainer` | Unterstützt bei Bewerbungsprozess und internen Projekten/Kanban. |
| `psychosoziale_mitarbeit` | Unterstützt bei mentaler Belastbarkeit/Wohlbefinden. |
| `einrichtungs_admin` | Verwaltet Accounts, Rollen, technische Administration. |

Ein Nutzer kann in Ausnahmefällen mehrere Rollen haben (z. B. Admin, der
gleichzeitig Berufstrainer ist) – Berechtigungsprüfung erfolgt trotzdem
immer pro Rolle einzeln, nie über "hat irgendeine Rolle mit Zugriff".

---

## 3. Berechtigungsmatrix (Standard, ohne explizite Freigabe)

| Datenbereich | Teilnehmer (eigene Daten) | Berufstrainer | Psychosoziale Mitarbeit | Einrichtungs-Admin |
|---|---|---|---|---|
| Kanban/Tickets (interne Projekte) | Lesen/Schreiben | Lesen/Schreiben (zugewiesene Boards) | Kein Standardzugriff | Kein inhaltlicher Zugriff, nur technische Verwaltung |
| Wohlbefinden-Einträge | Lesen/Schreiben/Löschen | **Kein Zugriff** | **Nur nach expliziter Freigabe** | **Kein Zugriff** |
| Bewerbungs-Einträge | Lesen/Schreiben/Löschen | **Nur nach expliziter Freigabe** | **Kein Zugriff** | **Kein Zugriff** |
| Stammdaten (Name, Kontakt) | Lesen/Schreiben (eigene) | Lesen (zugeordnete Teilnehmer) | Lesen (zugeordnete Teilnehmer) | Lesen/Schreiben (Verwaltung) |
| Audit-Log der eigenen Daten | Lesen (wer hat wann auf meine Daten zugegriffen) | Nein | Nein | Nein (außer eigene Admin-Aktionen im Log der Einrichtung) |

Freigaben (Consent) sind:

- **granular**: pro Datenkategorie (nicht "alles freigeben"), idealerweise
  sogar pro Zeitraum/Eintrag möglich
- **widerrufbar**: jederzeit durch den Teilnehmer entziehbar, Wirkung sofort
- **zeitlich befristbar**: optionale automatische Ablaufzeit
- **sichtbar**: der Teilnehmer sieht jederzeit, wer aktuell Zugriff auf was hat

Administrativer Zugriff auf Inhalte (z. B. Support-Fall) ist kein
Standardrecht, sondern ein protokollierter Ausnahmeprozess (Break-Glass):
Begründung erforderlich, zeitlich begrenzt, vollständig geloggt, im
Idealfall mit Benachrichtigung an den Teilnehmer.

---

## 4. Technische Schutzmaßnahmen

### 4.1 Verschlüsselung

- Sensible Freitextfelder (Wohlbefinden-Notizen, Bewerbungsnotizen,
  hochgeladene Bewerbungsdokumente) werden feldweise/objektweise
  verschlüsselt gespeichert (Vorbild: Fernet-Ansatz aus
  `scandy-lite/app/core/crypto.py`).
- Verschlüsselungs-Keys getrennt von der Datenbank verwalten (ENV/Secret
  Store), niemals im Repository oder Docker-Image.
- Transport ausschließlich über TLS (Caddy als Reverse Proxy, wie in
  Scandy-Lite).

### 4.2 Zugriffskontrolle

- Zentrale Autorisierungs-Schicht (analog `access.py` in Scandy-Lite),
  die für jede Anfrage prüft: Rolle + Ownership + aktive Freigabe.
- Keine Berechtigungslogik verstreut in einzelnen Routen duplizieren.
- Serverseitige Prüfung bei jedem Endpoint, unabhängig vom Frontend-Zustand.
- Schutz vor IDOR: IDs allein reichen nie als Zugriffsnachweis.

### 4.3 Audit-Logging

- Protokolliert wird: Zugriff auf Wohlbefinden-/Bewerbungsdaten durch
  Nicht-Eigentümer (wer, wann, welcher Datensatz, auf Basis welcher
  Freigabe).
- Audit-Log selbst enthält keine Inhalte, nur Metadaten (kein Klartext der
  sensiblen Einträge).
- Audit-Log-Einträge zu gelöschten Personen werden pseudonymisiert
  (Personenbezug entfernt), nicht 1:1 mitgelöscht, sofern sie aus
  Sicherheitsgründen (z. B. Nachweis von Fehlzugriffen) aufbewahrt werden
  müssen – Aufbewahrungsdauer explizit begrenzen.

### 4.4 Authentifizierung

- Lokale Accounts mit bcrypt-Hashing.
- Optionales OIDC/SSO (siehe `app/core/oidc.py`, `app/routers/oidc.py`) -
  analog zu `oidc.py` in Scandy-Lite, damit beide Apps langfristig gegen
  denselben Identity-Provider laufen können (zentral gesteuerte
  Nutzer:innen). Der Provider klärt nur die Identität; Rolle und
  Freischaltung bleiben immer eine bewusste, lokale Admin-Entscheidung -
  ein per SSO neu erkannter Account startet inaktiv und ohne Rolle
  (CLAUDE.md §8: "Rollen ... niemals implizit"). Lokales Passwort-Login
  bleibt in jedem Fall parallel nutzbar, auch für SSO-Accounts optional
  als Alternative einrichtbar.
- Sinnvolle Session-Timeouts, sichere Cookies (HttpOnly, Secure, SameSite),
  Rate-Limiting auf Login/Passwort-Reset.
- 2FA als spätere Ausbaustufe einplanen, insbesondere für
  Betreuer-/Admin-Rollen.

### 4.5 Datenminimierung im UI

- Listen-/Übersichtsansichten für Betreuer zeigen nur, was für ihre Rolle
  nötig ist (z. B. Berufstrainer sieht Kanban-Fortschritt, nicht
  automatisch Bewerbungsdetails).
- Keine "globale Suche", die versehentlich über Rollengrenzen hinweg
  sensible Daten anzeigt.

---

## 5. Löschkonzept (Recht auf Löschung, Art. 17 DSGVO)

- Für Wohlbefinden- und Bewerbungsdaten gilt: **echtes Hard-Delete**, kein
  reiner Soft-Delete/Papierkorb wie bei unkritischen Scandy-Lite-Assets.
- Löschung durch den Teilnehmer selbst muss im UI möglich sein:
  - einzelner Eintrag
  - ganze Datenkategorie (z. B. "alle Wohlbefinden-Einträge löschen")
  - vollständiges Konto inkl. aller personenbezogenen Daten
- Kaskadierende Löschung muss erfassen: DB-Zeilen, hochgeladene Dateien
  (Storage), aktive Freigaben, ggf. Caches/Suchindizes.
- Bei jeder neuen Tabelle mit Personenbezug: Löschroutine/Migration ist
  Teil der Definition of Done, nicht nachträglich.
- Backups: Löschkonzept muss auch für Backups mitgedacht werden
  (z. B. maximale Backup-Retention definieren, damit gelöschte Daten nicht
  faktisch unbegrenzt in Backups fortbestehen).
- Kanban/Projekt-Daten (weniger sensibel, oft auch für Einrichtungs-
  Dokumentation relevant) können nach Soft-Delete-Muster wie in Scandy-Lite
  behandelt werden – Ausnahme ist bewusst nur für diesen Bereich zulässig.

### 5.1 Umsetzung der vollständigen Konto-Löschung

Umgesetzt in `app/core/deletion.py:loesche_konto_vollstaendig`, ausgelöst
über die Benutzerverwaltung (`/admin/benutzer`). Die Löschung unterscheidet
drei Arten von Personenbezug:

| Art des Bezugs | Behandlung |
|---|---|
| **Eigene Inhalte** – Tagebuch inkl. Fotos, Bewerbungen inkl. Unterlagen, Wochenberichte, persönliches Kanban-Board | gelöscht, inklusive der Dateien im Storage |
| **Zugehörigkeiten** – Kartenzuweisungen, Gruppen-/Handlungsfeld-Mitgliedschaften, PSM-/Trainer-Zuordnungen, erteilte und erhaltene Freigaben | Zeilen entfernt |
| **Urheberschaft an Team-Inhalten** – wer eine Karte/ein Board angelegt oder eine Karte bewegt hat | auf NULL gesetzt, der Inhalt bleibt |
| **Audit-Log** | bleibt vollständig erhalten |

**Warum Team-Karten bestehen bleiben:** Auf Team-Boards arbeiten mehrere
Menschen gemeinsam. Eine Kaskaden-Löschung würde fremde Arbeitsergebnisse
vernichten, nur weil eine Person die Einrichtung verlässt. Stattdessen
bleibt die Karte stehen und erscheint **ohne Zuständige** – die Leitung des
Handlungsfelds entscheidet dann, ob sie neu vergeben oder entfernt wird.
Die Verwaltung erhält nach der Löschung eine Meldung, wie viele Karten das
betrifft.

**Warum das Audit-Log bleibt:** Abschnitt 4.3 und CLAUDE.md §9 verlangen
*pseudonymisierte* Löschung, nicht das Verschwinden des Nachweises.
`akteur_id` und `ziel_teilnehmer_id` tragen deshalb keinen Fremdschlüssel;
der Eintrag belegt weiterhin, dass ein Zugriff stattgefunden hat, ohne dass
die Person noch existiert. Inhalte standen dort ohnehin nie.

**Grenze:** Backups, die vor der Löschung entstanden sind, enthalten die
Daten weiterhin. Sie laufen über die Aufbewahrungsfrist aus (Standard:
6 Monatsstände, siehe [BACKUP.md](BACKUP.md)) – diese Frist ist damit
zugleich die maximale Zeit, bis eine Löschung auch dort durchgeschlagen
ist, und muss der Einrichtung bekannt sein.

---

## 6. Datenübertragbarkeit (Art. 20 DSGVO)

- Teilnehmer sollen ihre eigenen Daten (Wohlbefinden-Historie,
  Bewerbungs-Historie) in einem strukturierten, gängigen Format
  exportieren können (z. B. JSON/CSV/PDF).
- Export ist eine Funktion, die früh mitgeplant, aber nicht zwingend in der
  ersten Ausbaustufe umgesetzt werden muss – bei Datenmodell-Entscheidungen
  aber nicht verbauen.

---

## 7. Was explizit vermieden wird

- Keine automatische Eskalation von Wohlbefinden-Daten an Betreuer ohne
  Zustimmung (kein "Alarm bei niedrigem Wert an psychosoziale Mitarbeit").
  Dies ist eine bewusste Produktentscheidung zugunsten der Selbstbestimmung
  und muss vor Einführung einer solchen Funktion explizit mit dem Nutzer
  besprochen werden – nicht stillschweigend implementieren.
- Keine Zusammenführung von Bewerbungs- und Wohlbefinden-Daten in
  Auswertungen, die Rückschlüsse auf Krankheitsbilder für Berufstrainer
  ermöglichen würden.
- Kein Tracking/Analytics von Drittanbietern auf Seiten mit sensiblen
  Daten.
- Keine Klartext-Logs, Fehlermeldungen oder Stacktraces mit Inhalten aus
  Wohlbefinden- oder Bewerbungseinträgen.
- Kein Multi-Tenant-Betrieb einer zentralen Instanz für mehrere
  Einrichtungen (Entscheidung: self-hosted pro Einrichtung) – reduziert
  Angriffsfläche und Mandanten-Verwechslungsrisiko erheblich.

---

## 8. Offene Punkte / bei Bedarf zu klären

- 2FA-Pflicht für Betreuer-/Admin-Rollen: ja/nein, ab welcher Ausbaustufe?
- Konkrete Aufbewahrungsfristen für Audit-Logs.
- Ob und wie eine Krisen-/Notfall-Funktion (z. B. akute Selbstgefährdung)
  ohne die Selbstbestimmungs-Prinzipien zu verletzen abgebildet werden
  kann – falls gewünscht, gesondert und sehr sorgfältig konzipieren, nicht
  nebenbei implementieren.
- Rechtliche Prüfung durch die jeweilige Einrichtung vor Produktivbetrieb.
