from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.security import verify_csrf_token
from app.models.user import User

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(request: Request, session: SessionDep) -> User:
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet.")
    user = await session.get(User, user_id)
    if user is None:
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sitzung ungültig.")
    if not user.aktiv:
        # Sofortige Aussperrung bei laufender Session, falls der Account
        # zwischenzeitlich deaktiviert wurde (siehe app/routers/admin.py) -
        # nicht erst beim nächsten Login.
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Dieser Account ist deaktiviert.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_optional(request: Request, session: SessionDep) -> User | None:
    """Wie get_current_user, aber ohne HTTPException - für Stellen, die auch
    ohne Anmeldung funktionieren müssen (Dashboard-Redirect, Fehlerseiten).

    Prüft `aktiv` genauso wie get_current_user: sonst behielte ein
    zwischenzeitlich deaktivierter Account weiterhin Zugriff auf das
    Dashboard (Kontaktdaten, "Was steht an" inkl. Kartentiteln,
    Wochenrückblick), weil ausgerechnet die Startseite die optionale
    Variante nutzt (siehe app/main.py)."""
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    user = await session.get(User, user_id)
    if user is None or not user.aktiv:
        request.session.clear()
        return None
    return user


async def verify_csrf(request: Request) -> None:
    """CSRF-Schutz für mutierende Formulare/Requests: das Token muss zum
    stabilen, in der Session abgelegten Zufallswert passen (siehe
    app.core.templating.csrf_token, app.core.security.generate_csrf_token -
    bewusst NICHT der rohe Session-Cookie-String, der sich bei jeder Antwort
    durch Starlettes Timestamp-Neusignierung ändert und ein daraus
    abgeleitetes Token sofort ungültig machen würde). Klassische Formulare
    senden es im versteckten `csrf_token`-Feld, per fetch() gesendete
    JSON-Requests (app/static/js/kanban.js) im Header `X-CSRF-Token`.

    Als Router-Dependency eingebunden wirkt das auf jede Route des Routers;
    bei GET/HEAD wirkungslos (early return), da diese nie mutieren sollten.
    Bewusst NICHT auf /login (die Anmeldung selbst braucht keinen Schutz vor
    eingeloggten Fremd-Sessions, die einen Login-Request fälschen könnten)."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return

    token = request.headers.get("X-CSRF-Token")
    if not token:
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type:
            form = await request.form()
            token = form.get("csrf_token", "")

    secret = request.session.get("_csrf_secret", "")
    if not verify_csrf_token(str(token or ""), secret):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ungültige oder abgelaufene Anfrage. Bitte Seite neu laden.")
