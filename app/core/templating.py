from pathlib import Path

from fastapi.templating import Jinja2Templates

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
