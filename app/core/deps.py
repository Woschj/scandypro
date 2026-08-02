from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.security import SESSION_COOKIE_NAME, verify_csrf_token
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
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_optional(request: Request, session: SessionDep) -> User | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return await session.get(User, user_id)


async def verify_csrf(request: Request) -> None:
    """CSRF-Schutz für mutierende Formulare/Requests: das Token muss zum
    aktuellen Session-Cookie passen (siehe app.core.security.generate_csrf_token).
    Klassische Formulare senden es im versteckten `csrf_token`-Feld, per
    fetch() gesendete JSON-Requests (app/static/js/kanban.js,
    app/static/js/wohlbefinden.js) im Header `X-CSRF-Token`.

    Als Router-Dependency eingebunden wirkt das auf jede Route des Routers;
    bei GET/HEAD wirkungslos (early return), da diese nie mutieren sollten.
    Bewusst NICHT auf /login (dort existiert vor der Anmeldung noch kein
    Session-Cookie, aus dem sich ein Token ableiten ließe)."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return

    token = request.headers.get("X-CSRF-Token")
    if not token:
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type:
            form = await request.form()
            token = form.get("csrf_token", "")

    session_value = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not verify_csrf_token(str(token or ""), session_value):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ungültige oder abgelaufene Anfrage. Bitte Seite neu laden.")
