import json
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.core.security import SESSION_COOKIE_NAME, generate_csrf_token
from app.core.skala import ENERGIE_EMOJI, STIMMUNG_EMOJI, energie_emoji, heatmap_farbe, stimmung_emoji
from app.version import __version__

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

# Cache-Busting-Query für statische Assets über die App-Version statt
# Datei-mtime - analog zum Schwestermodul Scandy-Lite (app/core/templating.py
# dort: asset_version = __version__), damit beide Apps dieselbe Konvention
# nutzen (Templates schreiben literal "/static/....js?v={{ asset_version }}").
templates.env.globals["asset_version"] = __version__


def csrf_token(request: Request) -> str:
    """Für `{{ csrf_token(request) }}` in app/templates/partials/csrf_field.html
    - leitet das Token aus dem aktuellen Session-Cookie ab (siehe
    app.core.security.generate_csrf_token). Vor dem Login gibt es kein
    Session-Cookie; dann liefert das einen "leeren" Token, was unkritisch
    ist, da /login selbst nicht CSRF-geschützt ist (siehe app.core.deps.verify_csrf)."""
    return generate_csrf_token(request.cookies.get(SESSION_COOKIE_NAME, ""))


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

templates.env.filters["stimmung_emoji"] = stimmung_emoji
templates.env.filters["energie_emoji"] = energie_emoji
templates.env.filters["heatmap_farbe"] = heatmap_farbe
templates.env.globals["STIMMUNG_EMOJI"] = STIMMUNG_EMOJI
templates.env.globals["ENERGIE_EMOJI"] = ENERGIE_EMOJI


def tojson(value) -> str:
    """Minimaler tojson-Filter (Jinja2 bringt ihn ohne Flask nicht mit) -
    für kleine, sichere JSON-Snippets direkt im Template."""
    return json.dumps(value).replace("</", "<\\/")


templates.env.filters["tojson"] = tojson
