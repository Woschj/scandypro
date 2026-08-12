"""HTTP-Routen für den optionalen SSO-Login - siehe app/core/oidc.py für
die Zuordnungs-/Anlegelogik. Alle Routen antworten mit 404, solange kein
Provider konfiguriert ist (settings.oidc_enabled), damit sich die App ohne
SSO-Konfiguration exakt wie zuvor verhält."""


from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.config import settings
from app.core.deps import SessionDep
from app.core.oidc import finde_oder_lege_an, oauth
from app.core.templating import templates
from app.core.zeit import jetzt

router = APIRouter(prefix="/auth/oidc", tags=["oidc"])


def _sso_pruefen() -> None:
    if not settings.oidc_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND)


@router.get("/login")
async def oidc_login(request: Request):
    _sso_pruefen()
    redirect_uri = request.url_for("oidc_callback")
    return await oauth.oidc.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="oidc_callback", response_class=HTMLResponse)
async def oidc_callback(request: Request, session: SessionDep):
    _sso_pruefen()
    token = await oauth.oidc.authorize_access_token(request)
    claims = token.get("userinfo") or await oauth.oidc.userinfo(token=token)

    user = await finde_oder_lege_an(session, dict(claims))

    if not user.aktiv:
        return templates.TemplateResponse(
            request,
            "auth/sso_wartet.html",
            {"current_user": None, "oidc_provider_name": settings.oidc_provider_name},
        )

    user.letzter_login = jetzt()
    session.add(user)
    await session.commit()
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)
