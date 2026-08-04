from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

from app.core.access import (
    betreute_teilnehmer_ids,
    boardmitglieder_ids,
    geleitete_handlungsfeld_ids,
    ist_leiter_von_handlungsfeld,
    ist_mitglied_von_handlungsfeld,
    ist_zustaendiger_trainer,
    kann_board_verwalten,
    require_board_verwaltung,
    require_kanban_access,
    require_role,
    sichtbare_board_ids_fuer_teilnehmer,
    sichtbare_karten_filter,
)
from app.core.deletion import (
    loesche_board_kaskadierend,
    loesche_spalte_kaskadierend,
    loesche_teilnehmergruppe_kaskadierend,
)
from app.core.deps import CurrentUser, SessionDep, verify_csrf
from app.core.templating import templates
from app.models.bewerbung import BewerbungsFreigabe
from app.models.kanban import Board, BoardFreigabe, BoardTyp, Karte, KartenZuweisung, Spalte, Unteraufgabe
from app.models.organisation import (
    Abteilung,
    BerufstrainerZuordnung,
    Handlungsfeld,
    HandlungsfeldMitglied,
    Teilnehmergruppe,
    TeilnehmergruppeMitglied,
)
from app.models.user import RoleEnum, User

router = APIRouter(prefix="/kanban", tags=["kanban"], dependencies=[Depends(verify_csrf)])

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
    letzter_index = len(STANDARD_SPALTEN) - 1
    for i, name in enumerate(STANDARD_SPALTEN):
        session.add(Spalte(board_id=board.id, name=name, reihenfolge=i, ist_system_erledigt=i == letzter_index))
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


async def _require_zustaendiger_trainer_fuer(
    session: SessionDep, current_user: User, teilnehmer_id: int
) -> User:
    """Gemeinsame Zugriffsprüfung für die Teilnehmer:innen-Perspektive auf
    Kanban-Boards (siehe teilnehmer_boards_liste/board_teilnehmer_ansicht):
    nur die/der persönlich zugeordnete Berufstrainer:in darf sich ansehen,
    was eine/ein Teilnehmer:in selbst an Boards sehen kann."""
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer:innen sehen Boards aus Teilnehmer:innen-Perspektive.")
    teilnehmer = await session.get(User, teilnehmer_id)
    if teilnehmer is None or teilnehmer.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not await ist_zustaendiger_trainer(session, current_user.id, teilnehmer_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du bist dieser/diesem Teilnehmer:in nicht zugeordnet.")
    return teilnehmer


@router.get("/teilnehmer/{teilnehmer_id}/boards", response_class=HTMLResponse)
async def teilnehmer_boards_liste(
    request: Request, teilnehmer_id: int, current_user: CurrentUser, session: SessionDep
):
    """Alle Kanban-Boards aus der Perspektive einer/eines zugeordneten
    Teilnehmer:in - alle öffentlichen Team-Boards, die für sie/ihn über
    Arbeitsgruppe, Handlungsfeld oder individuelle Freigabe sichtbar sind
    (siehe sichtbare_board_ids_fuer_teilnehmer), plus das eigene
    Personen-Board. Bewusst NICHT auf die Handlungsfelder beschränkt, die
    die/der betrachtende Trainer:in selbst leitet - reine Leseansicht, kein
    Aktionsangebot, das über require_kanban_access ohnehin nicht
    durchginge."""
    teilnehmer = await _require_zustaendiger_trainer_fuer(session, current_user, teilnehmer_id)
    await _hole_oder_erstelle_personenboard(session, teilnehmer_id)

    board_ids = await sichtbare_board_ids_fuer_teilnehmer(session, teilnehmer_id)
    boards: list[Board] = []
    if board_ids:
        boards_result = await session.execute(select(Board).where(Board.id.in_(board_ids)))
        boards = list(boards_result.scalars().all())
    boards.sort(key=lambda b: (b.typ != BoardTyp.person, b.titel))

    handlungsfeld_ids = {b.handlungsfeld_id for b in boards if b.handlungsfeld_id is not None}
    handlungsfeld_by_id: dict[int, Handlungsfeld] = {}
    if handlungsfeld_ids:
        hf_result = await session.execute(select(Handlungsfeld).where(Handlungsfeld.id.in_(handlungsfeld_ids)))
        handlungsfeld_by_id = {h.id: h for h in hf_result.scalars().all()}

    return templates.TemplateResponse(
        request,
        "kanban/teilnehmer_boards.html",
        {
            "current_user": current_user,
            "teilnehmer": teilnehmer,
            "boards": boards,
            "handlungsfeld_by_id": handlungsfeld_by_id,
        },
    )


@router.get("/teilnehmer/{teilnehmer_id}/boards/{board_id}", response_class=HTMLResponse)
async def board_teilnehmer_ansicht(
    request: Request, teilnehmer_id: int, board_id: int, current_user: CurrentUser, session: SessionDep
):
    """Reine Leseansicht eines einzelnen Boards aus der
    Teilnehmer:innen-Perspektive (siehe teilnehmer_boards_liste) - eigenes,
    formularloses Template statt kanban/board.html, damit keine Aktionen
    angeboten werden, die die eigentlichen Mutations-Routen (weiterhin nur
    für Handlungsfeld-Leitung bzw. Board-Mitglieder, siehe
    require_kanban_access/require_board_verwaltung) ohnehin ablehnen
    würden. Die Karten-Sichtbarkeitsfilterung bleibt bewusst an
    current_user (die/der betrachtende Trainer:in) gebunden, nicht an
    teilnehmer - private Karten der/des Teilnehmer:in bleiben ihr/ihm auch
    hier vorbehalten (siehe karte_ist_sichtbar_fuer)."""
    teilnehmer = await _require_zustaendiger_trainer_fuer(session, current_user, teilnehmer_id)

    board = await session.get(Board, board_id)
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    sichtbare_ids = await sichtbare_board_ids_fuer_teilnehmer(session, teilnehmer_id)
    if board_id not in sichtbare_ids:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Dieses Board ist für diese/diesen Teilnehmer:in nicht sichtbar.")

    kontext = await _board_kontext(session, current_user, board)

    return templates.TemplateResponse(
        request,
        "kanban/board_teilnehmer_ansicht.html",
        {
            "current_user": current_user,
            "teilnehmer": teilnehmer,
            "k": kontext,
        },
    )


@router.post("/boards")
async def board_erstellen(
    current_user: CurrentUser,
    session: SessionDep,
    titel: str = Form(...),
    handlungsfeld_id: int = Form(...),
):
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer:innen legen Boards an.")
    if not await ist_leiter_von_handlungsfeld(session, current_user.id, handlungsfeld_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur die Leitung eines Handlungsfelds legt dort Boards an.")

    board = Board(
        titel=titel, typ=BoardTyp.team, handlungsfeld_id=handlungsfeld_id, ersteller_id=current_user.id
    )
    session.add(board)
    await session.flush()
    letzter_index = len(STANDARD_SPALTEN) - 1
    for i, name in enumerate(STANDARD_SPALTEN):
        session.add(Spalte(board_id=board.id, name=name, reihenfolge=i, ist_system_erledigt=i == letzter_index))
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

    # Zuweisungen/Unteraufgaben können auf Personen verweisen, die seither aus
    # der Arbeitsgruppe/dem Handlungsfeld entfernt wurden und daher nicht mehr
    # in boardmitglieder stehen - für die Anzeige (Name/Avatar) brauchen wir
    # sie trotzdem, ohne sie erneut zuweisbar zu machen.
    referenzierte_ids: set[int] = set(boardmitglieder_ids_liste)
    for zuweisungen in zuweisungen_by_karte.values():
        referenzierte_ids.update(z.teilnehmer_id for z in zuweisungen)
    for unteraufgaben in unteraufgaben_by_karte.values():
        referenzierte_ids.update(u.zugewiesen_an for u in unteraufgaben if u.zugewiesen_an is not None)
    fehlende_ids = referenzierte_ids - boardmitglieder.keys()
    anzeige_personen = dict(boardmitglieder)
    if fehlende_ids:
        fehlende_result = await session.execute(select(User).where(User.id.in_(fehlende_ids)))
        anzeige_personen.update({u.id: u for u in fehlende_result.scalars().all()})

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
        "anzeige_personen": anzeige_personen,
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
    # Freigabe-Verwaltung ist Board-Verwaltung (nicht nur "irgendeine
    # berufstrainende Person auf einem Team-Board") - bisher implizit über
    # require_kanban_access korrekt (das ließ auf Team-Boards für
    # Berufstrainer:innen ohnehin nur die Handlungsfeld-Leitung durch),
    # jetzt explizit über kann_board_verwalten geprüft, um nicht auf diese
    # Zufälligkeit angewiesen zu sein.
    if board.typ == BoardTyp.team and await kann_board_verwalten(session, current_user, board):
        alle_freigaben_result = await session.execute(select(BoardFreigabe).where(BoardFreigabe.board_id == board_id))
        alle_freigaben = list(alle_freigaben_result.scalars().all())

        gruppen_ids = {f.gruppe_id for f in alle_freigaben if f.gruppe_id is not None}
        teilnehmer_ids = {f.teilnehmer_id for f in alle_freigaben if f.teilnehmer_id is not None}
        hat_handlungsfeld_freigabe = any(f.handlungsfeld_id is not None for f in alle_freigaben)

        gruppe_by_id: dict[int, Teilnehmergruppe] = {}
        if gruppen_ids:
            gruppen_result = await session.execute(select(Teilnehmergruppe).where(Teilnehmergruppe.id.in_(gruppen_ids)))
            gruppe_by_id = {g.id: g for g in gruppen_result.scalars().all()}

        teilnehmer_by_id: dict[int, User] = {}
        if teilnehmer_ids:
            teilnehmer_result = await session.execute(select(User).where(User.id.in_(teilnehmer_ids)))
            teilnehmer_by_id = {t.id: t for t in teilnehmer_result.scalars().all()}

        freigaben_anzeige = []
        for f in alle_freigaben:
            if f.gruppe_id is not None:
                ziel_label = f"Arbeitsgruppe: {gruppe_by_id[f.gruppe_id].name}" if f.gruppe_id in gruppe_by_id else "Arbeitsgruppe"
            elif f.handlungsfeld_id is not None:
                ziel_label = "Ganzes Handlungsfeld"
            else:
                ziel_label = f"Person: {teilnehmer_by_id[f.teilnehmer_id].name}" if f.teilnehmer_id in teilnehmer_by_id else "Person"
            freigaben_anzeige.append({"freigabe": f, "ziel_label": ziel_label})

        gruppen_hf_result = await session.execute(
            select(Teilnehmergruppe).where(Teilnehmergruppe.handlungsfeld_id == board.handlungsfeld_id)
        )
        verfuegbare_gruppen = [g for g in gruppen_hf_result.scalars().all() if g.id not in gruppen_ids]

        hf_mitglieder_result = await session.execute(
            select(User)
            .join(HandlungsfeldMitglied, HandlungsfeldMitglied.teilnehmer_id == User.id)
            .where(HandlungsfeldMitglied.handlungsfeld_id == board.handlungsfeld_id)
            .order_by(User.name)
        )
        verfuegbare_teilnehmer = [t for t in hf_mitglieder_result.scalars().all() if t.id not in teilnehmer_ids]

        freigaben_kontext = {
            "freigaben": freigaben_anzeige,
            "verfuegbare_gruppen": verfuegbare_gruppen,
            "verfuegbare_teilnehmer": verfuegbare_teilnehmer,
            "hat_handlungsfeld_freigabe": hat_handlungsfeld_freigabe,
        }

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

    erledigt_result = await session.execute(
        select(Spalte).where(Spalte.board_id == board_id, Spalte.ist_system_erledigt == True)  # noqa: E712
    )
    erledigt_spalte = erledigt_result.scalar_one_or_none()

    if erledigt_spalte is not None:
        # Neue Spalten landen immer vor der fixierten Erledigt-Spalte (siehe
        # CLAUDE.md Abschnitt 25 "positive Verstärkung" / Konzept-Entscheidung:
        # Erledigt bleibt strukturell das Ende jedes Boards).
        neue_reihenfolge = erledigt_spalte.reihenfolge
        erledigt_spalte.reihenfolge += 1
        session.add(erledigt_spalte)
    else:
        max_result = await session.execute(
            select(Spalte.reihenfolge).where(Spalte.board_id == board_id).order_by(Spalte.reihenfolge.desc())
        )
        neue_reihenfolge = (max_result.scalars().first() or -1) + 1

    session.add(Spalte(board_id=board_id, name=name, reihenfolge=neue_reihenfolge))
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

    if spalte.ist_system_erledigt:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Die Erledigt-Spalte ist fest verankert und kann nicht gelöscht werden.")

    anzahl_spalten = list((await session.execute(select(Spalte.id).where(Spalte.board_id == board.id))).scalars().all())
    if len(anzahl_spalten) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ein Board braucht mindestens eine Spalte.")

    await loesche_spalte_kaskadierend(session, spalte_id)
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

    await loesche_board_kaskadierend(session, board_id)
    await session.commit()
    return RedirectResponse(url="/kanban", status_code=303)


@router.post("/boards/{board_id}/freigaben")
async def freigabe_erstellen(
    board_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    ziel_typ: str = Form(...),
    ziel_id: str = Form(""),
):
    """Gibt ein Team-Board für eine von drei Zielarten frei (siehe
    app/models/kanban.py:BoardFreigabe): eine einzelne Arbeitsgruppe, das
    ganze Handlungsfeld (dann ist `ziel_id` irrelevant - es gibt nur das
    eine Handlungsfeld des Boards) oder eine einzelne Person aus dem
    Handlungsfeld."""
    board = await session.get(Board, board_id)
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not await ist_leiter_von_handlungsfeld(session, current_user.id, board.handlungsfeld_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur die Leitung des Handlungsfelds verwaltet Freigaben.")

    if ziel_typ == "gruppe":
        gruppe_id = int(ziel_id) if ziel_id else None
        gruppe = await session.get(Teilnehmergruppe, gruppe_id) if gruppe_id is not None else None
        if gruppe is None or gruppe.handlungsfeld_id != board.handlungsfeld_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Gruppe gehört nicht zum Handlungsfeld des Boards.")
        session.add(BoardFreigabe(board_id=board_id, gruppe_id=gruppe_id))
    elif ziel_typ == "handlungsfeld":
        session.add(BoardFreigabe(board_id=board_id, handlungsfeld_id=board.handlungsfeld_id))
    elif ziel_typ == "teilnehmer":
        teilnehmer_id = int(ziel_id) if ziel_id else None
        teilnehmer = await session.get(User, teilnehmer_id) if teilnehmer_id is not None else None
        if teilnehmer is None or teilnehmer.role != RoleEnum.teilnehmer:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Teilnehmer-Auswahl.")
        if not await ist_mitglied_von_handlungsfeld(session, teilnehmer_id, board.handlungsfeld_id):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Diese Person gehört nicht zum Handlungsfeld des Boards."
            )
        session.add(BoardFreigabe(board_id=board_id, teilnehmer_id=teilnehmer_id))
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültiger Freigabe-Typ.")

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


@router.get("/teilnehmer", response_class=HTMLResponse)
async def meine_teilnehmer(request: Request, current_user: CurrentUser, session: SessionDep):
    """"Meine Teilnehmer:innen" für Berufstrainer:innen - bewusst NUR
    persönlich zugeordnete Teilnehmer:innen (BerufstrainerZuordnung), nicht
    alle Mitglieder eines geleiteten Handlungsfelds: ein Handlungsfeld kann
    deutlich mehr Mitglieder haben, als diese/dieser Trainer:in tatsächlich
    persönlich betreut (siehe app/routers/admin.py:trainer_zuordnungen_uebersicht
    für die organisatorische Zuordnung selbst) - eine ungefilterte Liste war
    dadurch irreführend. Die Handlungsfeld-Zugehörigkeit bleibt trotzdem als
    Info-Spalte sichtbar, bestimmt aber nicht mehr, wer in der Liste
    auftaucht."""
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer:innen haben eine Teilnehmer:innen-Übersicht.")

    zuordnung_result = await session.execute(
        select(BerufstrainerZuordnung).where(BerufstrainerZuordnung.berufstrainer_id == current_user.id)
    )
    persoenlich_zugeordnet_ids = {z.teilnehmer_id for z in zuordnung_result.scalars().all()}

    geleitete_ids = await geleitete_handlungsfeld_ids(session, current_user.id)
    handlungsfeld_by_id: dict[int, Handlungsfeld] = {}
    if geleitete_ids:
        hf_result = await session.execute(select(Handlungsfeld).where(Handlungsfeld.id.in_(geleitete_ids)))
        handlungsfeld_by_id = {h.id: h for h in hf_result.scalars().all()}

    hf_mitglied_handlungsfelder: dict[int, list[str]] = {}
    if geleitete_ids and persoenlich_zugeordnet_ids:
        hf_mitglieder_result = await session.execute(
            select(HandlungsfeldMitglied).where(
                HandlungsfeldMitglied.handlungsfeld_id.in_(geleitete_ids),
                HandlungsfeldMitglied.teilnehmer_id.in_(persoenlich_zugeordnet_ids),
            )
        )
        for m in hf_mitglieder_result.scalars().all():
            hf_mitglied_handlungsfelder.setdefault(m.teilnehmer_id, []).append(
                handlungsfeld_by_id[m.handlungsfeld_id].name
            )

    teilnehmer_liste: list[User] = []
    abteilung_by_id: dict[int, Abteilung] = {}
    if persoenlich_zugeordnet_ids:
        teilnehmer_result = await session.execute(
            select(User).where(User.id.in_(persoenlich_zugeordnet_ids)).order_by(User.name)
        )
        teilnehmer_liste = list(teilnehmer_result.scalars().all())
        abteilungs_ids = {t.abteilung_id for t in teilnehmer_liste if t.abteilung_id is not None}
        if abteilungs_ids:
            abteilung_result = await session.execute(select(Abteilung).where(Abteilung.id.in_(abteilungs_ids)))
            abteilung_by_id = {a.id: a for a in abteilung_result.scalars().all()}

    wochenbericht_sichtbar_ids = set(await betreute_teilnehmer_ids(session, current_user.id))

    heute = date.today()
    bewerbung_freigabe_ids: set[int] = set()
    if persoenlich_zugeordnet_ids:
        freigaben_result = await session.execute(
            select(BewerbungsFreigabe).where(
                BewerbungsFreigabe.empfaenger_id == current_user.id,
                BewerbungsFreigabe.teilnehmer_id.in_(persoenlich_zugeordnet_ids),
                BewerbungsFreigabe.widerrufen_am.is_(None),
            )
        )
        for freigabe in freigaben_result.scalars().all():
            if freigabe.gueltig_bis is None or freigabe.gueltig_bis >= heute:
                bewerbung_freigabe_ids.add(freigabe.teilnehmer_id)

    return templates.TemplateResponse(
        request,
        "kanban/teilnehmer.html",
        {
            "current_user": current_user,
            "teilnehmer_liste": teilnehmer_liste,
            "abteilung_by_id": abteilung_by_id,
            "hf_mitglied_handlungsfelder": hf_mitglied_handlungsfelder,
            "persoenlich_zugeordnet_ids": persoenlich_zugeordnet_ids,
            "wochenbericht_sichtbar_ids": wochenbericht_sichtbar_ids,
            "bewerbung_freigabe_ids": bewerbung_freigabe_ids,
        },
    )


@router.get("/gruppen", response_class=HTMLResponse)
async def gruppen_liste(
    request: Request, current_user: CurrentUser, session: SessionDep, handlungsfeld_id: str | None = None
):
    """`handlungsfeld_id` kommt als Query-Parameter aus einem <select> im
    Template (siehe kanban/gruppen.html) - bei der leeren Platzhalter-Option
    wird ein leerer String statt gar keinem Parameter gesendet, daher hier
    als str entgegennehmen und selbst zu int|None konvertieren, statt
    FastAPI direkt int|None parsen zu lassen (das wirft bei "" einen 422)."""
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer:innen verwalten Handlungsfeld-Teams.")
    handlungsfeld_id = int(handlungsfeld_id) if handlungsfeld_id else None

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
    gruppe_mitglied_id_by_teilnehmer: dict[int, dict[int, int]] = {}
    for m in mitglieder:
        mitglieder_by_gruppe.setdefault(m.gruppe_id, []).append(m.teilnehmer_id)
        gruppe_mitglied_id_by_teilnehmer.setdefault(m.gruppe_id, {})[m.teilnehmer_id] = m.id

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
            "gruppe_mitglied_id_by_teilnehmer": gruppe_mitglied_id_by_teilnehmer,
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
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer:innen verwalten Handlungsfeld-Mitglieder.")
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
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer:innen verwalten Handlungsfeld-Mitglieder.")
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
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer:innen verwalten Arbeitsgruppen.")
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


async def _hole_eigene_gruppe(session: SessionDep, current_user: User, gruppe_id: int) -> Teilnehmergruppe:
    """Lädt eine Arbeitsgruppe und prüft, dass current_user das zugehörige
    Handlungsfeld leitet - gemeinsame Berechtigungsprüfung für Umbenennen/
    Löschen/Mitgliederverwaltung einer bestehenden Gruppe."""
    require_role(current_user, RoleEnum.berufstrainer, "Nur Berufstrainer:innen verwalten Arbeitsgruppen.")
    gruppe = await session.get(Teilnehmergruppe, gruppe_id)
    if gruppe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not await ist_leiter_von_handlungsfeld(session, current_user.id, gruppe.handlungsfeld_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Du leitest dieses Handlungsfeld nicht.")
    return gruppe


@router.post("/gruppen/{gruppe_id}/umbenennen")
async def gruppe_umbenennen(gruppe_id: int, current_user: CurrentUser, session: SessionDep, name: str = Form(...)):
    gruppe = await _hole_eigene_gruppe(session, current_user, gruppe_id)
    gruppe.name = name
    session.add(gruppe)
    await session.commit()
    return RedirectResponse(url=f"/kanban/gruppen?handlungsfeld_id={gruppe.handlungsfeld_id}", status_code=303)


@router.post("/gruppen/{gruppe_id}/mitglieder")
async def gruppe_mitglied_hinzufuegen(
    gruppe_id: int, current_user: CurrentUser, session: SessionDep, teilnehmer_id: int = Form(...)
):
    gruppe = await _hole_eigene_gruppe(session, current_user, gruppe_id)
    if not await ist_mitglied_von_handlungsfeld(session, teilnehmer_id, gruppe.handlungsfeld_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Person gehört nicht zum Handlungsfeld dieser Gruppe.")

    vorhanden = await session.execute(
        select(TeilnehmergruppeMitglied).where(
            TeilnehmergruppeMitglied.gruppe_id == gruppe_id,
            TeilnehmergruppeMitglied.teilnehmer_id == teilnehmer_id,
        )
    )
    if vorhanden.first() is None:
        session.add(TeilnehmergruppeMitglied(gruppe_id=gruppe_id, teilnehmer_id=teilnehmer_id))
        await session.commit()
    return RedirectResponse(url=f"/kanban/gruppen?handlungsfeld_id={gruppe.handlungsfeld_id}", status_code=303)


@router.post("/gruppen/{gruppe_id}/mitglieder/{mitglied_id}/entfernen")
async def gruppe_mitglied_entfernen(gruppe_id: int, mitglied_id: int, current_user: CurrentUser, session: SessionDep):
    gruppe = await _hole_eigene_gruppe(session, current_user, gruppe_id)
    mitglied = await session.get(TeilnehmergruppeMitglied, mitglied_id)
    if mitglied is None or mitglied.gruppe_id != gruppe_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    await session.delete(mitglied)
    await session.commit()
    return RedirectResponse(url=f"/kanban/gruppen?handlungsfeld_id={gruppe.handlungsfeld_id}", status_code=303)


@router.post("/gruppen/{gruppe_id}/loeschen")
async def gruppe_loeschen(gruppe_id: int, current_user: CurrentUser, session: SessionDep):
    gruppe = await _hole_eigene_gruppe(session, current_user, gruppe_id)
    handlungsfeld_id = gruppe.handlungsfeld_id
    await loesche_teilnehmergruppe_kaskadierend(session, gruppe_id)
    return RedirectResponse(url=f"/kanban/gruppen?handlungsfeld_id={handlungsfeld_id}", status_code=303)
