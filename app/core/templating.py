from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.skala import ENERGIE_EMOJI, STIMMUNG_EMOJI, energie_emoji, heatmap_farbe, stimmung_emoji

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def static_version(pfad: str) -> str:
    """Cache-Busting-Query anhand der mtime der Datei unter app/static, damit
    CSS/JS-Änderungen nach einem Deploy nicht durch Browser-Caching verdeckt
    werden (siehe app/templates/base.html)."""
    voller_pfad = _STATIC_DIR / pfad
    try:
        mtime = int(voller_pfad.stat().st_mtime)
    except OSError:
        mtime = 0
    return f"/static/{pfad}?v={mtime}"


templates.env.globals["static_version"] = static_version


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
