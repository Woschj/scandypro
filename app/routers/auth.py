import json
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlmodel import select

from app.core.audit import protokolliere
from app.core.config import settings
from app.core.datenexport import eigene_daten_export
from app.core.deps import CurrentUser, SessionDep, verify_csrf
from app.core.rate_limit import ist_gesperrt, registriere_fehlversuch, zuruecksetzen
from app.core.security import hash_password, verify_password
from app.core.templating import templates
from app.models.audit import AuditAktion, AuditZieltyp
from app.models.user import RoleEnum, User

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {
            "error": None,
            "seed_demo_data": settings.seed_demo_data,
            "oidc_enabled": settings.oidc_enabled,
            "oidc_provider_name": settings.oidc_provider_name,
        },
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    session: SessionDep,
    email: str = Form(...),
    password: str = Form(...),
):
    login_kontext = {
        "seed_demo_data": settings.seed_demo_data,
        "oidc_enabled": settings.oidc_enabled,
        "oidc_provider_name": settings.oidc_provider_name,
    }
    client_ip = request.client.host if request.client else "unbekannt"
    if ist_gesperrt(email, client_ip):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Zu viele Versuche. Bitte versuch es in ein paar Minuten noch einmal.", **login_kontext},
            status_code=429,
        )

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or user.password_hash is None or not verify_password(password, user.password_hash):
        registriere_fehlversuch(email, client_ip)
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "E-Mail oder Passwort ist falsch.", **login_kontext},
            status_code=401,
        )
    if not user.aktiv:
        registriere_fehlversuch(email, client_ip)
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {
                "error": "Dieser Account ist aktuell deaktiviert. Wende dich an deine Einrichtung.",
                **login_kontext,
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
    return templates.TemplateResponse(
        request,
        "auth/konto.html",
        {"current_user": current_user, "oidc_provider_name": settings.oidc_provider_name},
    )


@router.post("/konto/stammdaten", response_class=HTMLResponse, dependencies=[Depends(verify_csrf)])
async def stammdaten_aendern(
    request: Request,
    current_user: CurrentUser,
    session: SessionDep,
    name: str = Form(...),
    email: str = Form(...),
    telefon: str = Form(""),
):
    """Berufstrainer:innen, PSM und Admins pflegen ihre eigenen Kontaktdaten
    selbst - Teilnehmer:innen bewusst außen vor, für sie bleiben Name/E-Mail
    Sache der Einrichtungs-Verwaltung (siehe app/routers/admin.py)."""
    if current_user.role == RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    name = name.strip()
    email = email.strip().lower()
    telefon = telefon.strip()
    fehler = None
    if not name:
        fehler = "Name darf nicht leer sein."
    elif not email:
        fehler = "E-Mail darf nicht leer sein."
    elif email != current_user.email:
        vorhanden = await session.execute(select(User).where(User.email == email, User.id != current_user.id))
        if vorhanden.first() is not None:
            fehler = "Diese E-Mail-Adresse wird bereits verwendet."

    if fehler:
        return templates.TemplateResponse(
            request, "auth/konto.html", {"current_user": current_user, "stammdaten_error": fehler}, status_code=400
        )

    current_user.name = name
    current_user.email = email
    current_user.telefon = telefon or None
    session.add(current_user)
    await session.commit()
    return templates.TemplateResponse(
        request, "auth/konto.html", {"current_user": current_user, "erfolg_stammdaten": True}
    )


@router.post("/konto/passwort", response_class=HTMLResponse, dependencies=[Depends(verify_csrf)])
async def passwort_aendern(
    request: Request,
    current_user: CurrentUser,
    session: SessionDep,
    aktuelles_passwort: str = Form(...),
    neues_passwort: str = Form(...),
    neues_passwort_wiederholen: str = Form(...),
):
    # Der Passwortwechsel prüft das *aktuelle* Passwort und ist damit
    # genauso online-bruteforcebar wie der Login - deshalb derselbe
    # Sperrmechanismus (siehe tasks/codebase-audit/README.md, CA-008).
    # Eigener Schlüsselraum ("pw:"-Präfix), damit Fehlversuche hier nicht
    # den regulären Login derselben Person aussperren.
    ip = request.client.host if request.client else "unbekannt"
    sperrschluessel = f"pw:{current_user.email}"
    if ist_gesperrt(sperrschluessel, ip):
        return templates.TemplateResponse(
            request,
            "auth/konto.html",
            {
                "current_user": current_user,
                "passwort_error": "Zu viele Versuche. Bitte warte ein paar Minuten.",
            },
            status_code=429,
        )

    fehler = None
    # SSO-Accounts ohne bisheriges lokales Passwort (siehe app/core/oidc.py)
    # dürfen direkt eines vergeben, ohne ein "aktuelles Passwort" nachweisen
    # zu können, das es noch gar nicht gibt.
    hat_lokales_passwort = current_user.password_hash is not None
    if hat_lokales_passwort and not verify_password(aktuelles_passwort, current_user.password_hash):
        fehler = "Aktuelles Passwort ist falsch."
        registriere_fehlversuch(sperrschluessel, ip)
    elif len(neues_passwort) < 8:
        fehler = "Neues Passwort muss mindestens 8 Zeichen haben."
    elif neues_passwort != neues_passwort_wiederholen:
        fehler = "Die Wiederholung stimmt nicht mit dem neuen Passwort überein."

    if fehler:
        return templates.TemplateResponse(
            request, "auth/konto.html", {"current_user": current_user, "passwort_error": fehler}, status_code=400
        )

    current_user.password_hash = hash_password(neues_passwort)
    session.add(current_user)
    await session.commit()
    zuruecksetzen(sperrschluessel, ip)
    return templates.TemplateResponse(
        request, "auth/konto.html", {"current_user": current_user, "erfolg": True}
    )


@router.get("/konto/export")
async def konto_export(current_user: CurrentUser, session: SessionDep):
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Export ist aktuell nur für Teilnehmer:innen verfügbar.")
    daten = await eigene_daten_export(session, current_user.id)

    # Selbstauskunft nach Art. 15 DSGVO: kein Fremdzugriff, aber der
    # belegrelevanteste Vorgang überhaupt - deshalb protokolliert (siehe
    # tasks/codebase-audit/README.md, CA-002). Akteur und Ziel sind hier
    # dieselbe Person.
    await protokolliere(
        session,
        akteur_id=current_user.id,
        aktion=AuditAktion.daten_exportiert,
        zieltyp=AuditZieltyp.eigene_daten,
        ziel_teilnehmer_id=current_user.id,
    )

    inhalt = json.dumps(daten, ensure_ascii=False, indent=2)
    return Response(
        content=inhalt,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=meine-daten.json"},
    )
