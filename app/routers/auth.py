import json
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlmodel import select

from app.core.config import settings
from app.core.datenexport import eigene_daten_export
from app.core.deps import CurrentUser, SessionDep, verify_csrf
from app.core.rate_limit import ist_gesperrt, registriere_fehlversuch, zuruecksetzen
from app.core.security import hash_password, verify_password
from app.core.templating import templates
from app.models.user import RoleEnum, User

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse(
        request, "auth/login.html", {"error": None, "seed_demo_data": settings.seed_demo_data}
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    session: SessionDep,
    email: str = Form(...),
    password: str = Form(...),
):
    client_ip = request.client.host if request.client else "unbekannt"
    if ist_gesperrt(email, client_ip):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Zu viele Versuche. Bitte versuch es in ein paar Minuten noch einmal.", "seed_demo_data": settings.seed_demo_data},
            status_code=429,
        )

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        registriere_fehlversuch(email, client_ip)
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "E-Mail oder Passwort ist falsch.", "seed_demo_data": settings.seed_demo_data},
            status_code=401,
        )
    if not user.aktiv:
        registriere_fehlversuch(email, client_ip)
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {
                "error": "Dieser Account ist aktuell deaktiviert. Wende dich an deine Einrichtung.",
                "seed_demo_data": settings.seed_demo_data,
            },
            status_code=403,
        )
    zuruecksetzen(email, client_ip)
    user.letzter_login = datetime.utcnow()
    session.add(user)
    await session.commit()
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout", dependencies=[Depends(verify_csrf)])
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/konto", response_class=HTMLResponse)
async def konto_form(request: Request, current_user: CurrentUser):
    return templates.TemplateResponse(request, "auth/konto.html", {"current_user": current_user, "error": None})


@router.post("/konto/passwort", response_class=HTMLResponse, dependencies=[Depends(verify_csrf)])
async def passwort_aendern(
    request: Request,
    current_user: CurrentUser,
    session: SessionDep,
    aktuelles_passwort: str = Form(...),
    neues_passwort: str = Form(...),
    neues_passwort_wiederholen: str = Form(...),
):
    fehler = None
    if not verify_password(aktuelles_passwort, current_user.password_hash):
        fehler = "Aktuelles Passwort ist falsch."
    elif len(neues_passwort) < 8:
        fehler = "Neues Passwort muss mindestens 8 Zeichen haben."
    elif neues_passwort != neues_passwort_wiederholen:
        fehler = "Die Wiederholung stimmt nicht mit dem neuen Passwort überein."

    if fehler:
        return templates.TemplateResponse(
            request, "auth/konto.html", {"current_user": current_user, "error": fehler}, status_code=400
        )

    current_user.password_hash = hash_password(neues_passwort)
    session.add(current_user)
    await session.commit()
    return templates.TemplateResponse(
        request, "auth/konto.html", {"current_user": current_user, "error": None, "erfolg": True}
    )


@router.get("/konto/export")
async def konto_export(current_user: CurrentUser, session: SessionDep):
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Export ist aktuell nur für Teilnehmer:innen verfügbar.")
    daten = await eigene_daten_export(session, current_user.id)
    inhalt = json.dumps(daten, ensure_ascii=False, indent=2)
    return Response(
        content=inhalt,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=meine-daten.json"},
    )
