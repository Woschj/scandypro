"""Karten-Details: Erstellen/Bearbeiten, Zuweisungen, Unteraufgaben,
Drag&Drop-Persistierung.

Ausgelagert aus app/routers/kanban.py, um die Datei nicht über die in
CLAUDE.md vorgegebene Größenordnung wachsen zu lassen - gleicher Prefix,
gleiche zentrale Zugriffsprüfung über app/core/access.py.
"""

from datetime import date, datetime

from fastapi import APIRouter, Body, Form, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlmodel import select

from app.core.access import boardmitglieder_ids, ist_leiter_von_handlungsfeld, require_kanban_access
from app.core.deps import CurrentUser, SessionDep
from app.models.kanban import Board, BoardTyp, Karte, KartenSichtbarkeit, KartenZuweisung, Spalte, Unteraufgabe
from app.models.user import RoleEnum

router = APIRouter(prefix="/kanban", tags=["kanban"])


async def _board_von_spalte(session: SessionDep, spalte_id: int) -> tuple[Spalte, Board]:
    spalte = await session.get(Spalte, spalte_id)
    if spalte is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    board = await session.get(Board, spalte.board_id)
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return spalte, board


async def _board_von_karte(session: SessionDep, karte_id: int) -> tuple[Karte, Board]:
    karte = await session.get(Karte, karte_id)
    if karte is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    _, board = await _board_von_spalte(session, karte.spalte_id)
    return karte, board


async def _karte_ist_gesperrt(session: SessionDep, karte: Karte) -> bool:
    """Karten in der fest verankerten Erledigt-Spalte (siehe
    app/models/kanban.py:Spalte.ist_system_erledigt) gelten als
    abgeschlossen und sind nicht mehr editierbar - nur das Zurückziehen in
    eine andere Spalte (karte_verschieben/spalte_reihenfolge_setzen) bleibt
    erlaubt und hebt die Sperre auf."""
    spalte = await session.get(Spalte, karte.spalte_id)
    return spalte is not None and spalte.ist_system_erledigt


async def _require_karte_entsperrt(session: SessionDep, karte: Karte) -> None:
    if await _karte_ist_gesperrt(session, karte):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Diese Karte ist erledigt und abgeschlossen. Zum Bearbeiten zurück in eine andere Spalte ziehen.",
        )


@router.post("/boards/{board_id}/spalten/{spalte_id}/karten")
async def karte_erstellen(
    board_id: int,
    spalte_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    titel: str = Form(...),
    beschreibung: str = Form(""),
    faelligkeit: str = Form(""),
    zugewiesene: list[int] = Form(default=[]),
    sichtbarkeit: str = Form("team"),
):
    board = await session.get(Board, board_id)
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    await require_kanban_access(session, current_user, board)

    spalte = await session.get(Spalte, spalte_id)
    if spalte is None or spalte.board_id != board_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    kartensichtbarkeit = KartenSichtbarkeit.team
    if board.typ == BoardTyp.person and current_user.id == board.person_teilnehmer_id:
        kartensichtbarkeit = (
            KartenSichtbarkeit.team if sichtbarkeit == "team" else KartenSichtbarkeit.privat
        )

    erlaubte_zuweisungen = set(await boardmitglieder_ids(session, board))
    ungueltige = [z for z in zugewiesene if z not in erlaubte_zuweisungen]
    if ungueltige:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Zuweisung an eine boardfremde Person nicht möglich.")

    max_reihenfolge_result = await session.execute(
        select(Karte.reihenfolge).where(Karte.spalte_id == spalte_id).order_by(Karte.reihenfolge.desc())
    )
    naechste_reihenfolge = (max_reihenfolge_result.scalars().first() or 0) + 1

    karte = Karte(
        spalte_id=spalte_id,
        titel=titel,
        beschreibung=beschreibung or None,
        faelligkeit=date.fromisoformat(faelligkeit) if faelligkeit else None,
        ersteller_id=current_user.id,
        sichtbarkeit=kartensichtbarkeit,
        reihenfolge=naechste_reihenfolge,
    )
    session.add(karte)
    await session.flush()

    for teilnehmer_id in zugewiesene:
        session.add(KartenZuweisung(karte_id=karte.id, teilnehmer_id=teilnehmer_id))

    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board_id}", status_code=303)


@router.post("/karten/{karte_id}/aktualisieren")
async def karte_aktualisieren(
    karte_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    titel: str = Form(...),
    beschreibung: str = Form(""),
    faelligkeit: str = Form(""),
    sichtbarkeit: str = Form(""),
):
    karte, board = await _board_von_karte(session, karte_id)
    await require_kanban_access(session, current_user, board)
    await _require_karte_entsperrt(session, karte)

    karte.titel = titel
    karte.beschreibung = beschreibung or None
    karte.faelligkeit = date.fromisoformat(faelligkeit) if faelligkeit else None

    if sichtbarkeit and board.typ == BoardTyp.person:
        if current_user.id != board.person_teilnehmer_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Nur die/der Teilnehmer:in selbst ändert die Sichtbarkeit."
            )
        karte.sichtbarkeit = KartenSichtbarkeit.team if sichtbarkeit == "team" else KartenSichtbarkeit.privat

    session.add(karte)
    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board.id}", status_code=303)


async def _darf_karte_loeschen(session: SessionDep, current_user, karte: Karte, board: Board) -> bool:
    """Wer eine Karte löschen darf: die/der Ersteller:in selbst, die
    Handlungsfeld-Leitung eines Team-Boards, oder die/der Owner:in eines
    Personen-Boards (bewusst enger als das ungebundene Bearbeiten von
    Titel/Beschreibung, siehe karte_aktualisieren)."""
    if karte.ersteller_id == current_user.id:
        return True
    if board.typ == BoardTyp.team:
        return current_user.role == RoleEnum.berufstrainer and await ist_leiter_von_handlungsfeld(
            session, current_user.id, board.handlungsfeld_id
        )
    return current_user.id == board.person_teilnehmer_id


@router.post("/karten/{karte_id}/loeschen")
async def karte_loeschen(karte_id: int, current_user: CurrentUser, session: SessionDep):
    karte, board = await _board_von_karte(session, karte_id)
    await require_kanban_access(session, current_user, board)

    if not await _darf_karte_loeschen(session, current_user, karte, board):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Nur die Ersteller:in oder die Board-Verwaltung löscht diese Karte."
        )
    await _require_karte_entsperrt(session, karte)

    for modell in (KartenZuweisung, Unteraufgabe):
        rows = (await session.execute(select(modell).where(modell.karte_id == karte_id))).scalars().all()
        for row in rows:
            await session.delete(row)
    await session.flush()

    await session.delete(karte)
    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board.id}", status_code=303)


@router.post("/karten/{karte_id}/verschieben")
async def karte_verschieben(
    karte_id: int, current_user: CurrentUser, session: SessionDep, ziel_spalte_id: int = Form(...)
):
    karte, board = await _board_von_karte(session, karte_id)
    await require_kanban_access(session, current_user, board)

    ziel_spalte = await session.get(Spalte, ziel_spalte_id)
    if ziel_spalte is None or ziel_spalte.board_id != board.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Zielspalte.")

    max_reihenfolge_result = await session.execute(
        select(Karte.reihenfolge).where(Karte.spalte_id == ziel_spalte_id).order_by(Karte.reihenfolge.desc())
    )
    karte.spalte_id = ziel_spalte_id
    karte.reihenfolge = (max_reihenfolge_result.scalars().first() or 0) + 1
    if ziel_spalte.ist_system_erledigt:
        if karte.abgeschlossen_am is None:
            karte.abgeschlossen_am = datetime.utcnow()
    else:
        karte.abgeschlossen_am = None
    session.add(karte)
    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board.id}", status_code=303)


@router.post("/spalten/{spalte_id}/reihenfolge")
async def spalte_reihenfolge_setzen(
    spalte_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    karten_ids: list[int] = Body(embed=True),
):
    """Persistiert die Kartenreihenfolge nach einem Drag&Drop (siehe
    app/static/js/kanban.js). `karten_ids` ist die vollständige, neue
    Reihenfolge der Karten in dieser Spalte (inkl. ggf. neu hineingezogener
    Karte aus einer anderen Spalte)."""
    ziel_spalte, board = await _board_von_spalte(session, spalte_id)
    await require_kanban_access(session, current_user, board)

    for index, karte_id in enumerate(karten_ids):
        karte = await session.get(Karte, karte_id)
        if karte is None:
            continue
        vorherige_spalte = await session.get(Spalte, karte.spalte_id)
        if vorherige_spalte is None or vorherige_spalte.board_id != board.id:
            continue
        karte.spalte_id = spalte_id
        karte.reihenfolge = index
        if ziel_spalte.ist_system_erledigt:
            if karte.abgeschlossen_am is None:
                karte.abgeschlossen_am = datetime.utcnow()
        else:
            karte.abgeschlossen_am = None
        session.add(karte)

    await session.commit()
    return {"ok": True}


@router.post("/karten/{karte_id}/zuweisungen")
async def zuweisung_hinzufuegen(
    karte_id: int, current_user: CurrentUser, session: SessionDep, teilnehmer_id: int = Form(...)
):
    karte, board = await _board_von_karte(session, karte_id)
    await require_kanban_access(session, current_user, board)
    await _require_karte_entsperrt(session, karte)

    if teilnehmer_id not in await boardmitglieder_ids(session, board):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Zuweisung an eine boardfremde Person nicht möglich.")

    bestehend_result = await session.execute(
        select(KartenZuweisung).where(
            KartenZuweisung.karte_id == karte_id, KartenZuweisung.teilnehmer_id == teilnehmer_id
        )
    )
    if bestehend_result.first() is None:
        session.add(KartenZuweisung(karte_id=karte_id, teilnehmer_id=teilnehmer_id))
        await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board.id}", status_code=303)


@router.post("/karten/{karte_id}/zuweisungen/{zuweisung_id}/entfernen")
async def zuweisung_entfernen(karte_id: int, zuweisung_id: int, current_user: CurrentUser, session: SessionDep):
    karte, board = await _board_von_karte(session, karte_id)
    await require_kanban_access(session, current_user, board)
    await _require_karte_entsperrt(session, karte)

    zuweisung = await session.get(KartenZuweisung, zuweisung_id)
    if zuweisung is None or zuweisung.karte_id != karte_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    await session.delete(zuweisung)
    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board.id}", status_code=303)


@router.post("/karten/{karte_id}/unteraufgaben")
async def unteraufgabe_hinzufuegen(
    karte_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    titel: str = Form(...),
    zugewiesen_an: str = Form(""),
):
    karte, board = await _board_von_karte(session, karte_id)
    await require_kanban_access(session, current_user, board)
    await _require_karte_entsperrt(session, karte)

    zugewiesen_an_id = int(zugewiesen_an) if zugewiesen_an else None
    if zugewiesen_an_id is not None and zugewiesen_an_id not in await boardmitglieder_ids(session, board):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Zuweisung an eine boardfremde Person nicht möglich.")

    max_reihenfolge_result = await session.execute(
        select(Unteraufgabe.reihenfolge).where(Unteraufgabe.karte_id == karte_id).order_by(
            Unteraufgabe.reihenfolge.desc()
        )
    )
    naechste_reihenfolge = (max_reihenfolge_result.scalars().first() or 0) + 1

    session.add(
        Unteraufgabe(
            karte_id=karte_id, titel=titel, zugewiesen_an=zugewiesen_an_id, reihenfolge=naechste_reihenfolge
        )
    )
    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board.id}", status_code=303)


@router.post("/unteraufgaben/{unteraufgabe_id}/umschalten")
async def unteraufgabe_umschalten(unteraufgabe_id: int, current_user: CurrentUser, session: SessionDep):
    unteraufgabe = await session.get(Unteraufgabe, unteraufgabe_id)
    if unteraufgabe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    karte, board = await _board_von_karte(session, unteraufgabe.karte_id)
    await require_kanban_access(session, current_user, board)
    await _require_karte_entsperrt(session, karte)

    unteraufgabe.erledigt = not unteraufgabe.erledigt
    unteraufgabe.erledigt_am = datetime.utcnow() if unteraufgabe.erledigt else None
    session.add(unteraufgabe)
    await session.commit()

    # Für das sanfte "geschafft"-Feedback im Frontend (app/static/js/kanban.js)
    # - true, wenn mit diesem Umschalten JETZT alle Unteraufgaben der Karte
    # erledigt sind (nicht nur diese eine).
    alle_result = await session.execute(
        select(Unteraufgabe.erledigt).where(Unteraufgabe.karte_id == unteraufgabe.karte_id)
    )
    alle_werte = alle_result.scalars().all()
    karte_komplett = bool(alle_werte) and all(alle_werte)

    return {"ok": True, "erledigt": unteraufgabe.erledigt, "karte_komplett": karte_komplett}


@router.post("/unteraufgaben/{unteraufgabe_id}/loeschen")
async def unteraufgabe_loeschen(unteraufgabe_id: int, current_user: CurrentUser, session: SessionDep):
    unteraufgabe = await session.get(Unteraufgabe, unteraufgabe_id)
    if unteraufgabe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    karte, board = await _board_von_karte(session, unteraufgabe.karte_id)
    await require_kanban_access(session, current_user, board)
    await _require_karte_entsperrt(session, karte)

    await session.delete(unteraufgabe)
    await session.commit()
    return RedirectResponse(url=f"/kanban/boards/{board.id}", status_code=303)
