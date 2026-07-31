from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

from app.core.access import require_role
from app.core.deps import CurrentUser, SessionDep
from app.core.templating import templates
from app.models.organisation import (
    Abteilung,
    BerufstrainerZuordnung,
    Handlungsfeld,
    HandlungsfeldLeitung,
    PsmZuordnung,
)
from app.models.user import RoleEnum, User

router = APIRouter(prefix="/admin", tags=["admin"])


async def _require_admin(current_user: CurrentUser) -> None:
    require_role(current_user, RoleEnum.einrichtungs_admin, "Nur die Einrichtungs-Verwaltung darf dies.")


@router.get("/abteilungen", response_class=HTMLResponse)
async def abteilungen_uebersicht(request: Request, current_user: CurrentUser, session: SessionDep):
    await _require_admin(current_user)

    abteilungen_result = await session.execute(select(Abteilung).order_by(Abteilung.name))
    abteilungen = list(abteilungen_result.scalars().all())

    handlungsfelder_result = await session.execute(select(Handlungsfeld))
    handlungsfelder = list(handlungsfelder_result.scalars().all())
    handlungsfelder_by_abteilung: dict[int, list[Handlungsfeld]] = {}
    for h in handlungsfelder:
        handlungsfelder_by_abteilung.setdefault(h.abteilung_id, []).append(h)

    leitungen_result = await session.execute(select(HandlungsfeldLeitung))
    leitungen = list(leitungen_result.scalars().all())
    leitungen_by_handlungsfeld: dict[int, list[HandlungsfeldLeitung]] = {}
    for l in leitungen:
        leitungen_by_handlungsfeld.setdefault(l.handlungsfeld_id, []).append(l)

    trainer_result = await session.execute(select(User).where(User.role == RoleEnum.berufstrainer))
    trainer_by_id = {t.id: t for t in trainer_result.scalars().all()}

    return templates.TemplateResponse(
        request,
        "admin/abteilungen.html",
        {
            "current_user": current_user,
            "abteilungen": abteilungen,
            "handlungsfelder_by_abteilung": handlungsfelder_by_abteilung,
            "leitungen_by_handlungsfeld": leitungen_by_handlungsfeld,
            "trainer_by_id": trainer_by_id,
            "alle_trainer": list(trainer_by_id.values()),
        },
    )


@router.post("/abteilungen")
async def abteilung_erstellen(current_user: CurrentUser, session: SessionDep, name: str = Form(...)):
    await _require_admin(current_user)
    session.add(Abteilung(name=name))
    await session.commit()
    return RedirectResponse(url="/admin/abteilungen", status_code=303)


@router.post("/abteilungen/{abteilung_id}/umbenennen")
async def abteilung_umbenennen(
    abteilung_id: int, current_user: CurrentUser, session: SessionDep, name: str = Form(...)
):
    await _require_admin(current_user)
    abteilung = await session.get(Abteilung, abteilung_id)
    if abteilung is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    abteilung.name = name
    session.add(abteilung)
    await session.commit()
    return RedirectResponse(url="/admin/abteilungen", status_code=303)


@router.post("/handlungsfelder")
async def handlungsfeld_erstellen(
    current_user: CurrentUser, session: SessionDep, name: str = Form(...), abteilung_id: int = Form(...)
):
    await _require_admin(current_user)
    abteilung = await session.get(Abteilung, abteilung_id)
    if abteilung is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unbekannte Abteilung.")
    session.add(Handlungsfeld(name=name, abteilung_id=abteilung_id))
    await session.commit()
    return RedirectResponse(url="/admin/abteilungen", status_code=303)


@router.post("/handlungsfelder/{handlungsfeld_id}/umbenennen")
async def handlungsfeld_umbenennen(
    handlungsfeld_id: int, current_user: CurrentUser, session: SessionDep, name: str = Form(...)
):
    await _require_admin(current_user)
    handlungsfeld = await session.get(Handlungsfeld, handlungsfeld_id)
    if handlungsfeld is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    handlungsfeld.name = name
    session.add(handlungsfeld)
    await session.commit()
    return RedirectResponse(url="/admin/abteilungen", status_code=303)


@router.post("/handlungsfelder/{handlungsfeld_id}/leitung")
async def leitung_hinzufuegen(
    handlungsfeld_id: int, current_user: CurrentUser, session: SessionDep, berufstrainer_id: int = Form(...)
):
    await _require_admin(current_user)
    handlungsfeld = await session.get(Handlungsfeld, handlungsfeld_id)
    trainer = await session.get(User, berufstrainer_id)
    if handlungsfeld is None or trainer is None or trainer.role != RoleEnum.berufstrainer:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültiges Handlungsfeld oder ungültiger Trainer.")

    session.add(HandlungsfeldLeitung(handlungsfeld_id=handlungsfeld_id, berufstrainer_id=berufstrainer_id))
    await session.commit()
    return RedirectResponse(url="/admin/abteilungen", status_code=303)


@router.post("/handlungsfelder/{handlungsfeld_id}/leitung/{leitung_id}/entfernen")
async def leitung_entfernen(handlungsfeld_id: int, leitung_id: int, current_user: CurrentUser, session: SessionDep):
    await _require_admin(current_user)
    leitung = await session.get(HandlungsfeldLeitung, leitung_id)
    if leitung is None or leitung.handlungsfeld_id != handlungsfeld_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.delete(leitung)
    await session.commit()
    return RedirectResponse(url="/admin/abteilungen", status_code=303)


@router.get("/psm-zuordnungen", response_class=HTMLResponse)
async def psm_zuordnungen_uebersicht(request: Request, current_user: CurrentUser, session: SessionDep):
    await _require_admin(current_user)

    zuordnungen_result = await session.execute(select(PsmZuordnung))
    zuordnungen = list(zuordnungen_result.scalars().all())

    psm_result = await session.execute(select(User).where(User.role == RoleEnum.psychosoziale_mitarbeit))
    alle_psm = list(psm_result.scalars().all())

    teilnehmer_result = await session.execute(select(User).where(User.role == RoleEnum.teilnehmer))
    alle_teilnehmer = list(teilnehmer_result.scalars().all())
    user_by_id = {u.id: u for u in alle_psm + alle_teilnehmer}

    return templates.TemplateResponse(
        request,
        "admin/psm_zuordnungen.html",
        {
            "current_user": current_user,
            "zuordnungen": zuordnungen,
            "alle_psm": alle_psm,
            "alle_teilnehmer": alle_teilnehmer,
            "user_by_id": user_by_id,
        },
    )


@router.post("/psm-zuordnungen")
async def psm_zuordnung_erstellen(
    current_user: CurrentUser, session: SessionDep, psm_id: int = Form(...), teilnehmer_id: int = Form(...)
):
    await _require_admin(current_user)
    psm = await session.get(User, psm_id)
    teilnehmer = await session.get(User, teilnehmer_id)
    if psm is None or psm.role != RoleEnum.psychosoziale_mitarbeit:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige PSM-Auswahl.")
    if teilnehmer is None or teilnehmer.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Teilnehmer-Auswahl.")

    session.add(PsmZuordnung(psm_id=psm_id, teilnehmer_id=teilnehmer_id))
    await session.commit()
    return RedirectResponse(url="/admin/psm-zuordnungen", status_code=303)


@router.post("/psm-zuordnungen/{zuordnung_id}/entfernen")
async def psm_zuordnung_entfernen(zuordnung_id: int, current_user: CurrentUser, session: SessionDep):
    await _require_admin(current_user)
    zuordnung = await session.get(PsmZuordnung, zuordnung_id)
    if zuordnung is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.delete(zuordnung)
    await session.commit()
    return RedirectResponse(url="/admin/psm-zuordnungen", status_code=303)


@router.get("/trainer-zuordnungen", response_class=HTMLResponse)
async def trainer_zuordnungen_uebersicht(request: Request, current_user: CurrentUser, session: SessionDep):
    await _require_admin(current_user)

    zuordnungen_result = await session.execute(select(BerufstrainerZuordnung))
    zuordnungen = list(zuordnungen_result.scalars().all())

    trainer_result = await session.execute(select(User).where(User.role == RoleEnum.berufstrainer))
    alle_trainer = list(trainer_result.scalars().all())

    teilnehmer_result = await session.execute(select(User).where(User.role == RoleEnum.teilnehmer))
    alle_teilnehmer = list(teilnehmer_result.scalars().all())
    user_by_id = {u.id: u for u in alle_trainer + alle_teilnehmer}

    return templates.TemplateResponse(
        request,
        "admin/trainer_zuordnungen.html",
        {
            "current_user": current_user,
            "zuordnungen": zuordnungen,
            "alle_trainer": alle_trainer,
            "alle_teilnehmer": alle_teilnehmer,
            "user_by_id": user_by_id,
        },
    )


@router.post("/trainer-zuordnungen")
async def trainer_zuordnung_erstellen(
    current_user: CurrentUser, session: SessionDep, berufstrainer_id: int = Form(...), teilnehmer_id: int = Form(...)
):
    await _require_admin(current_user)
    trainer = await session.get(User, berufstrainer_id)
    teilnehmer = await session.get(User, teilnehmer_id)
    if trainer is None or trainer.role != RoleEnum.berufstrainer:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Trainer-Auswahl.")
    if teilnehmer is None or teilnehmer.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Teilnehmer-Auswahl.")

    session.add(BerufstrainerZuordnung(berufstrainer_id=berufstrainer_id, teilnehmer_id=teilnehmer_id))
    await session.commit()
    return RedirectResponse(url="/admin/trainer-zuordnungen", status_code=303)


@router.post("/trainer-zuordnungen/{zuordnung_id}/entfernen")
async def trainer_zuordnung_entfernen(zuordnung_id: int, current_user: CurrentUser, session: SessionDep):
    await _require_admin(current_user)
    zuordnung = await session.get(BerufstrainerZuordnung, zuordnung_id)
    if zuordnung is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await session.delete(zuordnung)
    await session.commit()
    return RedirectResponse(url="/admin/trainer-zuordnungen", status_code=303)
