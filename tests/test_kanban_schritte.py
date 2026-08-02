"""Neue Schritte-Definition (siehe app/models/kanban.py:KartenBewegung,
app/core/fortschritt.py:woechentliche_schritte): jede Karte, die eine Person
mindestens einen Schritt weitergezogen hat, zählt - nicht erst bei
vollständigem Abschluss. Rückwärtsbewegungen zählen nicht (aber auch nicht
negativ)."""
from tests.conftest import login


async def _board_mit_drei_spalten(session_maker, teilnehmer_id):
    from app.models.kanban import Board, BoardTyp, Karte, Spalte

    async with session_maker() as session:
        board = Board(
            titel="Meine Aufgaben",
            typ=BoardTyp.person,
            person_teilnehmer_id=teilnehmer_id,
            ersteller_id=teilnehmer_id,
        )
        session.add(board)
        await session.commit()
        await session.refresh(board)

        spalten = []
        for i, name in enumerate(["Offen", "In Arbeit", "Erledigt"]):
            spalte = Spalte(board_id=board.id, name=name, reihenfolge=i, ist_system_erledigt=(name == "Erledigt"))
            session.add(spalte)
            spalten.append(spalte)
        await session.commit()
        for s in spalten:
            await session.refresh(s)

        karte = Karte(spalte_id=spalten[0].id, titel="Testkarte", ersteller_id=teilnehmer_id)
        session.add(karte)
        await session.commit()
        await session.refresh(karte)

        return board, spalten, karte


async def test_vorwaertsbewegung_zaehlt_als_schritt(client, seed_data, session_maker):
    from app.core.fortschritt import woechentliche_schritte

    _, spalten, karte = await _board_mit_drei_spalten(session_maker, seed_data["teilnehmer_id"])
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])

    konto_seite = await client.get("/konto")
    import re

    token = re.search(r'name="csrf_token" value="([^"]+)"', konto_seite.text).group(1)

    resp = await client.post(
        f"/kanban/karten/{karte.id}/verschieben",
        data={"ziel_spalte_id": spalten[1].id, "csrf_token": token},
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        schritte = await woechentliche_schritte(session, seed_data["teilnehmer_id"])
    assert schritte == 1


async def test_rueckwaertsbewegung_zaehlt_nicht_doppelt(client, seed_data, session_maker):
    from app.core.fortschritt import woechentliche_schritte

    _, spalten, karte = await _board_mit_drei_spalten(session_maker, seed_data["teilnehmer_id"])
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])

    konto_seite = await client.get("/konto")
    import re

    token = re.search(r'name="csrf_token" value="([^"]+)"', konto_seite.text).group(1)

    # Vorwärts (Offen -> Erledigt): 1 Schritt
    await client.post(
        f"/kanban/karten/{karte.id}/verschieben",
        data={"ziel_spalte_id": spalten[2].id, "csrf_token": token},
    )
    # Zurückziehen (Erledigt -> Offen), um die Karte wieder bearbeitbar zu
    # machen: darf NICHT als zweiter Schritt gezählt werden.
    await client.post(
        f"/kanban/karten/{karte.id}/verschieben",
        data={"ziel_spalte_id": spalten[0].id, "csrf_token": token},
    )

    async with session_maker() as session:
        schritte = await woechentliche_schritte(session, seed_data["teilnehmer_id"])
    assert schritte == 1
