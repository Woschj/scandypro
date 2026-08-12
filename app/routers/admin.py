from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import func, select

from urllib.parse import quote

from app.core.access import require_role
from app.core.deletion import loesche_konto_vollstaendig
from app.core.deps import CurrentUser, SessionDep, verify_csrf
from app.core.security import hash_password
from app.core.templating import templates
from app.models.organisation import (
    Abteilung,
    BerufstrainerZuordnung,
    Handlungsfeld,
    HandlungsfeldLeitung,
    PsmZuordnung,
)
from app.models.user import RoleEnum, User

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_csrf)])


async def _require_admin(current_user: CurrentUser) -> None:
    require_role(current_user, RoleEnum.einrichtungs_admin, "Nur die Einrichtungs-Verwaltung darf dies.")


@router.get("/abteilungen", response_class=HTMLResponse)
async def abteilungen_uebersicht(
    request: Request, current_user: CurrentUser, session: SessionDep, fehler: str | None = None
):
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
    for leitung in leitungen:
        leitungen_by_handlungsfeld.setdefault(leitung.handlungsfeld_id, []).append(leitung)

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
            "fehler": fehler,
        },
    )


@router.post("/abteilungen")
async def abteilung_erstellen(current_user: CurrentUser, session: SessionDep, name: str = Form(...)):
    await _require_admin(current_user)
    vorhandene = await session.execute(select(Abteilung).where(Abteilung.name == name.strip()))
    if vorhandene.scalars().first() is not None:
        return RedirectResponse(
            url="/admin/abteilungen?fehler=Eine+Abteilung+mit+diesem+Namen+existiert+bereits.", status_code=303
        )
    session.add(Abteilung(name=name.strip()))
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
    name_bereinigt = name.strip()
    vorhandene = await session.execute(
        select(Handlungsfeld).where(
            Handlungsfeld.abteilung_id == abteilung_id,
            func.lower(Handlungsfeld.name) == name_bereinigt.lower(),
        )
    )
    if vorhandene.scalars().first() is not None:
        return RedirectResponse(
            url="/admin/abteilungen?fehler=In+dieser+Abteilung+gibt+es+bereits+ein+Handlungsfeld+mit+diesem+Namen.",
            status_code=303,
        )
    session.add(Handlungsfeld(name=name_bereinigt, abteilung_id=abteilung_id))
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
    name_bereinigt = name.strip()
    vorhandene = await session.execute(
        select(Handlungsfeld).where(
            Handlungsfeld.abteilung_id == handlungsfeld.abteilung_id,
            Handlungsfeld.id != handlungsfeld_id,
            func.lower(Handlungsfeld.name) == name_bereinigt.lower(),
        )
    )
    if vorhandene.scalars().first() is not None:
        return RedirectResponse(
            url="/admin/abteilungen?fehler=In+dieser+Abteilung+gibt+es+bereits+ein+Handlungsfeld+mit+diesem+Namen.",
            status_code=303,
        )
    handlungsfeld.name = name_bereinigt
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültiges Handlungsfeld oder ungültige Berufstrainer:in.")

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

    psm_result = await session.execute(
        select(User).where(User.role == RoleEnum.psychosoziale_mitarbeit).order_by(User.name)
    )
    alle_psm = list(psm_result.scalars().all())

    teilnehmer_result = await session.execute(
        select(User).where(User.role == RoleEnum.teilnehmer).order_by(User.name)
    )
    alle_teilnehmer = list(teilnehmer_result.scalars().all())
    user_by_id = {u.id: u for u in alle_psm + alle_teilnehmer}

    teilnehmer_ids_by_psm: dict[int, list[int]] = {}
    zuordnung_id_by_psm_teilnehmer: dict[int, dict[int, int]] = {}
    for z in zuordnungen:
        teilnehmer_ids_by_psm.setdefault(z.psm_id, []).append(z.teilnehmer_id)
        zuordnung_id_by_psm_teilnehmer.setdefault(z.psm_id, {})[z.teilnehmer_id] = z.id

    return templates.TemplateResponse(
        request,
        "admin/psm_zuordnungen.html",
        {
            "current_user": current_user,
            "alle_psm": alle_psm,
            "alle_teilnehmer": alle_teilnehmer,
            "user_by_id": user_by_id,
            "teilnehmer_ids_by_psm": teilnehmer_ids_by_psm,
            "zuordnung_id_by_psm_teilnehmer": zuordnung_id_by_psm_teilnehmer,
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Auswahl der psychosozialen Mitarbeiter:in.")
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

    trainer_result = await session.execute(
        select(User).where(User.role == RoleEnum.berufstrainer).order_by(User.name)
    )
    alle_trainer = list(trainer_result.scalars().all())

    teilnehmer_result = await session.execute(
        select(User).where(User.role == RoleEnum.teilnehmer).order_by(User.name)
    )
    alle_teilnehmer = list(teilnehmer_result.scalars().all())
    user_by_id = {u.id: u for u in alle_trainer + alle_teilnehmer}

    teilnehmer_ids_by_trainer: dict[int, list[int]] = {}
    zuordnung_id_by_trainer_teilnehmer: dict[int, dict[int, int]] = {}
    for z in zuordnungen:
        teilnehmer_ids_by_trainer.setdefault(z.berufstrainer_id, []).append(z.teilnehmer_id)
        zuordnung_id_by_trainer_teilnehmer.setdefault(z.berufstrainer_id, {})[z.teilnehmer_id] = z.id

    return templates.TemplateResponse(
        request,
        "admin/trainer_zuordnungen.html",
        {
            "current_user": current_user,
            "alle_trainer": alle_trainer,
            "alle_teilnehmer": alle_teilnehmer,
            "user_by_id": user_by_id,
            "teilnehmer_ids_by_trainer": teilnehmer_ids_by_trainer,
            "zuordnung_id_by_trainer_teilnehmer": zuordnung_id_by_trainer_teilnehmer,
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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Berufstrainer:in-Auswahl.")
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


@router.get("/benutzer", response_class=HTMLResponse)
async def benutzer_uebersicht(
    request: Request, current_user: CurrentUser, session: SessionDep, hinweis: str | None = None
):
    await _require_admin(current_user)

    benutzer_result = await session.execute(select(User).order_by(User.name))
    benutzer = list(benutzer_result.scalars().all())

    abteilungen_result = await session.execute(select(Abteilung).order_by(Abteilung.name))
    abteilungen = list(abteilungen_result.scalars().all())
    abteilung_by_id = {a.id: a for a in abteilungen}

    rollen_reihenfolge = [
        RoleEnum.teilnehmer,
        RoleEnum.berufstrainer,
        RoleEnum.psychosoziale_mitarbeit,
        RoleEnum.einrichtungs_admin,
    ]
    benutzer_by_rolle: dict[RoleEnum | None, list[User]] = {rolle: [] for rolle in rollen_reihenfolge}
    for b in benutzer:
        # b.role ist nur bei per SSO neu angelegten, noch nicht
        # freigeschalteten Accounts None - landet dadurch als eigene Gruppe
        # am Ende (siehe app/core/oidc.py, app/templates/admin/benutzer.html).
        benutzer_by_rolle.setdefault(b.role, []).append(b)

    return templates.TemplateResponse(
        request,
        "admin/benutzer.html",
        {
            "current_user": current_user,
            "benutzer": benutzer,
            "benutzer_by_rolle": benutzer_by_rolle,
            "abteilungen": abteilungen,
            "abteilung_by_id": abteilung_by_id,
            "hinweis": hinweis,
        },
    )


@router.post("/benutzer")
async def benutzer_erstellen(
    current_user: CurrentUser,
    session: SessionDep,
    name: str = Form(...),
    email: str = Form(...),
    passwort: str = Form(...),
    rolle: RoleEnum = Form(...),
    abteilung_id: str = Form(""),
    telefon: str = Form(""),
):
    await _require_admin(current_user)

    name = name.strip()
    email_norm = email.strip().lower()
    if not name or not email_norm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Name und E-Mail sind Pflichtfelder.")
    if len(passwort) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Passwort muss mindestens 8 Zeichen haben.")

    existing = await session.execute(select(User).where(User.email == email_norm))
    if existing.first() is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Diese E-Mail wird bereits verwendet.")

    abteilung_id_wert: int | None = None
    if abteilung_id:
        abteilung = await session.get(Abteilung, int(abteilung_id))
        if abteilung is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Abteilung.")
        abteilung_id_wert = abteilung.id

    session.add(
        User(
            name=name,
            email=email_norm,
            password_hash=hash_password(passwort),
            role=rolle,
            abteilung_id=abteilung_id_wert,
            telefon=telefon.strip() or None,
        )
    )
    await session.commit()
    return RedirectResponse(url="/admin/benutzer", status_code=303)


@router.get("/benutzer/{benutzer_id}/bearbeiten", response_class=HTMLResponse)
async def benutzer_bearbeiten_form(
    request: Request,
    benutzer_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    fehler: str | None = None,
    erfolg: str | None = None,
):
    await _require_admin(current_user)

    benutzer = await session.get(User, benutzer_id)
    if benutzer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    abteilungen_result = await session.execute(select(Abteilung).order_by(Abteilung.name))
    abteilungen = list(abteilungen_result.scalars().all())

    return templates.TemplateResponse(
        request,
        "admin/benutzer_bearbeiten.html",
        {
            "current_user": current_user,
            "benutzer": benutzer,
            "abteilungen": abteilungen,
            "ist_eigener_account": benutzer.id == current_user.id,
            "fehler": fehler,
            "erfolg": erfolg,
        },
    )


@router.post("/benutzer/{benutzer_id}/bearbeiten")
async def benutzer_bearbeiten(
    request: Request,
    benutzer_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    name: str = Form(...),
    email: str = Form(...),
    rolle: RoleEnum = Form(...),
    abteilung_id: str = Form(""),
    telefon: str = Form(""),
):
    await _require_admin(current_user)

    benutzer = await session.get(User, benutzer_id)
    if benutzer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    if benutzer.id == current_user.id and rolle != benutzer.role:
        return RedirectResponse(
            url=f"/admin/benutzer/{benutzer_id}/bearbeiten?fehler=Du+kannst+deine+eigene+Rolle+nicht+ändern.",
            status_code=303,
        )

    name = name.strip()
    email_norm = email.strip().lower()
    if not name or not email_norm:
        return RedirectResponse(
            url=f"/admin/benutzer/{benutzer_id}/bearbeiten?fehler=Name+und+E-Mail+sind+Pflichtfelder.",
            status_code=303,
        )

    existing = await session.execute(select(User).where(User.email == email_norm, User.id != benutzer_id))
    if existing.first() is not None:
        return RedirectResponse(
            url=f"/admin/benutzer/{benutzer_id}/bearbeiten?fehler=Diese+E-Mail+wird+bereits+verwendet.",
            status_code=303,
        )

    abteilung_id_wert: int | None = None
    if abteilung_id:
        abteilung = await session.get(Abteilung, int(abteilung_id))
        if abteilung is None:
            return RedirectResponse(
                url=f"/admin/benutzer/{benutzer_id}/bearbeiten?fehler=Ungültige+Abteilung.", status_code=303
            )
        abteilung_id_wert = abteilung.id

    benutzer.name = name
    benutzer.email = email_norm
    benutzer.role = rolle
    benutzer.abteilung_id = abteilung_id_wert
    benutzer.telefon = telefon.strip() or None
    session.add(benutzer)
    await session.commit()
    return RedirectResponse(url="/admin/benutzer", status_code=303)


@router.post("/benutzer/{benutzer_id}/aktiv-umschalten")
async def benutzer_aktiv_umschalten(benutzer_id: int, current_user: CurrentUser, session: SessionDep):
    await _require_admin(current_user)

    benutzer = await session.get(User, benutzer_id)
    if benutzer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if benutzer.id == current_user.id:
        return RedirectResponse(
            url=f"/admin/benutzer/{benutzer_id}/bearbeiten?fehler=Du+kannst+deinen+eigenen+Account+nicht+deaktivieren.",
            status_code=303,
        )
    if not benutzer.aktiv and benutzer.role is None:
        return RedirectResponse(
            url=f"/admin/benutzer/{benutzer_id}/bearbeiten?fehler=Bitte+zuerst+eine+Rolle+zuweisen+und+speichern.",
            status_code=303,
        )

    benutzer.aktiv = not benutzer.aktiv
    session.add(benutzer)
    await session.commit()
    return RedirectResponse(url=f"/admin/benutzer/{benutzer_id}/bearbeiten?erfolg=aktiv", status_code=303)


@router.post("/benutzer/{benutzer_id}/passwort-zuruecksetzen")
async def benutzer_passwort_zuruecksetzen(
    benutzer_id: int, current_user: CurrentUser, session: SessionDep, neues_passwort: str = Form(...)
):
    await _require_admin(current_user)

    benutzer = await session.get(User, benutzer_id)
    if benutzer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    if len(neues_passwort) < 8:
        return RedirectResponse(
            url=f"/admin/benutzer/{benutzer_id}/bearbeiten?fehler=Passwort+muss+mindestens+8+Zeichen+haben.",
            status_code=303,
        )

    benutzer.password_hash = hash_password(neues_passwort)
    session.add(benutzer)
    await session.commit()
    return RedirectResponse(url=f"/admin/benutzer/{benutzer_id}/bearbeiten?erfolg=passwort", status_code=303)


BESTAETIGUNGSWORT_KONTO = "KONTO LÖSCHEN"


@router.post("/benutzer/{benutzer_id}/loeschen")
async def benutzer_loeschen(
    benutzer_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    bestaetigung: str = Form(""),
):
    """Vollständige Konto-Löschung nach Art. 17 DSGVO (PR-005).

    Eigene Inhalte (Tagebuch, Bewerbungen, Wochenberichte, persönliches
    Board) verschwinden. Karten auf Team-Boards bleiben bewusst stehen -
    dort arbeiten andere weiter, und die Leitung entscheidet selbst, ob eine
    verwaiste Aufgabe neu zugewiesen oder entfernt wird (siehe
    app/core/deletion.py:loesche_konto_vollstaendig).
    """
    await _require_admin(current_user)

    benutzer = await session.get(User, benutzer_id)
    if benutzer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    if benutzer.id == current_user.id:
        return RedirectResponse(
            url=f"/admin/benutzer/{benutzer_id}/bearbeiten?fehler=Du+kannst+dein+eigenes+Konto+nicht+löschen.",
            status_code=303,
        )

    if bestaetigung.strip() != BESTAETIGUNGSWORT_KONTO:
        return RedirectResponse(
            url=f"/admin/benutzer/{benutzer_id}/bearbeiten"
            f"?fehler=Zum+Löschen+bitte+genau+„{BESTAETIGUNGSWORT_KONTO}“+eintippen.",
            status_code=303,
        )

    bilanz = await loesche_konto_vollstaendig(session, benutzer_id)

    hinweis = (
        f"Konto gelöscht. {bilanz['karten_ohne_zustaendige']} Karte(n) auf Team-Boards "
        f"haben jetzt keine Zuständigen mehr und brauchen eine Entscheidung."
    )
    if bilanz["handlungsfelder_ohne_leitung"]:
        hinweis += f" {bilanz['handlungsfelder_ohne_leitung']} Handlungsfeld(er) sind ohne Leitung."
    return RedirectResponse(url=f"/admin/benutzer?hinweis={quote(hinweis)}", status_code=303)
