from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

from app.core.deps import CurrentUser, SessionDep, verify_csrf
from app.core.security import hash_password, verify_password
from app.core.templating import templates
from app.models.user import User

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse(request, "auth/login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    session: SessionDep,
    email: str = Form(...),
    password: str = Form(...),
):
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "E-Mail oder Passwort ist falsch."},
            status_code=401,
        )
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
