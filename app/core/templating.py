import json
import secrets
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.core.security import generate_csrf_token
from app.version import __version__

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

# Cache-Busting-Query für statische Assets über die App-Version statt
# Datei-mtime - analog zum Schwestermodul Scandy-Lite (app/core/templating.py
# dort: asset_version = __version__), damit beide Apps dieselbe Konvention
# nutzen (Templates schreiben literal "/static/....js?v={{ asset_version }}").
templates.env.globals["asset_version"] = __version__


def csrf_token(request: Request) -> str:
    """Für `{{ csrf_token(request) }}` in app/templates/partials/csrf_field.html
    - leitet das Token aus einem stabilen, in der (serverseitig entschlüsselten)
    Session abgelegten Zufallswert ab (siehe app.core.security.generate_csrf_token),
    NICHT aus dem rohen Session-Cookie-String: Starlettes SessionMiddleware
    signiert den Cookie bei JEDER Antwort neu (itsdangerous.TimestampSigner,
    Zeitstempel in der Signatur), wodurch sich der rohe Cookie-Wert bei jedem
    Request-Response-Zyklus ändert - ein daraus abgeleitetes Token wäre schon
    beim nächsten Request wieder ungültig (siehe CHANGELOG). Der hier erzeugte
    Zufallswert liegt dagegen im entschlüsselten Session-Dict und bleibt über
    mehrere Requests hinweg stabil, bis die Session geleert wird (Login/Logout)."""
    secret = request.session.get("_csrf_secret")
    if not secret:
        secret = secrets.token_urlsafe(32)
        request.session["_csrf_secret"] = secret
    return generate_csrf_token(secret)


templates.env.globals["csrf_token"] = csrf_token


def initialen(name: str) -> str:
    """Kürzt einen Namen auf 1-2 Buchstaben für Avatar-Kreise (siehe
    app/templates/kanban/board.html)."""
    teile = name.split()
    if not teile:
        return "?"
    if len(teile) == 1:
        return teile[0][0].upper()
    return (teile[0][0] + teile[-1][0]).upper()


templates.env.filters["initialen"] = initialen

ROLLENNAMEN = {
    "teilnehmer": "Teilnehmer:in",
    "berufstrainer": "Berufstrainer:in",
    "psychosoziale_mitarbeit": "Psychosoziale Mitarbeiter:in",
    "einrichtungs_admin": "Einrichtungs-Admin",
}


def rollenname(rolle: str) -> str:
    """Menschenlesbare Rollenbezeichnung statt des rohen Enum-Slugs (siehe
    app/models/user.py:RoleEnum) - für Anzeige, z.B. app/templates/base.html."""
    return ROLLENNAMEN.get(rolle, rolle)


templates.env.filters["rollenname"] = rollenname


def tojson(value) -> str:
    """Minimaler tojson-Filter (Jinja2 bringt ihn ohne Flask nicht mit) -
    für kleine, sichere JSON-Snippets direkt im Template."""
    return json.dumps(value).replace("</", "<\\/")


templates.env.filters["tojson"] = tojson
