"""Statische Liste externer Hilfsangebote für den Sicherheitsnetz-Hinweis in
"Mein Tag" (siehe app/routers/wohlbefinden.py,
app/templates/wohlbefinden/uebersicht.html, docs/WOHLBEFINDEN_KONZEPT.md
Abschnitt 7 "Sicherheitsnetz").

Bewusst unabhängig von Trackingdaten/Werten - wird immer gleich angezeigt,
nie automatisch ausgelöst. Bundesweit kostenfrei und anonym erreichbare
Angebote, keine Einrichtungs-spezifische Konfiguration nötig."""

HILFSANGEBOTE: list[dict] = [
    {
        "name": "TelefonSeelsorge",
        "kontakt": "0800 111 0 111 oder 0800 111 0 222",
        "hinweis": "Kostenfrei, anonym, rund um die Uhr - auch per Chat unter telefonseelsorge.de",
    },
    {
        "name": "Nummer gegen Kummer",
        "kontakt": "116 123",
        "hinweis": "Kostenfrei, anonym, rund um die Uhr",
    },
]
