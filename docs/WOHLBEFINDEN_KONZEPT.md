# Konzept: Wohlbefinden-Tracking mit echtem Nutzen

> Vertiefung von Abschnitt 2.2 in [KONZEPT.md](KONZEPT.md). Prämisse: reines
> Zahlen-Sammeln ("Stimmung heute: 3/5") hat für sich genommen keinen Wert –
> es wird schnell zur lästigen Pflicht und niemand schaut sich die Trends je
> wieder an. Der Nutzen entsteht erst, wenn Tracking zu **Selbsterkenntnis**,
> **besseren Gesprächen** oder **passenderer Belastungssteuerung** führt.
> Alle Bausteine unten zahlen auf genau eines dieser drei Ziele ein.

---

## 0. Nutzenhypothese

Wohlbefinden-Tracking ist in ScandyPro **kein Diagnoseinstrument** und
**keine Überwachung**. Es ist ein Werkzeug für den Teilnehmer selbst, mit
drei möglichen Nutzeffekten:

1. **Selbsterkenntnis**: eigene Muster sehen ("An Tagen mit vielen offenen
   Fristen ist meine Energie niedriger") – ohne dass jemand anderes das
   auswerten muss.
2. **Bessere Gespräche**: strukturierte Grundlage für Termine mit
   psychosozialer Mitarbeit, statt vager Erinnerung ("Wie ging's die
   letzten Wochen?" → "Schau, hier ist es").
3. **Passendere Belastungssteuerung**: Berufstrainer können Arbeitspensum
   (Kanban) an die tatsächliche aktuelle Kapazität anpassen – ohne die
   sensiblen Rohdaten zu sehen.

Jedes Feature muss klar einem dieser drei Punkte zugeordnet werden können.
Wenn nicht: nicht bauen.

---

## 1. Baustein A – Kurz-Check-in (Grundlage)

> **Umgesetzt als 5-Minuten-Tagebuch** (siehe `app/models/wohlbefinden.py:
> TagebuchEintrag`, `app/core/tagebuch_prompts.py`): Die ursprünglich hier
> geplanten Skalen (Stimmung/Energie/Belastung 1–5) wurden verworfen, da
> jede numerische Skala – egal wie sie eingefärbt wird – bei fallenden
> Werten wie eine Bewertung wirkt (siehe CLAUDE.md "keine roten
> Warnsymbole"). Stattdessen: freier Text in festen Kategorien (morgens 3x
> "Ich bin dankbar für" + 1 rotierender Klarheits-/Vorsatz-Impuls; abends
> 3x "großartige Dinge" + 1 rotierender Abendreflexions-Impuls), pro
> Tageszeit deterministisch aus Teilnehmer:in + Datum abgeleitet. Das
> Dashboard-Signal zählt nur noch reine Teilnahme (Tage mit Eintrag), nie
> Inhalt/Stimmung (siehe `app/core/fortschritt.py:
> woechentliche_tagebuch_tage`).
>
> Die Bausteine B–F unten bleiben unverändert als **zukünftige Roadmap**
> stehen; sie setzen keine Skalenwerte mehr voraus, sondern könnten auf
> Basis der Tagebuch-Texte/Teilnahme neu gedacht werden, falls sie
> tatsächlich umgesetzt werden.

- Freitext optional, nie Pflichtfeld
- Erinnerung: sanft, konfigurierbar (täglich/mehrmals wöchentlich/aus),
  keine Streak-Zwänge, kein Schuldgefühl bei Auslassen ("3 Tage nicht
  ausgefüllt" wird nicht negativ dargestellt)

Ohne diesen Baustein funktioniert nichts anderes – aber er allein liefert
noch keinen Nutzen, nur Rohdaten.

---

## 2. Baustein B – Persönliche Muster-Erkennung (Nutzen: Selbsterkenntnis)

Der Teilnehmer sieht seine eigenen Daten nicht nur als Liniendiagramm,
sondern im Kontext der eigenen Ereignisse aus den anderen Modulen. Da alle
Daten demselben Owner gehören, ist das eine reine Personen-interne
Verknüpfung – kein neues Cross-User-Risiko.

- **Zeitleisten-Overlay**: Wohlbefinden-Trend + eigene Ereignisse
  (Bewerbungsstatus-Änderungen, Kanban-Fristen/erledigte Karten) auf einer
  gemeinsamen persönlichen Zeitachse. Beispiel: "Am 14.7. – Absage Firma X"
  neben dem Stimmungsverlauf.
- **Einfache, transparente Muster statt Blackbox-KI**: regelbasierte,
  nachvollziehbare Hinweise, z. B. "Deine Energie war an den letzten 5
  Tagen mit >2 offenen Kanban-Fristen im Schnitt niedriger als sonst."
  Immer als Beobachtung formuliert, nie als Diagnose oder Bewertung.
  Keine KI-generierten psychologischen Interpretationen (Haftungs- und
  Qualitätsrisiko) – Regeln sind einfache Aggregationen über die eigenen
  Daten, für den Teilnehmer nachvollziehbar und abschaltbar.
- **Tag-Auswertung**: "Diese Tags kommen an guten Tagen häufig vor: …" /
  "an belastenden Tagen häufig: …" – hilft, eigene Frühwarnzeichen und
  Ressourcen zu erkennen.
- Alles nur für den Teilnehmer selbst sichtbar, keine automatische
  Weitergabe der Insights.

---

## 3. Baustein C – Belastbarkeits-Signal (Nutzen: Belastungssteuerung)

Kernidee: Statt der sensiblen Rohdaten wird ein **bewusst gesetztes,
grobes, eigenständiges Signal** geteilt – nicht automatisch aus den
Check-in-Werten berechnet. Das trennt "was ich fühle" (privat, granular)
von "was ich gerade leisten kann" (bewusst geteilt, grob).

- Eigenes Datenfeld, unabhängig vom `WohlbefindenEintrag`:
  `Kapazitätseinschätzung` mit Werten z. B. *normal* / *reduziert* /
  *aktuell wenig Kapazität* – vom Teilnehmer aktiv gesetzt, nicht aus
  Stimmungswerten hergeleitet.
- Sichtbarkeit steuert der Teilnehmer wie jede Freigabe: Standard aus,
  optional dauerhaft für zugeordneten Berufstrainer sichtbar.
- Wirkung im Kanban-Modul: Berufstrainer sieht bei reduzierter Kapazität
  einen Hinweis bei der Aufgabenzuweisung ("aktuell reduzierte
  Kapazität angegeben") – keine automatische Sperre, sondern
  Entscheidungshilfe für den Menschen.
- Bewusst **keine** Ampel/Alarmfarben-Ästhetik (siehe UX-Leitlinien in
  [KONZEPT.md](KONZEPT.md)) – neutrale Wortwahl, keine Wertung.
- Das ist der zentrale Baustein, der Tracking von reiner
  Selbstbeobachtung zu echtem organisatorischem Nutzen macht, ohne die
  Rohdaten preiszugeben.

---

## 4. Baustein D – Gesprächsvorbereitung & Sitzungsfreigabe (Nutzen: bessere Gespräche)

- **Sitzungsfreigabe**: Vor einem Termin mit psychosozialer Mitarbeit kann
  der Teilnehmer eine zeitlich eng befristete Freigabe aktivieren (z. B.
  "heute, 14–15 Uhr" oder "für die Dauer dieses Termins"), die danach
  automatisch abläuft – bequemer und sicherer als eine dauerhafte
  Freigabe, die man vergisst zu widerrufen.
- **Kuratierte Zusammenfassung statt Rohdaten-Dump**: der Teilnehmer kann
  vor dem Teilen auswählen, welchen Zeitraum/welche Einträge er zeigen
  möchte ("letzte 2 Wochen", "nur diese 3 Einträge") – aktive Kuration
  statt Alles-oder-nichts.
- **Gemeinsame Ansicht während des Gesprächs**: einfache Trend-Darstellung
  plus die vom Teilnehmer markierten Tags/Ereignisse als Gesprächseinstieg
  – ersetzt "wie ging's dir so" durch konkrete Anknüpfungspunkte.
- Nach Ablauf der Sitzungsfreigabe: Zugriff endet automatisch, im
  Audit-Log sichtbar dokumentiert (siehe Datenschutzkonzept Abschnitt 4.3).

---

## 5. Baustein E – Ressourcen-Impulse (Nutzen: Selbsterkenntnis → Handlung)

- Kleine, redaktionell von der Einrichtung gepflegte Tipp-Bibliothek,
  verknüpft an Tags (z. B. Tag "Bewerbungsstress" → 2–3 kurze,
  praxisnahe Hinweise, die die Einrichtung selbst hinterlegt)
- **Kein KI-generierter psychologischer Ratschlag** – Inhalte werden von
  der Einrichtung (psychosoziale Mitarbeit) kuratiert, damit fachlich
  verantwortet und lokal passend (z. B. Verweis auf hausinterne Angebote)
- Rein optional einblendbar, nie aufdringlich, kein Popup-Zwang

---

## 6. Baustein F – Eigene Mini-Ziele (Nutzen: Selbstwirksamkeit)

- Teilnehmer kann sich freiwillig ein einfaches, selbst gewähltes Ziel
  setzen (z. B. "diese Woche 2x eine Pause bewusst machen") und im
  Check-in ankreuzen, ob es geklappt hat
- Reine Selbstbeobachtung, keine Bewertung/Score, keine Sichtbarkeit für
  Dritte außer über die normale Freigabe-Logik
- Bewusst kein Gamification-Wettbewerb (keine Bestenlisten, keine
  Vergleiche zwischen Teilnehmern) – passt nicht zum Kontext und würde
  Druck statt Nutzen erzeugen

---

## 7. Sicherheitsnetz (getrennt vom Tracking)

- Ein jederzeit sichtbarer, von den Trackingdaten **unabhängiger** Button
  "Ich möchte jetzt Unterstützung" – führt zu hinterlegten
  Ansprechpersonen/Kontaktwegen der Einrichtung (und ggf. externen
  Kriseninformationen)
- Bewusst **nicht** automatisch durch niedrige Wohlbefinden-Werte
  ausgelöst (siehe Datenschutzkonzept Abschnitt 7: keine automatische
  Eskalation) – das würde Vertrauen in die Privatheit des Trackings
  untergraben und Teilnehmer dazu bringen, ehrliche Angaben zu vermeiden
- Diese Funktion ist bewusst simpel und losgelöst vom Rest des Moduls zu
  halten – kein Diagnose- oder Risiko-Scoring dahinter

---

## 8. Was das Modul bewusst NICHT tut

- Keine automatische Alarmierung/Eskalation aus Zahlenwerten
- Keine KI-generierte psychologische Bewertung oder Diagnose
- Keine Ampel-/Score-Darstellung, die wertend wirkt
- Kein Vergleich zwischen Teilnehmern, keine Rankings
- Keine Ableitung des Belastbarkeits-Signals (Baustein C) direkt aus den
  Stimmungswerten – muss immer eine bewusste, eigene Angabe bleiben, sonst
  verwischt die Trennung "privates Gefühl" vs. "geteilte Kapazitätsangabe"

---

## 9. Woran Erfolg erkennbar wäre

- Teilnehmer nutzen den Check-in über Wochen regelmäßig (nicht nur einmalig
  aus Neugier)
- Sitzungsfreigaben (Baustein D) werden vor Gesprächen tatsächlich aktiv
  genutzt, statt dass Gespräche weiter ohne Datenbasis stattfinden
- Berufstrainer passen nachweislich Kanban-Zuweisungen an, wenn ein
  Belastbarkeits-Signal (Baustein C) gesetzt ist
- Qualitatives Feedback der Teilnehmer: Tracking wird als hilfreich für
  sich selbst empfunden, nicht als zusätzliche Kontrolle

---

## 10. Reihenfolge im Rahmen der Roadmap

Ergänzt/konkretisiert Abschnitt 5 (Phasen) in [KONZEPT.md](KONZEPT.md):

- **Phase 1 (MVP)**: Baustein A (Check-in) + einfache eigene
  Verlaufsansicht ohne Overlay
- **Phase 2**: Baustein D (Freigaben inkl. Sitzungsfreigabe) – hier
  entsteht der erste geteilte Nutzen
- **Phase 2/3**: Baustein C (Belastbarkeits-Signal) – eigenständiges
  Feature, technisch unabhängig vom Freigabe-Ausbau, aber inhaltlich am
  sinnvollsten direkt danach
- **Phase 3**: Baustein B (Muster-Overlay mit Kanban/Bewerbungen),
  Baustein E (Ressourcen-Impulse), Baustein F (Mini-Ziele)
- **Baustein 7 (Sicherheitsnetz-Button)**: so früh wie möglich, unabhängig
  vom restlichen Fortschritt – ist einfach umzusetzen und sollte nicht auf
  spätere Phasen warten
