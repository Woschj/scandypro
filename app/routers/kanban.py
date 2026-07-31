from datetime import date

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

from app.core.access import (
    boardmitglieder_ids,
    geleitete_handlungsfeld_ids,
    ist_leiter_von_handlungsfeld,
    ist_mitglied_von_handlungsfeld,
    ist_zustaendiger_trainer,
    kann_board_verwalten,
    require_board_verwaltung,
    require_kanban_access,
    require_role,
    sichtbare_karten_filter,
)
from app.core.deps import CurrentUser, SessionDep
from app.core.templating import templates
from app.models.kanban import Board, BoardFreigabe, BoardTyp, Karte, KartenZuweisung, Spalte, Unteraufgabe
from app.models.organisation import (
    Handlungsfeld,
    HandlungsfeldMitglied,
    Teilnehmergruppe,
    TeilnehmergruppeMitglied,
)
from app.models.user import RoleEnum, User

router = APIRouter(prefix="/kanban", tags=["kanban"])

STANDARD_SPALTEN = ["Offen", "In Arbeit", "Wartet", "Erledigt"]


async def _sichtbare_boards(session: SessionDep, current_user: User) -> list[Board]:
    if current_user.role == RoleEnum.berufstrainer:
        handlungsfeld_ids = await geleitete_handlungsfeld_ids(session, current_user.id)
        boards: list[Board] = []
        if handlungsfeld_ids:
            result = await session.execute(
                select(Board)
                .where(Board.typ == BoardTyp.team, Board.handlungsfeld_id.in_(handlungsfeld_ids))
                .order_by(Board.erstellt_am.desc())
            )
            boards.extend(result.scalars().all())
        return boards
    if current_user.role == RoleEnum.teilnehmer:
        result = await session.execute(
            select(Board)
            .join(BoardFreigabe, BoardFreigabe.board_id == Board.id)
            .join(
                TeilnehmergruppeMitglied,
                TeilnehmergruppeMitglied.gruppe_id == BoardFreigabe.gruppe_id,
            )
            .where(Board.typ == BoardTyp.team, TeilnehmergruppeMitglied.teilnehmer_id == current_user.id)
            .distinct()
        )
        return list(result.scalars().all())
    return []


async def _hole_oder_erstelle_personenboard(session: SessionDep, teilnehmer_id: int) -> Board:
    result = await session.execute(
        select(Board).where(Board.typ == BoardTyp.person, Board.person_teilnehmer_id == teilnehmer_id)
    )
    board = result.scalar_one_or_none()
    if board is not None:
        return board

    board = Board(
        titel="Meine Aufgaben",
        typ=BoardTyp.person,
        person_teilnehmer_id=teilnehmer_id,
        ersteller_id=teilnehmer_id,
    )
    session.add(board)
    await session.flush()
    for i, name in enumerate(STANDARD_SPALTEN):
        session.add(Spalte(board_id=board.id, name=name, reihenfolge=i))
    await session.commit()
    await session.refresh(board)
    return board


@router.get("", response_class=HTMLResponse)
async def board_liste(request: Request, current_user: CurrentUser, session: SessionDep):
    boards = await _sichtbare_boards(session, current_user)

    board_kontexte = []
    if current_user.role == RoleEnum.teilnehmer:
        persoenliches_board = await _hole_oder_erstelle_personenboard(session, current_user.id)
        board_kontexte.append(await _board_kontext(session, current_user, persoenliches_board))
    for board in boards:
        board_kontexte.append(await _board_kontext(session, current_user, board))

    handlungsfelder_result = await session.execute(select(Handlungsfeld))
    handlungsfeld_by_id = {h.id: h for h in handlungsfelder_result.scalars().all()}

    eigene_handlungsfelder = []
    if current_user.role == RoleEnum.berufstrainer:
        geleitete_ids = await geleitete_handlungsfeld_ids(session, current_user.id)
        eigene_handlungsfelder = [handlungsfeld_by_id[hid] for hid in geleitete_ids if hid in handlungsfeld_by_id]

    return templates.TemplateResponse(
        request,
        "kanban/liste.html",
        {
            "board_kontexte": board_kontexte,
            "handlungsfeld_by_id": handlungsfeld_by_id,
            "eigene_handlungsfelder": eigene_handlungsfelder,
            "current_user": current_user,
        },
    )


@router.get("/meine-aufgaben")
async def meine_aufgaben(current_user: CurrentUser, session: SessionDep):
    require_role(current_user, RoleEnum.teilnehmer, "Nur Teilnehmer:innen haben ein persönliches Aufgaben-Board.")
    board = await _hole_oder_erstelle_personenboard(session, current_user.id)
    return RedirectResponse(url=f"/kanban/boards/{board.id}", status_code=303)


@router.get("/boards/personen/{teilnehmer_id}")
async def personen_board_oeffnen(teilnehmer_id: int, current_user: CurrentUser, session: SessionDep):
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer öffnen fremde Personen-Boards.")
    teilnehmer = await session.get(User, teilnehmer_id)
    if teilnehmer is None or teilnehmer.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not await ist_zustaendiger_trainer(session, current_user.id, teilnehmer_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du bist dieser/diesem Teilnehmer:in nicht zugeordnet.")

    board = await _hole_oder_erstelle_personenboard(session, teilnehmer_id)
    return RedirectResponse(url=f"/kanban/boards/{board.id}", status_code=303)


@router.post("/boards")
async def board_erstellen(
    current_user: CurrentUser,
    session: SessionDep,
    titel: str = Form(...),
    handlungsfeld_id: int = Form(...),
):
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer legen Boards an.")
    if not await ist_leiter_von_handlungsfeld(session, current_user.id, handlungsfeld_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur die Leitung eines Handlungsfelds legt dort Boards an.")

    board = Board(
        titel=titel, typ=BoardTyp.team, handlungsfeld_id=handlungsfeld_id, ersteller_id=current_user.id
    )
    session.add(board)
    await session.flush()
    for i, name in enumerate(STANDARD_SPALTEN):
        session.add(Spalte(board_id=board.id, name=name, reihenfolge=i))
    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board.id}", status_code=303)


async def _board_kontext(session: SessionDep, current_user: User, board: Board) -> dict:
    """Baut den kompletten Render-Kontext eines Boards (Spalten, Karten,
    Zuweisungen, Unteraufgaben, Boardmitglieder) - gemeinsam genutzt von der
    Einzel-Board-Seite und der Board-Übersicht (dort alle Boards direkt mit
    vollen Spalten aufgeklappt, siehe app/templates/kanban/liste.html)."""
    spalten_result = await session.execute(
        select(Spalte).where(Spalte.board_id == board.id).order_by(Spalte.reihenfolge)
    )
    spalten = list(spalten_result.scalars().all())

    karten_by_spalte: dict[int, list[Karte]] = {s.id: [] for s in spalten}
    alle_karten: list[Karte] = []
    if spalten:
        karten_result = await session.execute(
            select(Karte).where(Karte.spalte_id.in_(karten_by_spalte.keys())).order_by(Karte.reihenfolge)
        )
        alle_karten = list(karten_result.scalars().all())

    sichtbare_karten = sichtbare_karten_filter(current_user, board, alle_karten)
    for karte in sichtbare_karten:
        karten_by_spalte.setdefault(karte.spalte_id, []).append(karte)
    sichtbare_karten_ids = {k.id for k in sichtbare_karten}

    zuweisungen_by_karte: dict[int, list[KartenZuweisung]] = {}
    unteraufgaben_by_karte: dict[int, list[Unteraufgabe]] = {}
    if sichtbare_karten_ids:
        zuweisungen_result = await session.execute(
            select(KartenZuweisung).where(KartenZuweisung.karte_id.in_(sichtbare_karten_ids))
        )
        for z in zuweisungen_result.scalars().all():
            zuweisungen_by_karte.setdefault(z.karte_id, []).append(z)

        unteraufgaben_result = await session.execute(
            select(Unteraufgabe)
            .where(Unteraufgabe.karte_id.in_(sichtbare_karten_ids))
            .order_by(Unteraufgabe.reihenfolge)
        )
        for u in unteraufgaben_result.scalars().all():
            unteraufgaben_by_karte.setdefault(u.karte_id, []).append(u)

    boardmitglieder_ids_liste = await boardmitglieder_ids(session, board)
    boardmitglieder: dict[int, User] = {}
    if boardmitglieder_ids_liste:
        mitglieder_result = await session.execute(select(User).where(User.id.in_(boardmitglieder_ids_liste)))
        boardmitglieder = {u.id: u for u in mitglieder_result.scalars().all()}

    handlungsfeld = None
    if board.handlungsfeld_id is not None:
        handlungsfeld = await session.get(Handlungsfeld, board.handlungsfeld_id)

    darf_sichtbarkeit_aendern = board.typ == BoardTyp.person and current_user.id == board.person_teilnehmer_id

    return {
        "board": board,
        "handlungsfeld": handlungsfeld,
        "spalten": spalten,
        "karten_by_spalte": karten_by_spalte,
        "zuweisungen_by_karte": zuweisungen_by_karte,
        "unteraufgaben_by_karte": unteraufgaben_by_karte,
        "boardmitglieder": boardmitglieder,
        "darf_sichtbarkeit_aendern": darf_sichtbarkeit_aendern,
        "darf_board_verwalten": await kann_board_verwalten(session, current_user, board),
        "heute": date.today(),
    }


@router.get("/boards/{board_id}", response_class=HTMLResponse)
async def board_detail(request: Request, board_id: int, current_user: CurrentUser, session: SessionDep):
    board = await session.get(Board, board_id)
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await require_kanban_access(session, current_user, board)

    kontext = await _board_kontext(session, current_user, board)

    freigaben_kontext = None
    if board.typ == BoardTyp.team and current_user.role == RoleEnum.berufstrainer:
        freigaben_result = await session.execute(
            select(BoardFreigabe, Teilnehmergruppe)
            .join(Teilnehmergruppe, Teilnehmergruppe.id == BoardFreigabe.gruppe_id)
            .where(BoardFreigabe.board_id == board_id)
        )
        freigaben = [(f, g) for f, g in freigaben_result.all()]
        freigegebene_gruppen_ids = {g.id for _, g in freigaben}

        gruppen_result = await session.execute(
            select(Teilnehmergruppe).where(Teilnehmergruppe.handlungsfeld_id == board.handlungsfeld_id)
        )
        verfuegbare_gruppen = [
            g for g in gruppen_result.scalars().all() if g.id not in freigegebene_gruppen_ids
        ]
        freigaben_kontext = {"freigaben": freigaben, "verfuegbare_gruppen": verfuegbare_gruppen}

    return templates.TemplateResponse(
        request,
        "kanban/board.html",
        {
            "current_user": current_user,
            "k": kontext,
            "freigaben_kontext": freigaben_kontext,
        },
    )


@router.post("/boards/{board_id}/spalten")
async def spalte_erstellen(board_id: int, current_user: CurrentUser, session: SessionDep, name: str = Form(...)):
    board = await session.get(Board, board_id)
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await require_board_verwaltung(session, current_user, board)

    max_result = await session.execute(
        select(Spalte.reihenfolge).where(Spalte.board_id == board_id).order_by(Spalte.reihenfolge.desc())
    )
    naechste_reihenfolge = (max_result.scalars().first() or -1) + 1
    session.add(Spalte(board_id=board_id, name=name, reihenfolge=naechste_reihenfolge))
    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board_id}", status_code=303)


@router.post("/spalten/{spalte_id}/umbenennen")
async def spalte_umbenennen(spalte_id: int, current_user: CurrentUser, session: SessionDep, name: str = Form(...)):
    spalte = await session.get(Spalte, spalte_id)
    if spalte is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    board = await session.get(Board, spalte.board_id)
    await require_board_verwaltung(session, current_user, board)

    spalte.name = name
    session.add(spalte)
    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board.id}", status_code=303)


@router.post("/spalten/{spalte_id}/loeschen")
async def spalte_loeschen(spalte_id: int, current_user: CurrentUser, session: SessionDep):
    spalte = await session.get(Spalte, spalte_id)
    if spalte is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    board = await session.get(Board, spalte.board_id)
    await require_board_verwaltung(session, current_user, board)

    anzahl_spalten = list((await session.execute(select(Spalte.id).where(Spalte.board_id == board.id))).scalars().all())
    if len(anzahl_spalten) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ein Board braucht mindestens eine Spalte.")

    karten = list((await session.execute(select(Karte).where(Karte.spalte_id == spalte_id))).scalars().all())
    karten_ids = [k.id for k in karten]
    if karten_ids:
        for modell in (KartenZuweisung, Unteraufgabe):
            rows = list((await session.execute(select(modell).where(modell.karte_id.in_(karten_ids)))).scalars().all())
            for row in rows:
                await session.delete(row)
        await session.flush()
        for karte in karten:
            await session.delete(karte)
        await session.flush()

    await session.delete(spalte)
    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board.id}", status_code=303)


@router.post("/boards/{board_id}/loeschen")
async def board_loeschen(board_id: int, current_user: CurrentUser, session: SessionDep):
    board = await session.get(Board, board_id)
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if board.typ != BoardTyp.team:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Persönliche Boards können nicht gelöscht werden.")
    await require_board_verwaltung(session, current_user, board)

    spalten = list((await session.execute(select(Spalte).where(Spalte.board_id == board_id))).scalars().all())
    spalten_ids = [s.id for s in spalten]
    if spalten_ids:
        karten = list((await session.execute(select(Karte).where(Karte.spalte_id.in_(spalten_ids)))).scalars().all())
        karten_ids = [k.id for k in karten]
        if karten_ids:
            for modell in (KartenZuweisung, Unteraufgabe):
                rows = list(
                    (await session.execute(select(modell).where(modell.karte_id.in_(karten_ids)))).scalars().all()
                )
                for row in rows:
                    await session.delete(row)
            await session.flush()
            for karte in karten:
                await session.delete(karte)
            await session.flush()
        for spalte in spalten:
            await session.delete(spalte)
        await session.flush()

    freigaben = list(
        (await session.execute(select(BoardFreigabe).where(BoardFreigabe.board_id == board_id))).scalars().all()
    )
    for freigabe in freigaben:
        await session.delete(freigabe)
    await session.flush()

    await session.delete(board)
    await session.commit()
    return RedirectResponse(url="/kanban", status_code=303)


@router.post("/boards/{board_id}/freigaben")
async def freigabe_erstellen(
    board_id: int, current_user: CurrentUser, session: SessionDep, gruppe_id: int = Form(...)
):
    board = await session.get(Board, board_id)
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not await ist_leiter_von_handlungsfeld(session, current_user.id, board.handlungsfeld_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur die Leitung des Handlungsfelds verwaltet Freigaben.")

    gruppe = await session.get(Teilnehmergruppe, gruppe_id)
    if gruppe is None or gruppe.handlungsfeld_id != board.handlungsfeld_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Gruppe gehört nicht zum Handlungsfeld des Boards.")

    session.add(BoardFreigabe(board_id=board_id, gruppe_id=gruppe_id))
    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board_id}", status_code=303)


@router.post("/boards/{board_id}/freigaben/{freigabe_id}/entfernen")
async def freigabe_entfernen(board_id: int, freigabe_id: int, current_user: CurrentUser, session: SessionDep):
    board = await session.get(Board, board_id)
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not await ist_leiter_von_handlungsfeld(session, current_user.id, board.handlungsfeld_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur die Leitung des Handlungsfelds verwaltet Freigaben.")

    freigabe = await session.get(BoardFreigabe, freigabe_id)
    if freigabe is None or freigabe.board_id != board_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    await session.delete(freigabe)
    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board_id}", status_code=303)


@router.get("/gruppen", response_class=HTMLResponse)
async def gruppen_liste(
    request: Request, current_user: CurrentUser, session: SessionDep, handlungsfeld_id: int | None = None
):
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer verwalten Handlungsfeld-Teams.")

    geleitete_ids = await geleitete_handlungsfeld_ids(session, current_user.id)
    handlungsfelder_result = await session.execute(select(Handlungsfeld).where(Handlungsfeld.id.in_(geleitete_ids)))
    eigene_handlungsfelder = list(handlungsfelder_result.scalars().all())

    if handlungsfeld_id is not None and handlungsfeld_id not in geleitete_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du leitest dieses Handlungsfeld nicht.")

    gruppen_result = await session.execute(
        select(Teilnehmergruppe).where(Teilnehmergruppe.handlungsfeld_id.in_(geleitete_ids))
    )
    gruppen = list(gruppen_result.scalars().all())
    handlungsfeld_by_id = {h.id: h for h in eigene_handlungsfelder}

    mitglieder_result = await session.execute(select(TeilnehmergruppeMitglied))
    mitglieder = list(mitglieder_result.scalars().all())
    mitglieder_by_gruppe: dict[int, list[int]] = {}
    for m in mitglieder:
        mitglieder_by_gruppe.setdefault(m.gruppe_id, []).append(m.teilnehmer_id)

    teilnehmer_result = await session.execute(select(User).where(User.role == RoleEnum.teilnehmer))
    alle_teilnehmer = list(teilnehmer_result.scalars().all())
    teilnehmer_by_id = {t.id: t for t in alle_teilnehmer}

    hf_mitglieder_result = await session.execute(
        select(HandlungsfeldMitglied).where(HandlungsfeldMitglied.handlungsfeld_id.in_(geleitete_ids))
    )
    hf_mitglieder = list(hf_mitglieder_result.scalars().all())
    hf_mitglied_teilnehmer_ids: dict[int, set[int]] = {}
    hf_mitglied_id_by_teilnehmer: dict[int, int] = {}
    for m in hf_mitglieder:
        hf_mitglied_teilnehmer_ids.setdefault(m.handlungsfeld_id, set()).add(m.teilnehmer_id)
        if m.handlungsfeld_id == handlungsfeld_id:
            hf_mitglied_id_by_teilnehmer[m.teilnehmer_id] = m.id

    auswahl_teilnehmer = []
    abteilungs_teilnehmer = []
    if handlungsfeld_id is not None:
        ziel_abteilung_id = handlungsfeld_by_id[handlungsfeld_id].abteilung_id
        abteilungs_teilnehmer = [t for t in alle_teilnehmer if t.abteilung_id == ziel_abteilung_id]
        hf_mitglieder_ids = hf_mitglied_teilnehmer_ids.get(handlungsfeld_id, set())
        auswahl_teilnehmer = [t for t in abteilungs_teilnehmer if t.id in hf_mitglieder_ids]

    return templates.TemplateResponse(
        request,
        "kanban/gruppen.html",
        {
            "current_user": current_user,
            "eigene_handlungsfelder": eigene_handlungsfelder,
            "gruppen": gruppen,
            "handlungsfeld_by_id": handlungsfeld_by_id,
            "mitglieder_by_gruppe": mitglieder_by_gruppe,
            "teilnehmer_by_id": teilnehmer_by_id,
            "ausgewaehltes_handlungsfeld_id": handlungsfeld_id,
            "auswahl_teilnehmer": auswahl_teilnehmer,
            "abteilungs_teilnehmer": abteilungs_teilnehmer,
            "hf_mitglied_teilnehmer_ids": hf_mitglied_teilnehmer_ids.get(handlungsfeld_id, set())
            if handlungsfeld_id is not None
            else set(),
            "hf_mitglied_id_by_teilnehmer": hf_mitglied_id_by_teilnehmer,
        },
    )


@router.post("/handlungsfelder/{handlungsfeld_id}/mitglieder")
async def hf_mitglied_hinzufuegen(
    handlungsfeld_id: int, current_user: CurrentUser, session: SessionDep, teilnehmer_id: int = Form(...)
):
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer verwalten Handlungsfeld-Mitglieder.")
    if not await ist_leiter_von_handlungsfeld(session, current_user.id, handlungsfeld_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du leitest dieses Handlungsfeld nicht.")

    handlungsfeld = await session.get(Handlungsfeld, handlungsfeld_id)
    teilnehmer = await session.get(User, teilnehmer_id)
    if handlungsfeld is None or teilnehmer is None or teilnehmer.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültiges Handlungsfeld oder ungültige:r Teilnehmer:in.")
    if teilnehmer.abteilung_id != handlungsfeld.abteilung_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Teilnehmer:in gehört nicht zur Abteilung des Handlungsfelds.")

    if not await ist_mitglied_von_handlungsfeld(session, teilnehmer_id, handlungsfeld_id):
        session.add(HandlungsfeldMitglied(handlungsfeld_id=handlungsfeld_id, teilnehmer_id=teilnehmer_id))
        await session.commit()
    return RedirectResponse(url=f"/kanban/gruppen?handlungsfeld_id={handlungsfeld_id}", status_code=303)


@router.post("/handlungsfelder/{handlungsfeld_id}/mitglieder/{mitglied_id}/entfernen")
async def hf_mitglied_entfernen(
    handlungsfeld_id: int, mitglied_id: int, current_user: CurrentUser, session: SessionDep
):
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer verwalten Handlungsfeld-Mitglieder.")
    if not await ist_leiter_von_handlungsfeld(session, current_user.id, handlungsfeld_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du leitest dieses Handlungsfeld nicht.")

    mitglied = await session.get(HandlungsfeldMitglied, mitglied_id)
    if mitglied is None or mitglied.handlungsfeld_id != handlungsfeld_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    gruppen_result = await session.execute(
        select(Teilnehmergruppe.id).where(Teilnehmergruppe.handlungsfeld_id == handlungsfeld_id)
    )
    gruppen_ids = list(gruppen_result.scalars().all())
    if gruppen_ids:
        zugehoerigkeit_result = await session.execute(
            select(TeilnehmergruppeMitglied).where(
                TeilnehmergruppeMitglied.gruppe_id.in_(gruppen_ids),
                TeilnehmergruppeMitglied.teilnehmer_id == mitglied.teilnehmer_id,
            )
        )
        for zugehoerigkeit in zugehoerigkeit_result.scalars().all():
            await session.delete(zugehoerigkeit)

    await session.delete(mitglied)
    await session.commit()
    return RedirectResponse(url=f"/kanban/gruppen?handlungsfeld_id={handlungsfeld_id}", status_code=303)


@router.post("/gruppen")
async def gruppe_erstellen(
    current_user: CurrentUser,
    session: SessionDep,
    name: str = Form(...),
    handlungsfeld_id: int = Form(...),
    mitglieder: list[int] = Form(default=[]),
):
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer verwalten Arbeitsgruppen.")
    if not await ist_leiter_von_handlungsfeld(session, current_user.id, handlungsfeld_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du leitest dieses Handlungsfeld nicht.")

    handlungsfeld = await session.get(Handlungsfeld, handlungsfeld_id)
    if handlungsfeld is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unbekanntes Handlungsfeld.")

    gruppe = Teilnehmergruppe(name=name, handlungsfeld_id=handlungsfeld_id, erstellt_von=current_user.id)
    session.add(gruppe)
    await session.flush()

    for teilnehmer_id in mitglieder:
        if not await ist_mitglied_von_handlungsfeld(session, teilnehmer_id, handlungsfeld_id):
            continue
        session.add(TeilnehmergruppeMitglied(gruppe_id=gruppe.id, teilnehmer_id=teilnehmer_id))

    await session.commit()
    return RedirectResponse(url=f"/kanban/gruppen?handlungsfeld_id={handlungsfeld_id}", status_code=303)
