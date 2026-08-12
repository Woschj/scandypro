"""Tests der vollständigen Konto-Löschung (PR-005, Art. 17 DSGVO).

Die Löschung muss zwei gegenläufige Dinge zugleich leisten:

- **Vollständig sein.** Bleibt irgendwo ein Rest der Person übrig, ist das
  Löschverlangen nicht erfüllt. Getestet wird deshalb tabellenweise, nicht
  nur "der Login geht nicht mehr".
- **Fremde Arbeit nicht zerstören.** Auf Team-Boards arbeiten andere
  Menschen weiter. Deren Karten dürfen nicht verschwinden, nur weil eine
  Person das Haus verlässt - sie sollen stattdessen unzugewiesen
  auffallen, damit die Leitung sie neu vergeben oder entfernen kann.

Der zweite Punkt ist der, an dem eine naive Kaskaden-Löschung Schaden
anrichten würde, und deshalb der Schwerpunkt hier.
"""
import re

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlmodel import select

from app.core.deletion import loesche_konto_vollstaendig
from app.core.security import hash_password
from app.models.audit import AuditAktion, AuditLogEintrag, AuditZieltyp
from app.models.bewerbung import Bewerbung, BewerbungStatus
from app.models.kanban import (
    Board,
    BoardTyp,
    Karte,
    KartenBewegung,
    KartenZuweisung,
    Spalte,
)
from app.models.organisation import (
    BerufstrainerZuordnung,
    Handlungsfeld,
    PsmZuordnung,
    Teilnehmergruppe,
    TeilnehmergruppeMitglied,
)
from app.models.user import RoleEnum, User
from app.models.wochenbericht import Wochenbericht, WochenberichtStatus, leere_tage
from app.models.wohlbefinden import TagebuchEintrag
from tests.conftest import login

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORT = "adminpass123"
KOLLEGE_EMAIL = "kollege@test.local"
KOLLEGE_PASSWORT = "kollegepass123"


async def _csrf_token(client: AsyncClient) -> str:
    seite = await client.get("/konto")
    treffer = re.search(r'name="csrf_token" value="([^"]+)"', seite.text)
    assert treffer
    return treffer.group(1)


@pytest_asyncio.fixture
async def welt(session_maker, seed_data):
    """Eine Person mit Daten in jedem Modul, plus ein Team-Board, auf dem
    sie gemeinsam mit einer Kollegin arbeitet."""
    async with session_maker() as session:
        admin = User(
            name="Test Admin", email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORT), role=RoleEnum.einrichtungs_admin,
        )
        kollege = User(
            name="Kollegin", email=KOLLEGE_EMAIL,
            password_hash=hash_password(KOLLEGE_PASSWORT), role=RoleEnum.teilnehmer,
        )
        psm = User(
            name="PSM", email="psm@test.local",
            password_hash=hash_password("psmpass123"), role=RoleEnum.psychosoziale_mitarbeit,
        )
        trainer = User(
            name="Trainer:in", email="bt@test.local",
            password_hash=hash_password("btpass123"), role=RoleEnum.berufstrainer,
        )
        session.add_all([admin, kollege, psm, trainer])
        await session.commit()
        for u in (admin, kollege, psm, trainer):
            await session.refresh(u)

        opfer_id = seed_data["teilnehmer_id"]

        # Eigene Inhalte
        session.add(TagebuchEintrag(teilnehmer_id=opfer_id, datum=__import__("datetime").date(2026, 8, 1),
                                    dankbarkeit_1="Ein guter Tag"))
        session.add(Bewerbung(teilnehmer_id=opfer_id, firma="Musterfirma",
                              position="Stelle", status=BewerbungStatus.versendet))
        session.add(Wochenbericht(teilnehmer_id=opfer_id, kw_jahr=2026, kw_nummer=31,
                                  tage=leere_tage(), status=WochenberichtStatus.entwurf))
        # Zuordnungen
        session.add(PsmZuordnung(psm_id=psm.id, teilnehmer_id=opfer_id))
        session.add(BerufstrainerZuordnung(berufstrainer_id=trainer.id, teilnehmer_id=opfer_id))
        # Audit-Eintrag, bei dem die Person Akteurin war
        session.add(AuditLogEintrag(akteur_id=opfer_id, aktion=AuditAktion.bewerbung_gelesen,
                                    zieltyp=AuditZieltyp.bewerbung, ziel_teilnehmer_id=kollege.id))

        handlungsfeld = Handlungsfeld(name="Video", abteilung_id=seed_data["abteilung_id"])
        session.add(handlungsfeld)
        await session.commit()
        await session.refresh(handlungsfeld)

        gruppe = Teilnehmergruppe(name="Team", handlungsfeld_id=handlungsfeld.id, erstellt_von=opfer_id)
        session.add(gruppe)
        await session.commit()
        await session.refresh(gruppe)
        session.add(TeilnehmergruppeMitglied(gruppe_id=gruppe.id, teilnehmer_id=opfer_id))

        # Team-Board: von der zu löschenden Person angelegt, gemeinsam bearbeitet
        team_board = Board(titel="Imagefilm", typ=BoardTyp.team,
                           handlungsfeld_id=handlungsfeld.id, ersteller_id=opfer_id)
        session.add(team_board)
        await session.commit()
        await session.refresh(team_board)

        spalte = Spalte(board_id=team_board.id, name="Offen", reihenfolge=0)
        session.add(spalte)
        await session.commit()
        await session.refresh(spalte)

        # Karte 1: von der zu löschenden Person erstellt UND ihr zugewiesen
        karte_eigene = Karte(spalte_id=spalte.id, titel="Drehbuch schreiben", ersteller_id=opfer_id)
        # Karte 2: von der Kollegin erstellt, beiden zugewiesen
        karte_geteilt = Karte(spalte_id=spalte.id, titel="Location suchen", ersteller_id=kollege.id)
        session.add_all([karte_eigene, karte_geteilt])
        await session.commit()
        await session.refresh(karte_eigene)
        await session.refresh(karte_geteilt)

        session.add_all([
            KartenZuweisung(karte_id=karte_eigene.id, teilnehmer_id=opfer_id),
            KartenZuweisung(karte_id=karte_geteilt.id, teilnehmer_id=opfer_id),
            KartenZuweisung(karte_id=karte_geteilt.id, teilnehmer_id=kollege.id),
            KartenBewegung(karte_id=karte_eigene.id, bewegt_von_id=opfer_id),
        ])
        # Persönliches Board
        person_board = Board(titel="Meine Aufgaben", typ=BoardTyp.person,
                             person_teilnehmer_id=opfer_id, ersteller_id=opfer_id)
        session.add(person_board)
        await session.commit()

        return {
            **seed_data,
            "opfer_id": opfer_id,
            "admin_email": ADMIN_EMAIL, "admin_passwort": ADMIN_PASSWORT,
            "admin_id": admin.id, "kollege_id": kollege.id,
            "karte_eigene_id": karte_eigene.id, "karte_geteilt_id": karte_geteilt.id,
            "team_board_id": team_board.id, "gruppe_id": gruppe.id,
        }


async def _anzahl(session_maker, modell, bedingung) -> int:
    async with session_maker() as session:
        return len((await session.execute(select(modell).where(bedingung))).scalars().all())


# ---------------------------------------------------------------------------
# Vollständigkeit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_konto_und_eigene_inhalte_sind_weg(session_maker, welt):
    async with session_maker() as session:
        await loesche_konto_vollstaendig(session, welt["opfer_id"])

    opfer = welt["opfer_id"]
    async with session_maker() as session:
        assert await session.get(User, opfer) is None, "Konto existiert noch"

    for modell, bedingung, name in [
        (TagebuchEintrag, TagebuchEintrag.teilnehmer_id == opfer, "Tagebuch"),
        (Bewerbung, Bewerbung.teilnehmer_id == opfer, "Bewerbungen"),
        (Wochenbericht, Wochenbericht.teilnehmer_id == opfer, "Wochenberichte"),
        (PsmZuordnung, PsmZuordnung.teilnehmer_id == opfer, "PSM-Zuordnung"),
        (BerufstrainerZuordnung, BerufstrainerZuordnung.teilnehmer_id == opfer, "Trainer-Zuordnung"),
        (TeilnehmergruppeMitglied, TeilnehmergruppeMitglied.teilnehmer_id == opfer, "Gruppenmitgliedschaft"),
        (KartenZuweisung, KartenZuweisung.teilnehmer_id == opfer, "Kartenzuweisungen"),
    ]:
        assert await _anzahl(session_maker, modell, bedingung) == 0, f"{name} nicht gelöscht"


@pytest.mark.asyncio
async def test_persoenliches_board_ist_weg(session_maker, welt):
    async with session_maker() as session:
        await loesche_konto_vollstaendig(session, welt["opfer_id"])
    assert await _anzahl(
        session_maker, Board, Board.person_teilnehmer_id == welt["opfer_id"]
    ) == 0


@pytest.mark.asyncio
async def test_login_ist_danach_unmoeglich(client: AsyncClient, session_maker, welt):
    async with session_maker() as session:
        await loesche_konto_vollstaendig(session, welt["opfer_id"])

    antwort = await client.post(
        "/login",
        data={"email": welt["teilnehmer_email"], "password": welt["teilnehmer_passwort"]},
        follow_redirects=False,
    )
    assert antwort.status_code != 303


# ---------------------------------------------------------------------------
# Fremde Arbeit bleibt stehen - der eigentliche Punkt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_team_karten_bleiben_bestehen(session_maker, welt):
    """Auch die Karte, die die gelöschte Person selbst angelegt hatte."""
    async with session_maker() as session:
        await loesche_konto_vollstaendig(session, welt["opfer_id"])

    async with session_maker() as session:
        eigene = await session.get(Karte, welt["karte_eigene_id"])
        geteilt = await session.get(Karte, welt["karte_geteilt_id"])
    assert eigene is not None, "Karte der gelöschten Person wurde mitgerissen"
    assert geteilt is not None, "Karte der Kollegin wurde mitgerissen"
    assert eigene.titel == "Drehbuch schreiben"
    # Urheberschaft ist entfernt, Inhalt bleibt.
    assert eigene.ersteller_id is None
    # Fremde Urheberschaft bleibt unangetastet.
    assert geteilt.ersteller_id == welt["kollege_id"]


@pytest.mark.asyncio
async def test_karten_fallen_als_unzugewiesen_auf(session_maker, welt):
    """Das Signal für die Leitung: die Karte hat niemanden mehr."""
    async with session_maker() as session:
        await loesche_konto_vollstaendig(session, welt["opfer_id"])

    async with session_maker() as session:
        zuweisungen_eigene = (
            await session.execute(
                select(KartenZuweisung).where(KartenZuweisung.karte_id == welt["karte_eigene_id"])
            )
        ).scalars().all()
        zuweisungen_geteilt = (
            await session.execute(
                select(KartenZuweisung).where(KartenZuweisung.karte_id == welt["karte_geteilt_id"])
            )
        ).scalars().all()

    assert len(zuweisungen_eigene) == 0, "Karte müsste jetzt unzugewiesen sein"
    # Die Kollegin bleibt zugewiesen - nur die gelöschte Person fällt weg.
    assert [z.teilnehmer_id for z in zuweisungen_geteilt] == [welt["kollege_id"]]


@pytest.mark.asyncio
async def test_team_board_bleibt_bestehen(session_maker, welt):
    """Das Board wurde von der gelöschten Person angelegt - andere arbeiten
    trotzdem weiter darauf."""
    async with session_maker() as session:
        await loesche_konto_vollstaendig(session, welt["opfer_id"])

    async with session_maker() as session:
        board = await session.get(Board, welt["team_board_id"])
        gruppe = await session.get(Teilnehmergruppe, welt["gruppe_id"])
    assert board is not None and board.ersteller_id is None
    assert gruppe is not None and gruppe.erstellt_von is None


@pytest.mark.asyncio
async def test_kartenbewegung_bleibt_pseudonymisiert(session_maker, welt):
    """Die Bewegung selbst ist Teil der Board-Historie und bleibt - nur der
    Personenbezug fällt weg."""
    async with session_maker() as session:
        await loesche_konto_vollstaendig(session, welt["opfer_id"])

    async with session_maker() as session:
        bewegungen = (
            await session.execute(
                select(KartenBewegung).where(KartenBewegung.karte_id == welt["karte_eigene_id"])
            )
        ).scalars().all()
    assert len(bewegungen) == 1
    assert bewegungen[0].bewegt_von_id is None


@pytest.mark.asyncio
async def test_auditlog_bleibt_als_nachweis(session_maker, welt):
    """CLAUDE.md §9: pseudonymisierte Löschung, nicht Verschwinden. Der
    Nachweis, dass ein Zugriff stattgefunden hat, überlebt die Person."""
    async with session_maker() as session:
        await loesche_konto_vollstaendig(session, welt["opfer_id"])

    async with session_maker() as session:
        eintraege = (
            await session.execute(
                select(AuditLogEintrag).where(AuditLogEintrag.akteur_id == welt["opfer_id"])
            )
        ).scalars().all()
    assert len(eintraege) == 1, "Audit-Nachweis wurde mitgelöscht"


# ---------------------------------------------------------------------------
# Der Endpunkt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpunkt_verlangt_das_bestaetigungswort(client: AsyncClient, session_maker, welt):
    await login(client, welt["admin_email"], welt["admin_passwort"])
    antwort = await client.post(
        f"/admin/benutzer/{welt['opfer_id']}/loeschen",
        data={"csrf_token": await _csrf_token(client), "bestaetigung": "ja"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    assert "fehler=" in antwort.headers["location"]

    async with session_maker() as session:
        assert await session.get(User, welt["opfer_id"]) is not None, "trotz falscher Bestätigung gelöscht"


@pytest.mark.asyncio
async def test_endpunkt_loescht_mit_bestaetigung(client: AsyncClient, session_maker, welt):
    await login(client, welt["admin_email"], welt["admin_passwort"])
    antwort = await client.post(
        f"/admin/benutzer/{welt['opfer_id']}/loeschen",
        data={"csrf_token": await _csrf_token(client), "bestaetigung": "KONTO LÖSCHEN"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    assert "hinweis=" in antwort.headers["location"]

    async with session_maker() as session:
        assert await session.get(User, welt["opfer_id"]) is None


@pytest.mark.asyncio
async def test_admin_kann_sich_nicht_selbst_loeschen(client: AsyncClient, session_maker, welt):
    await login(client, welt["admin_email"], welt["admin_passwort"])
    antwort = await client.post(
        f"/admin/benutzer/{welt['admin_id']}/loeschen",
        data={"csrf_token": await _csrf_token(client), "bestaetigung": "KONTO LÖSCHEN"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    assert "fehler=" in antwort.headers["location"]

    async with session_maker() as session:
        assert await session.get(User, welt["admin_id"]) is not None


@pytest.mark.asyncio
async def test_nur_admins_duerfen_loeschen(client: AsyncClient, session_maker, welt):
    """Der gefährlichste Endpunkt der Anwendung - eine Teilnehmer:in, die
    hier durchkäme, könnte fremde Konten samt Daten vernichten."""
    await login(client, KOLLEGE_EMAIL, KOLLEGE_PASSWORT)
    antwort = await client.post(
        f"/admin/benutzer/{welt['opfer_id']}/loeschen",
        data={"csrf_token": await _csrf_token(client), "bestaetigung": "KONTO LÖSCHEN"},
    )
    assert antwort.status_code == 403

    async with session_maker() as session:
        assert await session.get(User, welt["opfer_id"]) is not None
