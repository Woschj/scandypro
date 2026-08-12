# Changelog

Alle nennenswerten Änderungen an ScandyPro werden hier dokumentiert.

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/) (vor
1.0.0: `0.MINOR.PATCH`, MINOR kann auch für neue Features brechende Änderungen
enthalten - üblich für Software vor dem ersten stabilen Release). Gepflegt
analog zum Schwestermodul Scandy-Lite.

## [0.1.42] - 2026-08-12

### Security
- **Deaktivierte Accounts behielten Zugriff auf das Dashboard.**
  `get_current_user_optional` prüfte im Gegensatz zu `get_current_user`
  das `aktiv`-Flag nicht - und ausgerechnet die Startseite nutzt diese
  Variante. Ein zwischenzeitlich deaktivierter Account sah damit weiterhin
  Kontaktdaten, "Was steht an" inklusive Kartentiteln und den
  Wochenrückblick; die Kontosperre aus VB-012 war nur halb wirksam.
  Gefunden durch die neuen Berechtigungstests.

### Added
- **Berechtigungstests für `app/core/access.py`** (24 Tests, CA-001):
  vollständige Organisationsstruktur als Fixture, dann je Zugriffspfad
  Negativ- und Positivfall - Zuordnung ohne Freigabe und Freigabe ohne
  Zuordnung blocken beide, Widerruf und Ablauf greifen sofort,
  Einzelfreigaben zeigen wirklich nur das eine Element, private
  Kanban-Karten bleiben auch dem zuständigen Trainer verborgen.
- **Löschtests für `app/core/deletion.py`** (7 Tests, CA-003): prüfen
  nicht nur DB-Zeilen, sondern dass keine verschlüsselte Datei auf der
  Platte zurückbleibt - auch beim Ersetzen eines Uploads und beim Löschen
  eines einzelnen Tages.
- **Audit-Logs für Wochenbericht-Zugriff und Datenexport** (CA-002).
  CLAUDE.md §4 verlangt die Protokollierung jedes Zugriffs auf sensible
  Daten; es gab bisher nur zwei `protokolliere()`-Aufrufe im gesamten
  Code. Migration `d5e6f7a8b9c1`.
- **Rate-Limiting auf dem Passwortwechsel** (CA-008) - er prüft das
  aktuelle Passwort und war damit genauso bruteforcebar wie der Login.

### Changed
- **Verlauf-Rendering als gemeinsames Partial** (CA-006):
  `wohlbefinden/_verlauf_eintrag.html` mit `ist_owner`-Flag statt zweier
  von Hand synchron gehaltener Blöcke. `teilnehmer_ansicht.html`:
  95 → 27 Zeilen.
- **211 Deprecation-Warnungen pro Testlauf auf 0** (CA-007): `jetzt()`
  aus `app/core/zeit.py` ersetzt das deprecated `datetime.utcnow()` an 48
  Stellen (bewusst UTC-naiv, passend zu den `sa.DateTime()`-Spalten - ein
  Wechsel auf zeitzonenbewusste Werte hätte Vergleiche zerbrochen). Die
  `session.execute()`-Warnung ist dagegen keine echte Deprecation, sondern
  SQLModels Werbung für die eigene `exec()`-API, und wird begründet
  gefiltert statt in 166 riskanten Einzelumbauten beseitigt.
- **`seed_demo_data` 228 → 37 Zeilen** und **`dashboard` 179 → 40 Zeilen**
  (CA-009), aufgeteilt in Helfer je Domäne bzw. je Rolle. Der Seed-Lauf
  wurde gegen eine echte SQLite-DB verifiziert: identische Datenmengen in
  allen 13 Tabellen.
- `ruff check .` ist erstmals vollständig grün (CA-010).

### Removed
- **Toter Code** (CA-004): `heatmap.js` wurde an jede
  Teilnehmer:innen-Seite ausgeliefert, obwohl die Mood-Heatmap seit dem
  Tagebuch-Umbau nicht mehr existiert. Dazu 145 Zeilen toter CSS aus der
  entfernten Stimmungs-Skala. `style.css`: 1482 → 1337 Zeilen.

### Hinweis zu CA-005
Der Audit-Befund "zwei parallele Speicherschemata vereinheitlichen" wurde
bei der Umsetzung **als falsch erkannt und zurückgezogen**: Ruhe-Ort
(drei Texte), Gedanken-Waage (zwei Texte) und Mini-Ziel (Text + Bool)
passen nicht in ein einzelnes Ergebnisfeld. Sie hineinzuzwingen hieße,
mehrere Werte als JSON in ein verschlüsseltes Feld zu kodieren - schlechter
lesbar und ohne die feldweise Verschlüsselungs-Granularität aus
CLAUDE.md §3. Stattdessen als Konvention festgehalten: neue Typen mit
*einer* Antwort nutzen das generische Schema, mehrteilige bekommen eigene
Spalten. Details in `tasks/codebase-audit/README.md`.

## [0.1.41] - 2026-08-04

### Fixed
- **PSM-Ansicht zeigte freigegebene Tage unvollständig.** Die in 0.1.40
  ergänzten Übungstypen speichern ihre Antworten in den generischen
  `*_uebung_ergebnis`-Feldern - `wohlbefinden/teilnehmer_ansicht.html`
  rendert diese aber nicht mit, sodass ein bewusst freigegebener Tag bei
  der psychosozialen Mitarbeit ohne die Antwort zu Absichts-Karte,
  Tagesmotto oder Abend-Karte ankam. Beide Ergebnisfelder und ein Hinweis
  auf hinterlegte Fotos ergänzt.
- Totes Formularfeld `grounding_erledigt_signal` aus dem Erdungs-Template
  entfernt (wurde vom Router nie gelesen; die Erdung wertet die fünf
  `grounding_N`-Felder aus).

### Added
- `tasks/codebase-audit/README.md`: vollständiges Codebase-Audit mit zehn
  priorisierten Befunden (CA-001 bis CA-010) und Umsetzungsreihenfolge.
  Kernbefunde: zentrale Zugriffsschicht `access.py` und die
  Hard-Delete-Pfade sind ungetestet, Audit-Logs fehlen bei
  Wochenbericht-Zugriff und Datenexport. **Keine** Autorisierungslücke
  gefunden (alle 103 Routen geprüft).

## [0.1.40] - 2026-08-04

### Added
- **Übungspools auf je 10 Typen erweitert (20 insgesamt)** - Ziel: zwei
  Übungen pro Tag (morgens + abends) x fünf Werktage = zehn pro Woche,
  damit sich in **zwei Arbeitswochen keine Übung wiederholt**.
  Neu morgens: **Absichts-Karte** (Karte umdrehen), **Tagesmotto**
  (Wort-Rad mit ganzen Sätzen), **Klarheits-Kompass** (Kopf/Herz/Bauch/
  Hände als Zonen mit Halten-Timer), **Gestern loslassen** (Wisch-Karte,
  wird nirgends gespeichert), **Motivations-Foto** (Foto-Rahmen).
  Neu abends: **Sternenhimmel ausmalen** (Leinwand mit Sterne-Vorlage auf
  Nachtblau), **Abend-Karte** (Karte umdrehen), **Kerzen anzünden**
  (drei Kerzen als Zonen mit Halten-Timer).
  Alle acht bauen auf den bestehenden Primitiven aus VB-018 auf - kein
  neues Interaktionsmuster, nur neue Inhalte/Grafiken.

### Changed
- **Rotation garantiert jetzt tatsächlich zwei wiederholungsfreie Wochen.**
  Bisher wurde pro Kalenderwoche neu gemischt, sodass Woche 2 dieselben
  Übungen wie Woche 1 ziehen konnte. Neu läuft die Rotation in Blöcken von
  zehn *Werktagen* (`app/core/tagesuebungen.py:_rotations_index`);
  Wochenenden verbrauchen bewusst keinen Rotationsplatz, sondern zeigen
  weiter die Freitags-Übung - sonst wäre das Ziel bei 14 Kalendertagen und
  10 Pool-Einträgen rechnerisch unmöglich. Per Test über viele
  Teilnehmer:innen und Zeiträume abgesichert.
- **Generische Ergebnisfelder statt einer Spalte pro Übungstyp.** Die acht
  neuen Typen teilen sich `morgen_uebung_*`/`abend_uebung_*`
  (erledigt_am/frage/ergebnis/datei_pfad, Migration `c4d5e6f7a8b9`) -
  ohne dieses Schema wären 11 weitere Spalten nötig gewesen. Die drei
  wiederverwendbaren JS-Widgets (Zonen, Wort-Rad, Mal-Leinwand) lesen
  ihren Feldnamen jetzt aus einem `data-`Attribut, statt ihn fest zu
  verdrahten.
- Neue Übungs-Uploads sind in beiden Löschpfaden berücksichtigt
  (Tag löschen + kompletter Konto-Hard-Delete), damit keine verwaisten
  verschlüsselten Dateien zurückbleiben.

## [0.1.39] - 2026-08-04

### Changed
- **VB-018 umgesetzt: komplettes Rework der Mein-Tag-Minispiele.** Die
  10 Übungstypen aus VB-006 waren größtenteils Formularfelder mit
  thematischem Label statt eigenständiger Interaktionen (Nutzer:
  "aktuell eine Katastrophe"). Ersetzt durch eine kleine Zahl polierter,
  wiederverwendbarer Interaktions-Primitive:
  - **Körper-Scan**: schematische Körpersilhouette (SVG) statt
    Button-Liste - Regionen leuchten beim Antippen auf, mit Halten-Timer.
  - **Ausmal-Mandala**: echtes Canvas-Übermalen eines Mandala-Führungs-
    musters (5-Farben-Palette) statt 7 anklickbarer Kreissegmente.
  - **Stärken-Karte, Ruhe-Ort-Visualisierung, Mini-Ziel des Tages**: neues
    Primitiv "Karte umdrehen" (echte CSS-3D-Flip-Animation) statt
    `<details>`-Akkordeon bzw. nackter Textfelder.
  - **Gedanken-Waage**: sichtbares Zwei-Schalen-Element, das sich neigt,
    sobald beide Seiten Text enthalten - macht die Metapher tatsächlich
    sichtbar statt nur im Namen.
  - **Sorgen loslassen, 5-4-3-2-1-Erdung**: neues Primitiv "Karte
    wegwischen" mit echter Pointer-Drag-Wischgeste (plus Tastatur-/
    Klick-Alternative); Erdung besteht jetzt aus 5 nacheinander
    erscheinenden Karten (ein Sinn pro Karte) statt 5 Checkboxen.
  - **Ein Wort für heute**: "Wort-Rad" - das gewählte Wort hebt sich
    sichtbar hervor statt einer starren Button-Wolke.
  - **Dankbarkeits-Foto-Moment**: Polaroid-Rahmen-Optik mit sofortiger
    Bildvorschau nach Auswahl statt eines nackten Datei-Inputs.
  - Atemübung und Zeichnung (bereits gute Primitive) unverändert.
  - Bestehendes Datenmodell (VB-006) unverändert - nur die
    Präsentationsschicht wurde ausgetauscht.
  - Funktional per Browser-JS gegen alle 8 überarbeiteten Übungstypen
    verifiziert (Karte-Flip, Waage-Neigung, Wort-Auswahl, 5er-Wisch-
    Stapel mit korrekten Einzelfeldern, Sorgen-Karte-Leerung).

### Fixed
- Ungenutzten `date`-Import in `app/main.py` entfernt (ruff F401).
- Veraltete Testassertion auf "Schnellzugriff" entfernt (Dashboard-
  Struktur hat sich seither geändert, Test war nicht mehr aussagekräftig).

## [0.1.38] - 2026-08-04

### Changed
- **Handlungsfeld-Team: Mitgliederliste getrennt** - "Mitglieder"-Tab zeigte
  bisher alle Teilnehmer:innen der Abteilung ungetrennt in einer Tabelle
  (Mitglieder und Nicht-Mitglieder nur am Button-Text "Entfernen"/
  "Hinzufügen" unterscheidbar). Jetzt zwei getrennte Abschnitte
  "Mitglieder des Handlungsfelds" und "Weitere Teilnehmer:innen der
  Abteilung" (mit eigener Suche), jeweils mit Anzahl im Titel.
- **"Meine Teilnehmer:innen" zeigt nur noch persönlich zugeordnete
  Teilnehmer:innen** - bisher zusätzlich alle Mitglieder eines geleiteten
  Handlungsfelds, auch ohne persönliche Zuordnung (`BerufstrainerZuordnung`)
  - das machte die Liste größer als die tatsächliche persönliche Betreuung.
  Handlungsfeld-Zugehörigkeit bleibt als Info-Spalte sichtbar, bestimmt
  aber nicht mehr, wer in der Liste auftaucht.

### Added
- **Kanban-Board-Ansicht aus Teilnehmer:innen-Perspektive** - der
  "Kanban-Board"-Link in "Meine Teilnehmer:innen" öffnet jetzt eine Liste
  aller Boards, die die/der jeweilige Teilnehmer:in selbst sehen kann
  (öffentliche Team-Boards über Arbeitsgruppen-, Handlungsfeld- oder
  individuelle Freigabe, plus das eigene Personen-Board) - nicht mehr nur
  einen Direktsprung zum persönlichen Board. Team-Boards aus
  Handlungsfeldern, die die/der betrachtende Trainer:in nicht selbst
  leitet, sind darüber jetzt einsehbar (rein lesend, eigenes Template ohne
  Formulare) - vorher gar nicht erreichbar. Private Karten des
  Personen-Boards bleiben weiterhin nach den bestehenden Regeln gefiltert
  (Sichtbarkeit an die/den tatsächlich betrachtende:n Trainer:in gebunden,
  nicht an die/den Teilnehmer:in "simuliert").
  - Neue Routen `GET /kanban/teilnehmer/{teilnehmer_id}/boards` und
    `GET /kanban/teilnehmer/{teilnehmer_id}/boards/{board_id}`, beide nur
    für persönlich zugeordnete Berufstrainer:innen.
  - `GET /kanban/boards/personen/{teilnehmer_id}` (Direktsprung-Route)
    entfernt, durch die neue Listenansicht ersetzt.
  - Nebenbei gehärtet: die Freigabe-Verwaltung eines Team-Boards
    (`board_detail`) prüft jetzt explizit `kann_board_verwalten` statt nur
    "ist Berufstrainer:in" - bisher indirekt korrekt, weil
    `require_kanban_access` Team-Boards für Berufstrainer:innen ohnehin nur
    der Handlungsfeld-Leitung erlaubte, jetzt nicht mehr auf diese
    Zufälligkeit angewiesen.

## [0.1.37] - 2026-08-04

Code-Review von `scandy-stack.sh` (unabhängig von den vorherigen Live-Test-
Fixes) - Robustheits-/Konsistenzlücken gefunden und behoben, die ein
einzelner erfolgreicher Testlauf nicht zwangsläufig aufdeckt.

### Fixed
- **Fehlerbehandlung im Authentik-Verdrahtungsblock war lückenhaft** -
  mehrere riskante Schritte (Zertifikatserzeugung, Django-Shell-Aufruf
  fürs Brand-Zertifikat, Dienst-Neustart, `pct push`/`pct pull`,
  `update-ca-certificates`) waren nicht gegen `set -e` abgesichert:
  schlug einer davon fehl, brach wegen `set -Eeuo pipefail` das gesamte
  Skript ab, auch die Abschluss-Zusammenfassung mit den Container-IDs
  wurde dann nie angezeigt - obwohl die App-Installationen selbst längst
  erfolgreich durchgelaufen waren. `provision_authentik_certificate()`
  und `wire_app_oidc()` sind jetzt eigene Funktionen, per `if
  function; then`/`function || ...` aufgerufen (bash wertet das nicht als
  `errexit`-Abbruch), sodass ein Fehlschlag nur den jeweiligen Teilschritt
  überspringt statt das ganze Skript zu beenden - und ein Fehlschlag bei
  einer App (z. B. Scandy-Lite) die bereits erfolgreiche Verdrahtung einer
  anderen (z. B. ScandyPro) nicht mehr verschweigt.
- **Zertifikatsvertrauen konnte nach einem Update stillschweigend wieder
  verschwinden** - die Authentik-CA wurde nur ins `certifi`-Bundle des
  App-venv angehängt; ein "Aktualisieren"-Lauf (`pip install -r
  requirements.txt`) kann dabei `certifi` selbst aktualisieren und
  `cacert.pem` komplett ersetzen, wodurch der Anhang verloren geht und SSO
  nach einem ganz normalen Update wieder mit dem TLS-Vertrauensfehler aus
  0.1.34 bricht. `scandypro.sh`'s Aktualisieren-Pfad hängt jetzt bei jedem
  Update alle CA-Zertifikate aus dem OS-weiten, von `pip` unabhängigen
  Ordner (`/usr/local/share/ca-certificates/`) erneut an.
- **`sort` statt `sort -n` bei der VMID-Erkennung** - lexikografische
  Sortierung könnte bei wiederverwendeten (kleineren) Container-IDs die
  falsche als "neu erstellt" erkennen; jetzt numerisch sortiert.
- **Automatisierter Blueprint nutzte `implicit-consent`, die manuelle
  Anleitung `explicit-consent`** - unbeabsichtigte Abweichung zwischen
  beiden Wegen. Automatisierung jetzt ebenfalls `explicit-consent`, damit
  Nutzer:innen beim ersten SSO-Login bewusst einen Bestätigungsdialog
  sehen statt stillschweigend durchgeleitet zu werden.

### Changed
- `OIDC_PROVIDER_NAME=Authentik` wird jetzt automatisch mit eingetragen
  (Login-Button zeigt "Mit Authentik anmelden" statt generisch "Mit SSO
  anmelden").
- Nach dem Eintragen der `OIDC_*`-Werte werden jetzt beide Dienste einer
  App neu gestartet (`${service}` und `${service}-https`), nicht nur der
  HTTPS-Dienst - beide lesen dieselbe `.env`.
- README.md "Proxmox-Stack" aktualisiert: veraltete Formulierung
  "experimentell, nicht gegen eine echte Authentik-Instanz verifiziert"
  entfernt (war durch die Live-Tests in 0.1.34-0.1.36 überholt), neuer
  Hinweis zur IP-Stabilität (DHCP-Adressen werden fest in Redirect-URI/
  `OIDC_ISSUER` eingetragen - feste IPs/DHCP-Reservierungen empfohlen).
  Skript gibt denselben Hinweis jetzt auch am Ende der Installation aus.

## [0.1.36] - 2026-08-04

### Fixed
- **OAuth2Provider-Blueprint fehlten `property_mappings`** - ohne sie
  bleiben `email`/`name`-Claims im ID-Token leer, obwohl
  `scope=openid email profile` angefragt wird. Beide Apps legen bei
  SSO-Erstlogin dadurch einen Platzhalter-Account an (z.B.
  `sso-<sub-präfix>` bei Scandy-Lite) statt echten Namen/E-Mail zu
  übernehmen. `scandy-stack.sh` verknüpft den Provider jetzt mit den
  Standard-Scope-Mappings (`openid`, `email`, `profile`).
  **Hinweis:** bereits angelegte Platzhalter-Accounts aktualisieren sich
  dadurch nicht rückwirkend (Zuordnung läuft über die stabile
  `external_id`/`sub`, nicht über Name/E-Mail) - Name manuell in der
  Benutzerverwaltung anpassen oder den Account löschen und neu per SSO
  anmelden.

## [0.1.35] - 2026-08-04

Echter Browser-Login-Test (nicht nur curl-Redirect-Check) deckte den
letzten Blocker auf: Klick auf "Mit SSO anmelden" scheiterte bei ScandyPro
mit Internal Server Error, bei Scandy-Lite mit "SSO-Anmeldung
fehlgeschlagen".

### Fixed
- **OAuth2Provider-Blueprint fehlte `grant_types`** - ohne dieses Feld
  bleibt es in der installierten Authentik-Version leer, wodurch Authentik
  *jede* Autorisierungsanfrage mit `Invalid grant_type for provider` /
  `The request is otherwise malformed` ablehnt (Authentiks eigenes
  Server-Log zeigte die genaue Ursache, das Frontend nur den generischen
  Fehler). `scandy-stack.sh` setzt jetzt `grant_types: [authorization_code,
  refresh_token]` im Blueprint; `SSO_AUTHENTIK.md` ergänzt um den Hinweis
  für die manuelle UI-Einrichtung.
- Live end-to-end verifiziert: der SSO-Link landet bei ScandyPro und
  Scandy-Lite jetzt korrekt auf Authentiks echter Login-Seite (Status 200),
  nicht mehr auf einer Fehlerseite.
- Nebenbei behoben: `scandypro-https.service` lief nach einer manuellen
  Debug-Session nicht mehr über systemd (war nur auf 127.0.0.1 gebunden,
  von außen nicht erreichbar) - sauber neu gestartet.

## [0.1.34] - 2026-08-03

SSO gegen den echten Testaufbau aus 0.1.33 bis zum funktionierenden
Ende-zu-Ende-Login durchgetestet - dabei zwei weitere, tiefer liegende
TLS-Probleme gefunden und in `scandy-stack.sh` automatisiert behoben (nicht
nur dokumentiert):

### Fixed
- **Authentiks generisches Zertifikat hat keinen zur Server-IP passenden
  SAN-Eintrag** - `scandy-stack.sh` erzeugt jetzt automatisch ein eigenes
  Zertifikat mit korrektem SAN und setzt es als Web-Zertifikat der
  Default-Brand, sobald Authentik zusammen mit mindestens einer App
  installiert wird.
- **CA-Vertrauen allein reicht nicht** - Python `httpx`/`authlib` (von
  ScandyPro/Scandy-Lite für den OIDC-Discovery-Aufruf genutzt) verwendet
  standardmäßig das mitgelieferte `certifi`-Bundle statt des
  OS-Zertifikatsspeichers. `scandy-stack.sh` trägt Authentiks CA jetzt an
  beiden Stellen ein (OS-Store per `update-ca-certificates` UND
  `certifi/cacert.pem` im jeweiligen App-venv).
- Live end-to-end verifiziert: `/auth/oidc/login` liefert bei ScandyPro
  **und** Scandy-Lite jetzt einen korrekten 302-Redirect zu Authentiks
  Autorisierungs-Endpunkt.
- `SSO_AUTHENTIK.md` "Voraussetzungen" um beide Fixes (inkl. manueller
  Befehle für bereits bestehende Installationen) ergänzt.

## [0.1.33] - 2026-08-03

Live-Test von `scandy-stack.sh` gegen einen echten Proxmox-Host (alle drei
Komponenten, inkl. Authentik-Community-Build und OIDC-Blueprint-
Automatisierung) - dabei gefundene und behobene Fehler:

### Fixed
- **`gnupg` fehlte im frischen Debian-13-Template**, wurde aber vom
  gemeinsamen `setup_postgresql`-Helper für den APT-Signaturschlüssel
  gebraucht (`Failed to install GPG key for pgdg`) -
  `proxmox/install/scandypro-install.sh` installiert es jetzt vorab.
- **Falsche URLs in `scandy-stack.sh`**: Scandy-Lite nutzt den Branch
  `master`, nicht `main`; der Authentik-Community-Skript-Link
  (`community-scripts.github.io/ProxmoxVE/ct/authentik.sh`) existiert
  nicht - korrekt ist `raw.githubusercontent.com/community-scripts/
  ProxmoxVE/main/ct/authentik.sh` (auch in `SSO_AUTHENTIK.md` korrigiert).

### Verified
- ScandyPro und Scandy-Lite installieren sich über `scandy-stack.sh` von
  Grund auf fehlerfrei (frischer Proxmox-Host, keine vorherigen
  Container) und sind danach sofort per HTTPS erreichbar.
- Authentik-Installation über das Community-Skript läuft vollständig durch
  (native Rust/Go/xmlsec-Kompilierung, ~30 Min.).
- Die experimentelle OIDC-Automatisierung (`ak apply_blueprint`) legt
  Provider + Application in Authentik korrekt an und trägt die Werte
  richtig in die App-`.env` ein - **aber** der eigentliche SSO-Handshake
  scheitert zusätzlich an einem unabhängigen TLS-Vertrauensproblem
  zwischen zwei selbstsignierten Diensten (Authentiks generisches
  Default-Zertifikat hat keinen zur Server-IP passenden SAN-Eintrag) -
  siehe `SSO_AUTHENTIK.md` "Voraussetzungen" für Ursache und Workaround.
  Das Blueprint-YAML-Schema selbst musste dabei an die tatsächliche
  Authentik-API angepasst werden (`redirect_uris` als Liste von Objekten
  statt String, `invalidation_flow` zusätzlich erforderlich).

## [0.1.32] - 2026-08-03

### Added
- **`proxmox/ct/scandy-stack.sh`**: EIN Einstiegspunkt für den ganzen
  Stack - Mehrfachauswahl-Menü (ScandyPro/Scandy-Lite/Authentik, jede
  Kombination), installiert die gewählten Komponenten nacheinander durch
  Aufruf der bereits vorhandenen Einzel-Installer (keine duplizierte
  Container-Erstellungs-Logik). Bei Authentik + mind. einer App zusammen:
  experimenteller Zusatzschritt, der versucht, automatisch einen
  OAuth2/OIDC-Provider + Application je App anzulegen (`ak
  apply_blueprint`) und `OIDC_*` direkt in deren `.env` einzutragen -
  nicht gegen eine echte Authentik-Instanz verifiziert, fällt bei Fehlschlag
  auf die manuelle Anleitung in `SSO_AUTHENTIK.md` Teil B zurück, ohne die
  bereits abgeschlossene Installation zu gefährden.

## [0.1.31] - 2026-08-03

Fehlersuche/Fixes waehrend der Erstinbetriebnahme auf einem frischen
Proxmox-Host (LXC-Installation, nicht Docker Compose).

### Fixed
- **`auth_source` fehlte der Postgres-ENUM-Typ** - Migration
  `e3f4a5b6c7d8` legte die Spalte als reinen `sa.String()` an, waehrend
  das `User`-Model einen nativen Enum erwartet (analog `role`/`roleenum`
  aus der initialen Migration). Ohne den Typ scheiterte das
  Admin-Seeding beim allerersten App-Start mit
  `UndefinedObjectError: type "authsource" does not exist` -
  uvicorn beendete sich dadurch dauerhaft mit Exit-Code 3, ohne
  sichtbaren Traceback im systemd-Journal (gepuffertes stdout ging beim
  harten Prozessende verloren). Neue Migration
  `f1a2b3c4d5e6_authsource_enum_type.py` legt den Typ nach und
  konvertiert die Spalte.

### Changed
- **Proxmox-LXC-Installer auf "ausschließlich HTTPS" umgestellt** -
  `proxmox/ct/scandypro.sh`/`proxmox/install/scandypro-install.sh` legen
  jetzt wie Scandy-Lite zwei systemd-Dienste an: `scandypro` (Klartext-
  HTTP, nur `127.0.0.1:8000`, von außen nicht erreichbar) und
  `scandypro-https` (selbstsigniertes Zertifikat, `0.0.0.0:8443`).
  Debian-Template von 12 auf 13 ("Trixie") angehoben.
- **README.md**: neuer Abschnitt "Proxmox-Stack: beliebige Kombination
  installieren" - stellt klar, dass ScandyPro/Scandy-Lite/Authentik
  bereits unabhängige Installer-Skripte haben und jede Kombination
  einfach durch Ausführen der gewünschten Teilmenge entsteht (keine
  gemeinsame Zustandsverwaltung nötig).

## [0.1.30] - 2026-08-03

Nutzer-Feedback zu 0.1.12.

### Changed
- **Per-Element-Toasts in "Mein Tag" wieder entfernt** - vom Nutzer als "zu
  unauffällig" eingestuft; `app/static/js/tagebuch-interaktiv.js` zurück auf
  den Stand vor 0.1.12 (die gemeinsame Toast-Komponente
  `app/static/js/toast.js` bleibt bestehen, wird weiterhin von Kanban
  genutzt).
- **Dashboard-Kachel "Tage ins Tagebuch geschrieben"** zeigt jetzt einen
  bestärkenden Satz statt nur der reinen Zahl - das war die eigentlich
  gewünschte Stelle für positive Verstärkung.

### Planned
- [VB-018](tasks/ganzheitliche-verbesserungen/VB-018.md): kompletter Plan
  für ein Rework der Mein-Tag-Minispiele aus 0.1.10/VB-006 - Diagnose: die
  meisten der 10 neuen Übungstypen sind im Kern Textfelder/Checkboxen mit
  Label, kein eigenständiges Interaktionserlebnis wie Atemübung/Zeichnung.
  Löst eine kleine Zahl wiederverwendbarer Interaktions-Primitive vor
  (Karte umdrehen, Zone mit Halten-Timer auf Körpersilhouette, Waage/
  Slider, Karten wegwischen, Foto-Rahmen, Wort-Rad). Noch nicht umgesetzt.

## [0.1.29] - 2026-08-03

### Added
- **TLS-Produktivbetrieb vorbereitet, zwei Varianten** - README.md neuer
  Abschnitt "TLS (Produktivbetrieb)" mit Schritt-für-Schritt-Anleitung für
  beide, "Bekannte Lücken" verweist jetzt darauf statt die Lücke nur zu
  benennen:
  - **Variante A**: `caddy/Caddyfile.domain-example` - echte Domain mit
    automatischem Let's-Encrypt-Zertifikat.
  - **Variante B**: `caddy/Caddyfile.internal-tls-example` - selbstsigniertes
    Zertifikat (Caddy `tls internal`, port-basiert per IP) für Server, die
    nur intern (LAN/VPN) erreichbar sind und keine Domain/öffentliche
    Zertifikatsausstellung haben; neue `APP_HTTPS_PORT`-Variable
    (`.env.example`). Browser zeigen dabei einmalig pro Gerät eine
    Zertifikatswarnung, funktioniert aber genauso für SSO/Authentik, da
    dieses nur `https://` in der Redirect-URI prüft, nicht die
    Vertrauenswürdigkeit des Zertifikats.
  - `SESSION_COOKIE_SECURE`-Setting ergänzt (`app/core/config.py`,
    `app/main.py`) für das Secure-Flag am Session-Cookie, unabhängig von
    der gewählten Variante. Standard-HTTP-Setup bleibt unverändert (Default
    weiterhin unverschlüsselt, nur für lokale Bewertung). `SSO_AUTHENTIK.md`
    verweist auf dieselbe Anleitung statt separat gepflegter
    Caddyfile-Vorlagen.

## [0.1.28] - 2026-08-03

### Added
- **Optionales Single Sign-On über OIDC** (z.B. Authentik) - Vorbereitung
  für zentral gesteuerte Nutzer:innen über mehrere Apps hinweg (siehe
  Vergleich mit dem Schwestermodul Scandy-Lite, das dieselbe Anbindung
  bereits produktiv nutzt). Ohne Konfiguration (`OIDC_ISSUER`/
  `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` in der `.env`) verhält sich die App
  exakt wie zuvor - lokales E-Mail/Passwort-Login bleibt in jedem Fall
  verfügbar.
  - `app/core/oidc.py` (Authlib-Client, Zuordnung Login → Account),
    `app/routers/oidc.py` (`/auth/oidc/login`, `/auth/oidc/callback`).
  - `User` um `auth_source` (`local`/`sso`) und `external_id` (OIDC `sub`)
    erweitert; `password_hash` und `role` sind jetzt nullable (Migration
    `e3f4a5b6c7d8`).
  - **Bewusst keine automatische Rollenübernahme vom Identity-Provider**
    (CLAUDE.md §8 "Rollen ... niemals implizit"): ein per SSO neu
    erkannter Account wird immer inaktiv und ohne Rolle angelegt und
    erscheint in der Benutzerverwaltung als eigene Gruppe "Wartet auf
    Freischaltung" - eine Einrichtungs-Admin muss Rolle und Abteilung
    bewusst zuweisen und den Account aktivieren, bevor ein Login möglich
    ist. Erkennt eine SSO-Anmeldung eine bereits vorhandene E-Mail, wird
    der bestehende lokale Account verknüpft statt dupliziert.
  - Konto-Seite erlaubt SSO-Accounts, zusätzlich ein lokales Passwort als
    Alternative einzurichten (ohne "aktuelles Passwort", da noch keins
    existiert).
- **[SSO_AUTHENTIK.md](SSO_AUTHENTIK.md)**: vollständige Installations- und
  Anbindungsanleitung - eigene Authentik-Instanz aufsetzen, wahlweise als
  natives LXC über das Community-Skript (passt zum bestehenden Muster
  `scandypro.sh`/`scandy-lite.sh`) oder per Docker Compose (offizieller
  Authentik-Weg), danach Provider/Application anlegen, ScandyPro
  konfigurieren, End-to-End-Testablauf, Fehlerbehebungstabelle.
  `.env.example` um die vier `OIDC_*`-Variablen ergänzt, README.md verweist
  darauf.

## [0.1.27] - 2026-08-03

### Added
- **Favicon ergänzt** - SVG-Icon im Markenlook (Brand-Teal-Quadrat mit dem
  "//" aus dem Logo-Schriftzug), bisher fehlte jeder Favicon-Link.

## [0.1.26] - 2026-08-03

### Changed
- **Dashboard: Kontakt zu Berufstrainer:in/PSM** - "Deine Rolle: ..." entfernt
  (redundant zur Topnav). Zuständige Berufstrainer:in/PSM werden jetzt als
  Kontakt-Karten mit Avatar dargestellt, inkl. direkter "E-Mail"- und
  "Anrufen"-Aktion (`mailto:`/`tel:`) statt reinem Fließtext-Link.
- **Dashboard: "Schnellzugriff"-Kacheln entfernt** - dupliziierten für
  Teilnehmer:innen 1:1 die Topnav-Links (Projekte, Wochenberichte, Mein Tag,
  Bewerbungen, Meine Freigaben) ohne eigenen Mehrwert.
- **Dashboard: "Deine Woche im Rückblick"-Kacheln sind jetzt anklickbare
  Links** statt reiner Statistik-Anzeige, und zeigen einen persönlichen,
  positiv formulierten Bezug zur eigenen Nutzung statt nur einer Zahl:
  die Kanban-Kachel verlinkt direkt auf die zuletzt bewegte Karte (oder,
  wenn diese Woche noch nichts bewegt wurde, auf eine anstehende Aufgabe
  als Vorschlag), die Tagebuch-Kachel zeigt das zuletzt eingetragene
  "Wort des Tages", die Bewerbungs-Kachel die zuletzt aktualisierte
  Bewerbung.

## [0.1.25] - 2026-08-03

Fixes aus einem gezielten Chrome-Klickthrough über alle vier Rollen
(Teilnehmer:in, Berufstrainer:in, Psychosoziale Mitarbeiter:in,
Einrichtungs-Admin).

### Changed
- **Benutzerverwaltung aufgeräumt** - "Neuer Account" ist jetzt ein eigener
  Tab statt ganz oben auf der Seite zu stehen und vom eigentlichen Zweck
  (bestehende Accounts finden/bearbeiten) abzulenken. Accounts-Liste ist
  nach Rolle gruppiert (Teilnehmer:in/Berufstrainer:in/Psychosoziale
  Mitarbeiter:in/Einrichtungs-Admin) mit je eigener Such-/Filterbox statt
  einer einzigen ~150-Zeilen-Tabelle mit redundanter Rollen-Spalte.

### Fixed
- **Verwaiste Kartenzuweisungen zeigten "?" statt Namen** - wenn eine
  Person eine Arbeitsgruppe/ein Handlungsfeld verlässt, das einem Board
  Zugriff gewährt, blieb ihre bestehende Kartenzuweisung bestehen, aber
  ihr Name/Avatar wurde nur noch als "?" angezeigt (weder auf der Karte
  noch im "Entfernen"-Formular erkennbar). `_board_kontext` löst jetzt
  zusätzlich alle referenzierten, aber nicht mehr board-berechtigten
  Personen separat auf (`anzeige_personen`) und zeigt ihren echten
  Namen mit dem Hinweis "(nicht mehr im Team)" an - ohne sie erneut
  zuweisbar zu machen.
- **Doppelte Handlungsfeld-Namen ohne Prüfung möglich** - `POST
  /admin/handlungsfelder` und `.../umbenennen` prüfen jetzt auf
  Namensgleichheit (case-insensitive) innerhalb derselben Abteilung und
  lehnen mit Fehlermeldung ab, statt stillschweigend ein zweites
  gleichnamiges Handlungsfeld anzulegen (das in jedem Dropdown, z.B.
  bei "Neues Board", nicht mehr unterscheidbar gewesen wäre). Gleiche
  Prüfung jetzt auch für `POST /admin/abteilungen`.
- **Namensgleiche Berufstrainer:innen/PSM in Zuordnungslisten nicht
  unterscheidbar** - "Zuordnungen Berufstrainer:innen" und "Zuordnungen
  Psychosoziale Mitarbeiter:innen" zeigen jetzt die E-Mail-Adresse
  neben dem Namen (Akkordeon-Kopfzeile und alle betroffenen
  Auswahllisten, inkl. Handlungsfeld-Leitung in
  "Abteilungen & Handlungsfelder").

### Changed
- **Redundante Kartenbeschreibung entfernt** - Beschreibungstext wurde
  auf Kanban-Karten doppelt angezeigt (einmal statisch, einmal im
  editierbaren Textfeld direkt darunter). Die statische Anzeige wurde
  entfernt.
- **"Zuweisen"-UI auf persönlichen Boards ausgeblendet** - auf
  Ein-Personen-Boards (`BoardTyp.person`) ergab die Möglichkeit, sich
  selbst zuzuweisen, keinen Sinn und wurde entfernt (Karten, neue
  Karte anlegen, Unteraufgaben).
- **Unterstützungsanfrage lässt sich zurückziehen** - Teilnehmer:innen
  können eine versehentlich abgeschickte, noch nicht von der PSM
  gesehene Anfrage jetzt selbst zurückziehen (`POST
  /wohlbefinden/unterstuetzung-anfragen/{id}/zurueckziehen`).
- **Erste Spalte bleibt beim horizontalen Scrollen sichtbar** - in
  breiten Tabellen mit `.table-scroll` (z.B. Benutzerverwaltung mit
  ~150 Accounts) bleibt die Name-Spalte jetzt via `position: sticky`
  stehen, damit der Zeilenbezug beim Scrollen nicht verloren geht.

## [0.1.24] - 2026-08-03

### Added
- **Abgegebene Wochenberichte lassen sich zurückziehen** und wieder
  bearbeiten (`POST /wochenberichte/{id}/zurueckziehen`) - die digitale
  Abgabe war bisher endgültig, obwohl Wochenberichte ohnehin ausgedruckt
  und unterschrieben werden müssen und die digitale Version damit keine
  verbindliche Festlegung sein muss. Zurückgezogene Berichte werden für
  die Handlungsfeld-Leitung wieder unsichtbar (Sichtbarkeit bleibt an
  `status=abgegeben` gekoppelt), bis erneut abgegeben wird.

## [0.1.23] - 2026-08-03

### Fixed
- **Absage-/Zusage-Rückmeldung erschien nicht beim Verschieben per
  Drag&Drop** - nur beim Verschieben über ein Formular (Server-Redirect
  mit `?feedback=...`). `bewerbungen-board.js` machte nach dem
  Drag&Drop-Request ein reines `location.reload()`, das lud die aktuelle
  URL ohne die Feedback-Parameter neu. Jetzt folgt es der von `fetch()`
  bereits aufgelösten Redirect-Ziel-URL (`antwort.url`).

### Removed
- **"Verschieben"-Auswahlfeld** in der Bewerbungskarte entfernt - auf
  ausdrücklichen Wunsch, da Drag&Drop dieselbe Funktion abdeckt.
  Bewusster Kompromiss: das Feld war zugleich die einzige
  Tastatur-Alternative zum Ziehen (analog zum echten Kanban-Board,
  siehe UI-003 in `tasks/uiux-audit/`) - Bewerbungen lassen sich damit
  aktuell nur per Maus/Touch zwischen Spalten verschieben.

## [0.1.22] - 2026-08-03

### Added
- **Bewerbungen jetzt als Kanban-artiges Board**: "Laufende"/"Abgeschlossene
  Bewerbungen" ersetzt durch einen einzigen "Bewerbungen"-Tab mit einer
  Spalte je Status (Entwurf, Versendet, Rückmeldung offen, Eingeladen,
  Abgesagt, Zugesagt) - jede Bewerbung ist ein per Drag&Drop verschiebbares
  Workitem, mit derselben Tastatur-Alternative wie beim echten Kanban-Board
  ("Verschieben"-Select). Wiederverwendet dieselben CSS-Klassen wie
  `app/templates/kanban/_spalten.html` für ein konsistentes Erscheinungsbild;
  neues, schlankes `app/static/js/bewerbungen-board.js` (kein
  Kartenreihenfolge-Tracking nötig, anders als bei Kanban).
- **Notizen sind jetzt ein wachsender Verlauf statt eines einzelnen
  Freitextfelds**: neues Modell `BewerbungsNotiz` (mehrere Einträge pro
  Bewerbung, mit Zeitstempel, einzeln löschbar) ersetzt
  `Bewerbung.notizen` (Migration `d1e2f3a4b5c6`, bestehende Werte wurden
  als erster Verlaufs-Eintrag übernommen). Jede Karte hat jetzt einen
  eigenen "Notizen"-Bereich zum Anhängen (z. B. "Telefonat geführt",
  "Zusage laut Anruf").
- Statuswechsel per Drag&Drop/Select ändert bewusst *nur* den Status
  (neue Route `POST /bewerbungen/{id}/verschieben`) - Termindaten bleiben
  dabei unangetastet; das bestehende "Termin bearbeiten"-Formular deckt
  weiterhin beides zusammen ab, wenn gewünscht.

## [0.1.21] - 2026-08-03

### Changed
- **Bewerbungs-Karte komplett neu strukturiert** - der "Aktualisieren"-
  Button für den Status stand bisher mitten zwischen vier Feldern in einer
  Zeile. Jetzt: Titel + Status-Chip klar oben, eine Meta-Zeile mit
  Bewerbungs-/Termindatum, danach zwei klar betitelte, aufklappbare
  Abschnitte ("Status & Termin bearbeiten" offen, "Unterlagen"
  eingeklappt mit Anzahl-Badge) mit dem Speichern-Button jeweils am Ende
  der zugehörigen Felder statt mittendrin. "Bewerbung löschen" steht jetzt
  sichtbar abgesetzt am Kartenende.

### Fixed
- **Bewerbungsstatus wurde als roher Enum-Slug angezeigt** statt in
  lesbarem Deutsch - `rueckmeldung_offen` erschien wortwörtlich (mit
  Unterstrich, ohne Umlaut) im Status-Dropdown und in Status-Chips.
  Neuer Filter `bewerbungsstatus` (analog `rollenname`,
  `app/core/templating.py`) überall dort ergänzt, wo der Status angezeigt
  wird (Bewerbungsübersicht, "Worauf du noch wartest", Trainer-Ansicht).

## [0.1.20] - 2026-08-03

### Changed
- **Bewerbungs-Statuswechsel** erlaubt jetzt direkt im selben Formular,
  auch Datum/Uhrzeit/Ort des nächsten Termins anzupassen (z. B. neuer
  Gesprächstermin bei Wechsel zu "eingeladen") - vorher waren diese Felder
  nur beim Anlegen setzbar und danach nur als statischer Text sichtbar
  (`app/routers/bewerbungen.py:status_aendern`).

## [0.1.19] - 2026-08-03

### Added
- **Einzelne "Mein Tag"-Einträge gezielt freigeben**, statt nur "Gesamter
  Verlauf" oder "Bis zu einem Datum" (beides teilte immer das komplette
  Tagebuch, nur die Dauer unterschied sich). Neuer Umfang `einzeln` bei
  `WohlbefindenFreigabe` mit `tagebuch_eintrag_id` (analog
  `BewerbungsFreigabe.bewerbung_id`, Migration `c0d1e2f3a4b5`). Jeder Tag
  in "Dein Verlauf" hat jetzt einen eigenen "Nur diesen Tag für ... freigeben"-
  Button. Die PSM-Ansicht (`/wohlbefinden/teilnehmer/{id}`) zeigt bei einer
  reinen Einzeltag-Freigabe wirklich nur die freigegebenen Tage - nicht
  mehr automatisch die letzten zwei Wochen (neue Funktion
  `app/core/access.py:sichtbare_wohlbefinden_tage`, ersetzt die reine
  Ja/Nein-Prüfung von `hat_wohlbefinden_freigabe`).

## [0.1.18] - 2026-08-03

### Added
- **Unterstützungsanfrage**: der "Ich möchte jetzt Unterstützung"-Bereich in
  "Mein Tag" hat jetzt einen echten Button, der - komplett unabhängig von
  Tagebuch-Inhalten - eine bewusste, freiwillige Anfrage an die zuständige
  PSM auslöst (neues Modell `Unterstuetzungsanfrage`,
  `app/models/wohlbefinden.py`, Migration `b9c0d1e2f3a4`). Erscheint auf
  dem PSM-Dashboard mit Zeitpunkt und "Als gesehen markieren" - keine
  automatische Eskalation, kein Status "erledigt" (siehe CLAUDE.md
  Abschnitt 24).
- **Dashboard "Neu geteilt"**: Berufstrainer:innen sehen dort neu erteilte
  Bewerbungsfreigaben, PSM neu erteilte "Mein Tag"-Freigaben (jeweils
  letzte 14 Tage) - direkt auf der Startseite, kein zusätzlicher Klick
  nötig (`app/main.py`, `app/templates/dashboard.html`).

### Changed
- **Wochenberichte (Berufstrainer:in-Ansicht) jetzt nach Teilnehmer:in
  gruppiert** statt einer einzigen flachen Liste aller Berichte aller
  betreuten Personen (bei realistischer Datenmenge mehrere hundert
  Einträge) - ein aufklappbarer Eintrag pro Person, darin die eigenen
  Wochenberichte, analog zu den Admin-Zuordnungsseiten aus [0.1.17].
- Dashboard-Kachel "Projekte" erscheint nur noch für Berufstrainer:innen -
  PSM und Einrichtungs-Admin hatten dort ohnehin nie sichtbare Boards
  (der Nav-Punkt war das bereits, die Dashboard-Kachel war übersehen worden).

### Fixed
- Zwei Teilnehmer:innen-Zuordnungs-Duplikate aus dem letzten Testdaten-
  Top-up bereinigt (14× doppelte PSM-, 10× doppelte Berufstrainer:in-
  Zuordnung) - hätten das Dashboard bzw. "Mein Tag" der betroffenen
  Teilnehmer:innen zum Absturz gebracht (`scalar_one_or_none()` erwartet
  höchstens eine Zuordnung).

## [0.1.17] - 2026-08-03

### Changed
- **Admin-Zuordnungsseiten** (`/admin/psm-zuordnungen`, `/admin/trainer-zuordnungen`)
  navigieren jetzt wie "Projekte": statt einer einzigen, ungruppierten Tabelle
  mit einer Zeile je Zuordnung (bei größeren Einrichtungen schnell mehrere
  hundert Zeilen) gibt es pro Berufstrainer:in/PSM einen aufklappbaren
  Eintrag (`.zuklapp-liste`, analog `admin/abteilungen.html`), der die
  zugeordneten Teilnehmer:innen zeigt - inklusive Entfernen und einem
  Inline-Formular zum Hinzufügen weiterer Teilnehmer:innen direkt in diesem
  Eintrag.
- Menüpunkte einheitlich benannt: "Berufstrainer:innen-Zuordnungen" heißt
  jetzt wie die PSM-Seite "Zuordnungen Berufstrainer:innen" (Verwaltungs-
  Dropdown, Seitentitel, Dashboard-Kachel).

## [0.1.16] - 2026-08-03

### Fixed
- **"⋮"-Verwalten-Menü der Arbeitsgruppen (Handlungsfeld-Team) war praktisch
  unbedienbar**: die Tabelle war (wie andere Verwaltungstabellen) in
  `.table-scroll` (`overflow-x: auto`) gewrappt - das erzwingt laut CSS-Spec
  automatisch auch `overflow-y: auto` auf demselben Element, wodurch das
  `position: absolute` Dropdown-Menü vom Container geclippt wurde und nur
  durch Scrollen in einem winzigen Bereich erreichbar war. Genau das Risiko,
  das bei `admin/abteilungen.html` bereits bewusst vermieden wurde ([0.1.13]) -
  hier beim Bauen der Arbeitsgruppen-Verwaltung übersehen. Wrapper entfernt;
  die Tabelle hat nur drei Spalten und braucht auch auf schmalen Screens
  keinen horizontalen Scroll.

## [0.1.15] - 2026-08-03

### Added
- **Arbeitsgruppen (Handlungsfeld-Team) sind jetzt vollständig verwaltbar**:
  bisher ließen sie sich nur anlegen, nicht mehr umbenennen, nicht löschen
  und nach dem Anlegen keine Mitglieder mehr hinzufügen/entfernen - ein
  Fund aus dem eigenen Testdurchlauf (siehe [0.1.14]), wo eine zu
  Testzwecken angelegte Gruppe sich nicht mehr entfernen ließ. Neue Routen
  `POST /kanban/gruppen/{id}/umbenennen`, `.../mitglieder`,
  `.../mitglieder/{mitglied_id}/entfernen`, `.../loeschen`
  (`app/routers/kanban.py`), neue kaskadierende Löschroutine
  `loesche_teilnehmergruppe_kaskadierend` (`app/core/deletion.py` - entfernt
  auch verwaiste `BoardFreigabe`-Einträge, die genau dieser Gruppe galten).
  UI über dasselbe "⋮"-Verwalten-Muster wie bei Handlungsfeldern in der
  Admin-Verwaltung (`.zeile-verwalten`).

## [0.1.14] - 2026-08-03

Nutzer-Feedback: Navigation/Übersicht für Berufstrainer:innen, PSM und
Einrichtungs-Admin.

### Added
- **"Meine Teilnehmer:innen"** als neue, eigenständige Übersicht für
  Berufstrainer:innen (`/kanban/teilnehmer`) und psychosoziale
  Mitarbeiter:innen (`/wohlbefinden/teilnehmer`), jeweils mit eigenem
  Nav-Eintrag. Löst die bisherige knappe Namensliste auf dem Dashboard ab:
  Trainer:innen sehen jetzt Abteilung, Handlungsfeld-Zugehörigkeit,
  persönliche Zuordnung sowie direkte Links zu Kanban-Board, Wochenbericht
  und (falls freigegeben) Bewerbungen pro Person; PSM sieht Abteilung und
  Freigabe-Status für "Mein Tag" mit Direktlink bei aktiver Freigabe.
  Beide Tabellen durchsuchbar (`table-tools.js`).
- **Stammdaten-Selbstverwaltung** für Berufstrainer:in/PSM/Admin: `/konto`
  hat jetzt ein "Meine Stammdaten"-Formular (Name, E-Mail, Telefon) zusätzlich
  zur bestehenden Passwortänderung - bewusst nicht für Teilnehmer:innen, deren
  Stammdaten weiterhin über die Einrichtungs-Verwaltung laufen
  (`app/routers/auth.py:stammdaten_aendern`).

### Changed
- **"Abteilungen & Handlungsfelder"** (Admin) navigiert jetzt wie
  "Bewerbungen" bei Teilnehmer:innen über die vertikale Tab-Leiste
  (`.seiten-tabs`) statt einer langen Seite - Tabs "Neue Abteilung" und
  "Abteilungen".
- **"Handlungsfeld-Team" komplett neu strukturiert**: nach Auswahl eines
  Handlungsfelds trennen zwei Tabs ("Mitglieder" / "Arbeitsgruppen") jetzt
  klar, was zusammengehört. Behebt nebenbei einen echten Verwirrungs-Bug:
  "Bestehende Arbeitsgruppen" zeigte bisher ausnahmslos die Gruppen
  **aller** geleiteten Handlungsfelder gemischt an, unabhängig von der
  Auswahl oben auf der Seite - jetzt nur noch die des gewählten Feldes.
- Dashboard-Karten für Berufstrainer:in/PSM zeigen nur noch einen Link zur
  jeweiligen neuen Übersichtsseite statt einer eingebetteten Liste
  (`app/main.py`: nicht mehr benötigte Server-Berechnung dafür entfernt).
- Der "Projekte"-Nav-Punkt erscheint nicht mehr für PSM/Admin - beide
  hatten dort ohnehin nie sichtbare Boards, nur eine leere Seite.

## [0.1.13] - 2026-08-03

Fund aus einem ersten realen Klick-Durchlauf durch alle fünf Demo-Rollen
(Playwright, headless Chromium - kein Docker/Postgres-Mangel mehr, siehe
frühere Sandbox-Einschränkungen in dieser Datei).

### Fixed
- **Kritischer Mobile-Bug: "Abmelden"-Button auf schmalen Screens
  unerreichbar.** `.user-chip` (Theme-Toggle, Name+Rolle, Abmelden) in der
  Topnav hatte kein `flex-wrap` und keine Textkürzung - bei Viewport-
  Breiten ≤860px (z.B. iPhone 12/13/14, 390px) brach der Name+Rolle-Text
  auf mehrere Zeilen um und drückte den Abmelden-Button über den rechten
  Bildschirmrand hinaus, nur per horizontalem Scrollen erreichbar. Betraf
  ausnahmslos jede Seite, für alle Rollen. Fix: Name/Rolle + Abmelden
  ziehen jetzt mit in die bereits vorhandene kollabierbare Hamburger-Nav
  (`.topnav-links`) um, nur der Theme-Toggle bleibt als kompakter
  Icon-Button permanent sichtbar (`app/templates/base.html`,
  `app/static/css/style.css`).
- **Benutzerverwaltung (`/admin/benutzer`) sprengte auf Mobile die ganze
  Seite horizontal** (953px statt 390px): die 8-spaltige Tabelle lag
  außerhalb jeder `.card` (die eigenes `overflow-x: auto` mitbringt) und
  damit ohne jeden Scroll-Container. Neue Utility-Klasse `.table-scroll`
  ergänzt, in `admin/benutzer.html` und `admin/trainer_zuordnungen.html`
  um die jeweilige Tabelle gelegt (dort bestätigt kein Aktions-Dropdown
  in einer Tabellenzelle, das durch die Scroll-Clipping riskiert würde -
  bei `admin/abteilungen.html`/`admin/psm_zuordnungen.html` war der
  gemessene Mobile-Overflow nach dem Topnav-Fix bereits vollständig
  verschwunden, dort bewusst nicht zusätzlich gewrappt, um die
  Zeilen-Dropdowns (`.zeile-verwalten-body`, `position: absolute`) nicht
  zu riskieren).
## [0.1.12] - 2026-08-03

### Added
- **Positives Feedback für jedes einzelne Element in "Mein Tag"**, nicht
  nur für den ganzen Tag: ein kurzer, sanfter Toast (rotierender Textpool,
  kein Punktestand) nach Atemübung, Körper-Scan, Erdung, Wort des Tages,
  Stärken-Karte, Zeichnung, Mandala, Ruhe-Ort/Gedanken-Waage/Mini-Ziel-Text
  (beim Verlassen des Feldes), Sorgen loslassen, Dankbarkeits-Foto und den
  Ankreuz-Chips (Pause gemacht, jemandem geholfen, Erfolgserlebnis) - siehe
  `app/static/js/tagebuch-interaktiv.js`.
- Neue gemeinsame Toast-Komponente (`app/static/js/toast.js`), aus dem
  bisher Kanban-spezifischen Toast herausgelöst (`kanban.js` nutzt sie jetzt
  mit) - eine Basis, um dasselbe ruhige Feedback-Vokabular künftig auch in
  anderen Modulen zu verwenden.

## [0.1.11] - 2026-08-03

Nutzer-Feedback zu 0.1.10 umgesetzt.

### Fixed
- **Ausmal-Mandala reagierte nicht auf Klicks**: SVG-Segmente mit
  `fill="none"` zählen laut SVG-Spezifikation nur mit ihrem Rand als
  klickbar, nicht mit der Innenfläche (`pointer-events: visiblePainted`-
  Standardverhalten) - `pointer-events: all` ergänzt.
- **Körper-Scan war eine reine Umbenennung der Atemübung** (gleiches
  "Punkte verbinden"-Widget, ohne inhaltlichen Bezug zum Körper) - komplett
  neu als eigenständiges Widget gebaut: eine Liste von Körperregionen, die
  der Reihe nach antippbar wird, mit sinnvollem Halten-Timer pro Region
  statt einer Linienzeichnung zwischen abstrakten Punkten.

### Changed
- **"Ich möchte jetzt Unterstützung"**: externe Hilfsangebote
  (TelefonSeelsorge, Nummer gegen Kummer) entfernt - stattdessen eigene
  PSM-Kontaktperson plus weitere psychosoziale Mitarbeiter:innen derselben
  Abteilung, jeweils mit Telefonnummer sofern hinterlegt.
- **Kanban-Board-Freigaben** gehen jetzt nicht mehr nur an einzelne
  Arbeitsgruppen, sondern wahlweise an ein ganzes Handlungsfeld oder eine
  einzelne Person (`app/models/kanban.py:BoardFreigabe` erweitert).
- **Wochenberichte (Berufstrainer-Ansicht)** lassen sich jetzt nach
  Teilnehmer:in filtern.
- **Wochenbericht-Kanban-Vorschläge**: schlagen jetzt auch Karten vor, die
  diese Woche auf eine "In Arbeit"-Spalte verschoben wurden (nicht nur bis
  "Erledigt"), plus Karten, die gerade in einer "In Arbeit"-Spalte liegen
  und der Person zugeordnet sind.
- **Benutzerverwaltung**: neues Telefon-Feld für alle Rollen (vor allem für
  Berufstrainer:in/PSM/Admin relevant), in der Benutzertabelle und überall
  dort sichtbar, wo bisher schon Kontakt-E-Mails angezeigt wurden
  (Dashboard, Mein-Tag-Unterstützung-Hinweis).

## [0.1.10] - 2026-08-03

Rest von [tasks/ganzheitliche-verbesserungen/](tasks/ganzheitliche-verbesserungen/README.md)
(VB-007 bis VB-017) umgesetzt - damit ist die gesamte Liste abgearbeitet.

### Fixed
- Upload-Validierung prüft jetzt zusätzlich zur Dateiendung die
  tatsächliche Datei-Signatur (Magic Bytes) für PDF/JPEG/PNG/DOC/DOCX
  (`app/core/uploads.py`).
- Demo-Logins auf der Login-Seite erscheinen nur noch, wenn
  `SEED_DEMO_DATA=true` gesetzt ist.
- Deaktivierte Accounts (siehe unten) werden auch bei bereits laufender
  Session sofort ausgesperrt, nicht erst beim nächsten Login.

### Added
- **Admin: Account-Deaktivierung** als Zwischenstufe zwischen aktiv und
  Löschung (`User.aktiv`), plus Anzeige des letzten Logins
  (`User.letzter_login`) in der Benutzerverwaltung.
- **"Meine Freigaben"**: neue Übersicht der für die eigene(n)
  Teilnehmergruppe(n) freigegebenen Team-Boards; dritte Lösch-Option für
  die persönliche Kanban-Aufgabenliste ergänzt die bestehenden
  Wohlbefinden-/Bewerbungs-Löschungen.
- **Bewerbungen**: Termine können jetzt mit Uhrzeit und Ort erfasst werden,
  erscheinen zusammen mit fälligen Kanban-Karten im Dashboard ("Was steht
  an"); Status-Wechsel zu "abgesagt"/"zugesagt" zeigen eine kurze, sanft
  formulierte Rückmeldung statt stiller Statusänderung.
- **Wochenberichte**: in dieser Woche abgeschlossene Kanban-Karten werden
  als antippbare Vorschläge im "Neuer Wochenbericht"-Formular angeboten
  (übernimmt nichts automatisch).
- **PSM und Einrichtungs-Admin** haben jetzt ebenfalls eine
  Bottom-Tab-Bar für schmale Bildschirme (vorher nur Teilnehmer/
  Berufstrainer).

### Changed
- Kaskadierendes Löschen von Kanban-Boards/-Spalten läuft jetzt über
  `app/core/deletion.py` (vorher inline in `app/routers/kanban.py` dupliziert).
- Wochenbericht-Formularfelder-Zuordnung in einer gemeinsamen Funktion
  statt zweimal ausgeschrieben (`bericht_erstellen`/`bericht_bearbeiten`).

### Verified (kein Code-Änderungsbedarf)
- Kanban-Kartenbewegung ist bereits per Tastatur/Touch bedienbar (natives
  `<select>` als Alternative zum Drag&Drop, seit einem früheren Commit) -
  die ursprüngliche Rechercheannahme dazu war veraltet.

## [0.1.9] - 2026-08-03

Umsetzung der ersten sechs Punkte aus
[tasks/ganzheitliche-verbesserungen/](tasks/ganzheitliche-verbesserungen/README.md)
(Accountverwaltung- und Mein-Tag-Review über alle Rollen hinweg).

### Fixed
- **IDOR bei privaten Kanban-Karten**: mutierende Karten-/Unteraufgaben-
  Endpunkte prüften Sichtbarkeit privater Karten (Personen-Board) nicht,
  nur die reine Board-Zugriffsprüfung - ein zuständiger Trainer konnte über
  die Karten-ID private Karten lesen/ändern/löschen. Neue zentrale Prüfung
  `require_karte_sichtbar` (`app/core/access.py`).
- Kein Rate-Limiting beim Login - einfacher In-Memory-Schutz gegen
  Brute-Force-Versuche ergänzt (`app/core/rate_limit.py`).

### Added
- **"Ich möchte jetzt Unterstützung"**: unabhängig vom Tagebuch immer
  sichtbarer Hinweis in "Mein Tag" mit PSM-Kontakt und externen
  Hilfsangeboten (TelefonSeelsorge, Nummer gegen Kummer) - nie automatisch
  ausgelöst.
- `/konto`: Link zu "Meine Freigaben", Datenexport der eigenen Daten
  (Art. 15 DSGVO, `GET /konto/export`) und Selbstlöschung der eigenen
  Wohlbefinden-/Bewerbungsdaten sowie der persönlichen Kanban-Aufgabenliste.
  Vollständige Konto-/Login-Löschung bewusst zurückgestellt (siehe
  `app/core/deletion.py`, VB-004.md) - blockiert durch nicht-nullbare
  Fremdschlüssel auf Team-Boards.
- Dashboard-Kachel **"Was steht an"** für Teilnehmer und Berufstrainer:
  fällige/überfällige Kanban-Karten der nächsten 7 Tage über alle
  sichtbaren Boards hinweg.
- **Mein-Tag-Übungspool auf 12 Typen erweitert** (siehe
  `app/core/tagesuebungen.py`): zusätzlich zu Atemübung und Zeichnung nun
  Körper-Scan, 5-4-3-2-1-Erdung, Ein Wort für heute, Stärken-Karte,
  Ausmal-Mandala, Ruhe-Ort-Visualisierung, Gedanken-Waage, Sorgen
  loslassen, Dankbarkeits-Foto-Moment und Mini-Ziel des Tages - wöchentlich
  rotierend (Fisher-Yates je Kalenderwoche), sodass innerhalb einer
  Arbeitswoche (Mo-Fr) kein Übungstyp doppelt gezeigt wird. Alle neuen
  Typen folgen demselben Prinzip wie die bestehenden: kein Scoring, keine
  wertende Sprache.

## [0.1.8] - 2026-08-03

### Added
- **Atemübungs-Pool mit 15 Varianten** (siehe `app/core/atemuebungen.py`):
  statt einer einzigen fest verdrahteten Verbinde-die-Punkte-Übung wird
  morgens täglich eine von 15 Varianten deterministisch ausgewählt (Box-
  Atmung, Dreieck-Atmung, Sechseck-Atmung, Anker setzen, ...) - Layout
  (Punktanzahl/-anordnung) wird je nach Übung automatisch berechnet.
  Migration `a1b2c3d4e5f6` speichert den gezeigten Namen, damit er beim
  erneuten Aufruf stabil bleibt.
- **Sinnvoller Halten-Timer (5-6 Sekunden)**: "Halten"-Punkte schalten
  nicht mehr sofort weiter, sondern zeigen einen kurzen Countdown ("Halten
  … noch 4"), bevor zum nächsten Punkt weitergezogen werden kann - eine
  bewusste Pause statt eines Präzisionstests.

### Fixed
- **"Zeichnung löschen" hat nicht funktioniert**: der Button lag im Markup
  außerhalb des von der JS als Container verwendeten `data-zeichenfeld`-
  Wrappers, wodurch der Klick-Handler nie gefunden/gebunden wurde - jetzt
  innerhalb des Wrappers verschachtelt.

## [0.1.7] - 2026-08-02

### Added
- **Vertikale Tab-Leiste** als wiederverwendbare Komponente (`.seiten-tabs`,
  siehe `app/static/css/style.css`) für Seiten mit mehreren klar getrennten
  Abschnitten - Alpine-gestützt, ohne Server-Roundtrip beim Wechseln. Auf
  schmalen Screens wird daraus eine horizontal scrollende Leiste statt
  einer Sidebar.
- **Bewerbungen-Seite komplett auf diese Tab-Leiste umgebaut**: "Neue
  Bewerbung", "Meine Unterlagen", "Laufende Bewerbungen", "Abgeschlossene
  Bewerbungen" und "Für wen freigeben" sind jetzt getrennte Abschnitte statt
  einer einzigen langen Seite mit allem untereinander.
- **4 interaktive Elemente im 5-Minuten-Tagebuch** (siehe
  `app/static/js/tagebuch-interaktiv.js`, `app/models/wohlbefinden.py`):
  eine Verbinde-die-Punkte-Atemübung morgens (nur der Zeitpunkt wird
  gespeichert, kein Zeichenpfad), ein optionaler Energie-Level als
  Batterie-Symbol morgens (rein privat, taucht nie im Dashboard-Trend auf),
  ein Freihand-Zeichenfeld abends ("Male, was dich heute gefreut hat" -
  wie Bewerbungsunterlagen verschlüsselt gespeichert, siehe
  `app/core/uploads.py`, mit eigenem Hard-Delete-Pfad) und drei antippbare
  Checklisten-Kacheln abends. Migration `f6a7b8c9d0e1`.

### Fixed
- Echter Bug beim Verbinde-die-Punkte-Widget behoben: der Startpunkt der
  Atemübung wurde nie als "erreicht" gezählt, da die Trefferprüfung nur bei
  Zeigerbewegung lief, nicht beim initialen Antippen selbst.
- CSS-Spezifitätsbug behoben, durch den die gefüllten Segmente der
  Energie-Batterie unsichtbar blieben (`button:not(.btn)` war spezifischer
  als `.energie-segment--voll`).
- Mobile Tab-Leiste verursachte horizontales Scrollen der gesamten Seite
  statt nur der Leiste selbst (fehlendes `min-width: 0` auf Flex-Kindern,
  plus `width: 100%` auf einzelnen Tab-Buttons, die dadurch je die volle
  Leistenbreite beanspruchten).

## [0.1.6] - 2026-08-02

### Fixed
- **Echter, reproduzierbarer CSRF-Bug behoben**: "+ Spalte hinzufügen" im
  Kanban (und praktisch jedes andere Formular) konnte mit "Ungültige oder
  abgelaufene Anfrage" (403) fehlschlagen, sobald zwischen dem Laden der
  Seite und dem Absenden mehr als eine Sekunde lag. Ursache: Starlettes
  `SessionMiddleware` signiert den Session-Cookie bei **jeder** Antwort mit
  einem neuen Zeitstempel neu (`itsdangerous.TimestampSigner`) - der rohe
  Cookie-String ändert sich dadurch bei jedem Request-Response-Zyklus,
  obwohl die enthaltenen Daten (z. B. `user_id`) gleich bleiben. Das
  CSRF-Token wurde bisher direkt aus diesem rohen, instabilen Cookie-Wert
  abgeleitet - ein beim Seitenaufruf eingebettetes Token war dadurch schon
  beim nächsten Request wieder ungültig. Fix: Das Token wird jetzt aus
  einem stabilen, zufälligen Wert abgeleitet, der im entschlüsselten
  Session-Dict liegt (`request.session["_csrf_secret"]`, siehe
  `app/core/templating.py:csrf_token`) und über beliebig viele Requests
  hinweg gültig bleibt, bis die Session geleert wird (Login/Logout).

## [0.1.5] - 2026-08-02

### Changed
- **"Mein Tag" komplett auf ein 5-Minuten-Tagebuch umgestellt** (in
  Anlehnung an das klassische "Five Minute Journal"-Format): die
  Stimmungs-/Energie-Skala (1-10, Heatmap-Verlauf) wurde vollständig durch
  ein strukturiertes Tagebuch ersetzt: morgens 3 feste
  Dankbarkeits-Felder + 1 täglich rotierender Klarheits-/Vorsatz-Impuls,
  abends 3 feste "großartige Dinge"-Felder + 1 rotierender
  Abendreflexions-Impuls. Der rotierende Impuls wird deterministisch aus
  Teilnehmer:in + Datum abgeleitet (`app/core/tagebuch_prompts.py`) - am
  selben Tag immer derselbe, ohne dass er separat gespeichert werden muss.
- Neues Datenmodell `TagebuchEintrag` ersetzt `WohlbefindenEintrag`
  (Migration `e5f6a7b8c9d0`); bestehende Stimmungs-Einträge werden dabei
  hart gelöscht (siehe CLAUDE.md §10 Löschkonzept - konsistent mit der
  bestehenden Hard-Delete-Pflicht für diese Datenkategorie).
- "Dein Verlauf" zeigt jetzt eine lesbare Liste der letzten 14 Tage mit
  Inhalt statt einer Farbraster-Heatmap - Freitext lässt sich nicht
  sinnvoll auf eine Farbskala reduzieren, ohne genau die Bewertungs-Optik
  zu erzeugen, die das neue Format vermeiden soll.
- Dashboard-Rückblick zählt jetzt Tage mit Tagebuch-Eintrag
  (`woechentliche_tagebuch_tage`) statt eines Stimmungs-Trends - eine
  reine Teilnahme-Zählung, die inhaltlich nie negativ ausfallen kann.

### Removed
- `app/core/skala.py`, `app/static/js/wohlbefinden.js` (nicht mehr
  benötigt, siehe oben).

## [0.1.4] - 2026-08-02

### Changed
- Kanban-Board-Layout von horizontal scrollender Flex-Reihe auf ein
  wrappendes CSS-Grid umgestellt: alle Spalten passen auf gängigen
  Breiten in eine Zeile (kein Scrollbalken, keine Pfeil-Buttons mehr
  nötig), bei mehr Spalten oder auf schmalen Screens wird umgebrochen
  statt seitlich zu scrollen. "+ Spalte hinzufügen" ist jetzt eine
  schlanke Leiste über den Spalten statt einer leeren Geister-Spalte im
  Spalten-Grid.

## [0.1.3] - 2026-08-02

### Changed
- **Neue Definition von "Schritte geschafft"**: zählt jetzt jede Karte, die
  mindestens einen Schritt nach rechts (in eine Spalte mit höherer
  Reihenfolge) gezogen wurde - nicht mehr erst bei vollständigem Abschluss.
  Neue Tabelle `kartenbewegung` protokolliert Vorwärtsbewegungen (Migration
  `d4e5f6a7b8c9`); Zurückziehen wird nicht negativ gewertet, zählt aber auch
  nicht doppelt.
- **Stimmungs-Trend statt Emoji als Primäranzeige** im Dashboard-Rückblick:
  großer Pfeil zeigt die Entwicklung, Emoji nur noch als Rückfall-Anzeige
  vor dem ersten Vergleichswert.
- **Trend-Sprache/-Farbe nie mehr wertend**: `app/core/skala.py:trend()`
  vermeidet jetzt Formulierungen wie "schwerer" zugunsten neutraler
  Beschreibungen ("diese Woche ruhiger"); die CSS-Klasse für rückläufige
  Werte ist bewusst NICHT mehr rot eingefärbt (wirkt auf Dashboard UND
  "Mein Tag" gleichermaßen, da beide dieselbe Funktion nutzen).
- Mood-Heatmap-Kacheln ("Mein Tag" → Verlauf) zeigen kein kleines,
  schlecht lesbares Emoji mehr - Farbe bleibt das alleinige Signal in der
  Kachel, Details weiterhin per Tooltip/Antippen abrufbar.

## [0.1.2] - 2026-08-02

### Added
- Bottom-Tab-Bar für echtes Mobile (`partials/tabbar.html`, analog Scandy-
  Lite): 4 Kernziele für Teilnehmer:innen (Projekte, Wochenberichte, Mein
  Tag, Bewerbungen), 3 für Berufstrainer:innen; seltenere Ziele bleiben im
  Hamburger-Menü.
- Dashboard für Teilnehmer:innen ausgebaut: Kachel-Schnellzugriff
  (`.quick-tiles`, analog Scandy-Lite) statt reiner Karten, plus
  "Deine Woche im Rückblick" mit Stimmungs-Trend und Bewerbungs-Überblick
  neben dem bestehenden Schritte-Signal - durchgehend sanfte Sprache ohne
  Bewertung (CLAUDE.md Abschnitt 24/25).

## [0.1.1] - 2026-08-02

### Added
- CSRF-Schutz für alle mutierenden Formulare/Requests.

### Fixed
- Hauptnav war auf breiten Screens dauerhaft unsichtbar (fehlende
  Gegenregel zu Alpines `x-show`, siehe Commit `e69b2bc`).
- Grellweiße native Formularelemente im Dark-Mode (fehlende
  `color-scheme`-Deklaration).
- **Wichtig für Cache-Busting**: versionierte Assets (`?v={{ asset_version }}`)
  werden ein Jahr lang unveränderlich gecacht (`app/core/static_cache.py`) -
  jede CSS/JS-Änderung MUSS ab sofort mit einem Bump von `__version__`
  (`app/version.py`) einhergehen, sonst bekommen wiederkehrende Browser
  die alte, gecachte Datei weiter ausgeliefert (genau das ist bei den
  beiden obigen Fixes zunächst passiert).

## [0.1.0] - 2026-08-02

### Added
- UI/UX-Audit mit 22 umgesetzten Befunden (siehe `tasks/uiux-audit/`):
  u.a. maskierte Passwortfelder, gestaltete Fehlerseiten statt roher
  JSON-Antworten, tastaturbedienbare Alternative zum Kanban-Drag&Drop,
  Dark-Mode, `aria-live` auf Speicher-Toasts, mobile Nav-Kollaps.
- Manueller Dark-/Light-Mode-Umschalter (zusätzlich zur automatischen
  Systemerkennung), `localStorage`-gestützt.
- Struktur an das Schwestermodul Scandy-Lite angeglichen: Alpine.js + htmx
  vendort, `asset_version`-Cache-Busting, `.icon-btn`/`.link-btn`-Klassen,
  `app/core/static_cache.py` (versionierte Assets cachebar bis zu einem
  Jahr), Test-Scaffolding (`tests/`, `pytest.ini`, `ruff.toml`).

### Known Gaps
- Kein CSRF-Schutz auf POST-Formularen (im Unterschied zu Scandy-Lite) -
  vorgemerkt als eigener, sicherheitskritischer Auftrag.
