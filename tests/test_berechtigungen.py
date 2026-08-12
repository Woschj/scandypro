"""Berechtigungstests für die zentrale Zugriffsschicht (app/core/access.py).

CLAUDE.md §20 verlangt Berechtigungs-, Ownership- und Löschtests als
Pflicht; bis zu diesem Modul war `access.py` - die Stelle, die für *alle*
Module entscheidet, wer was sehen darf - komplett ungetestet (siehe
tasks/codebase-audit/README.md, CA-001).

Aufbau: eine vollständige Organisationsstruktur (zwei Teilnehmer:innen,
Berufstrainer:in mit und ohne Zuordnung, PSM mit und ohne Zuordnung,
Admin) einmal als Fixture, danach je Zugriffspfad zwei Fälle - **ohne**
Freigabe muss geblockt werden, **mit** Freigabe darf gelesen werden. Der
Negativfall ist dabei der eigentlich wichtige: er würde bei einer
versehentlich zu weit gefassten Bedingung in access.py anschlagen.
"""
import re

import pytest_asyncio

from tests.conftest import login


async def _csrf_token(client):
    seite = await client.get("/konto")
    match = re.search(r'name="csrf_token" value="([^"]+)"', seite.text)
    assert match
    return match.group(1)


@pytest_asyncio.fixture
async def welt(session_maker, seed_data):
    """Vollständige Organisationsstruktur für Berechtigungsfälle.

    - `teilnehmer` (aus seed_data) und `fremder` - zwei unabhängige Personen
    - `trainer_zustaendig` per BerufstrainerZuordnung an `teilnehmer` gebunden
      UND Leitung eines Handlungsfelds, dessen Gruppe `teilnehmer` enthält
    - `trainer_fremd` ohne jede Zuordnung und ohne Handlungsfeld
    - `psm_zustaendig` per PsmZuordnung an `teilnehmer` gebunden
    - `psm_fremd` ohne Zuordnung
    - `admin`

    Beide Trainer-Bindungen sind nötig, weil die Module unterschiedliche
    Wege nutzen: Bewerbungen/Kanban-Personenboard gehen über die
    BerufstrainerZuordnung, Wochenberichte dagegen über die
    Handlungsfeld-Leitung (siehe access.py:betreute_teilnehmer_ids). Ohne
    beides würden Trainer-Tests stillschweigend trivial durchlaufen.

    Freigaben werden bewusst NICHT vorab angelegt - jeder Test setzt genau
    die, die er prüfen will.
    """
    from app.core.security import hash_password
    from app.models.organisation import (
        BerufstrainerZuordnung,
        Handlungsfeld,
        HandlungsfeldLeitung,
        HandlungsfeldMitglied,
        PsmZuordnung,
        Teilnehmergruppe,
        TeilnehmergruppeMitglied,
    )
    from app.models.user import RoleEnum, User

    passwort = "testpass123"
    personen = {
        "fremder": (RoleEnum.teilnehmer, "fremder@test.local"),
        "trainer_zustaendig": (RoleEnum.berufstrainer, "trainer-zu@test.local"),
        "trainer_fremd": (RoleEnum.berufstrainer, "trainer-fremd@test.local"),
        "psm_zustaendig": (RoleEnum.psychosoziale_mitarbeit, "psm-zu@test.local"),
        "psm_fremd": (RoleEnum.psychosoziale_mitarbeit, "psm-fremd@test.local"),
        "admin": (RoleEnum.einrichtungs_admin, "admin@test.local"),
    }

    ids: dict[str, int] = {}
    async with session_maker() as session:
        for schluessel, (rolle, email) in personen.items():
            user = User(
                name=schluessel,
                email=email,
                password_hash=hash_password(passwort),
                role=rolle,
                abteilung_id=seed_data["abteilung_id"],
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            ids[schluessel] = user.id

        session.add(
            BerufstrainerZuordnung(
                berufstrainer_id=ids["trainer_zustaendig"], teilnehmer_id=seed_data["teilnehmer_id"]
            )
        )
        session.add(PsmZuordnung(psm_id=ids["psm_zustaendig"], teilnehmer_id=seed_data["teilnehmer_id"]))

        handlungsfeld = Handlungsfeld(name="Testfeld", abteilung_id=seed_data["abteilung_id"])
        session.add(handlungsfeld)
        await session.commit()
        await session.refresh(handlungsfeld)

        session.add(
            HandlungsfeldLeitung(
                handlungsfeld_id=handlungsfeld.id, berufstrainer_id=ids["trainer_zustaendig"]
            )
        )
        session.add(
            HandlungsfeldMitglied(handlungsfeld_id=handlungsfeld.id, teilnehmer_id=seed_data["teilnehmer_id"])
        )

        gruppe = Teilnehmergruppe(
            name="Testgruppe",
            handlungsfeld_id=handlungsfeld.id,
            erstellt_von=ids["trainer_zustaendig"],
        )
        session.add(gruppe)
        await session.commit()
        await session.refresh(gruppe)

        session.add(TeilnehmergruppeMitglied(gruppe_id=gruppe.id, teilnehmer_id=seed_data["teilnehmer_id"]))
        await session.commit()

    return {
        "ids": ids,
        "emails": {k: v[1] for k, v in personen.items()},
        "passwort": passwort,
        "teilnehmer_id": seed_data["teilnehmer_id"],
        "handlungsfeld_id": handlungsfeld.id,
        "gruppe_id": gruppe.id,
    }


async def _als(client, welt, rolle: str):
    await login(client, welt["emails"][rolle], welt["passwort"])


# ---------------------------------------------------------------- Wohlbefinden


async def test_psm_ohne_freigabe_sieht_tagebuch_nicht(client, welt):
    """Organisatorische Zuordnung allein reicht NICHT - ohne aktive Freigabe
    bleibt das Tagebuch zu (CLAUDE.md §4: Zuordnung ≠ Einblick)."""
    await _als(client, welt, "psm_zustaendig")
    resp = await client.get(f"/wohlbefinden/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 403


async def test_psm_ohne_zuordnung_sieht_tagebuch_nicht_einmal_mit_freigabe(client, welt, session_maker):
    """Umgekehrter Fall: eine Freigabe ohne organisatorische Zuordnung darf
    ebenfalls nicht reichen - beide Bedingungen müssen erfüllt sein."""
    from app.models.wohlbefinden import WohlbefindenFreigabe, WohlbefindenFreigabeUmfang

    async with session_maker() as session:
        session.add(
            WohlbefindenFreigabe(
                teilnehmer_id=welt["teilnehmer_id"],
                empfaenger_id=welt["ids"]["psm_fremd"],
                umfang=WohlbefindenFreigabeUmfang.alle,
            )
        )
        await session.commit()

    await _als(client, welt, "psm_fremd")
    resp = await client.get(f"/wohlbefinden/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 403


async def test_psm_mit_zuordnung_und_freigabe_darf_lesen(client, welt, session_maker):
    from app.models.wohlbefinden import TagebuchEintrag, WohlbefindenFreigabe, WohlbefindenFreigabeUmfang
    from datetime import date

    async with session_maker() as session:
        session.add(
            TagebuchEintrag(
                teilnehmer_id=welt["teilnehmer_id"], datum=date.today(), dankbarkeit_1="Sichtbarer Inhalt"
            )
        )
        session.add(
            WohlbefindenFreigabe(
                teilnehmer_id=welt["teilnehmer_id"],
                empfaenger_id=welt["ids"]["psm_zustaendig"],
                umfang=WohlbefindenFreigabeUmfang.alle,
            )
        )
        await session.commit()

    await _als(client, welt, "psm_zustaendig")
    resp = await client.get(f"/wohlbefinden/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 200
    assert "Sichtbarer Inhalt" in resp.text


async def test_widerrufene_freigabe_sperrt_wieder(client, welt, session_maker):
    """Widerruf muss sofort greifen - sonst wäre die Widerrufbarkeit aus
    CLAUDE.md §8 wirkungslos."""
    from datetime import datetime

    from app.models.wohlbefinden import WohlbefindenFreigabe, WohlbefindenFreigabeUmfang

    async with session_maker() as session:
        session.add(
            WohlbefindenFreigabe(
                teilnehmer_id=welt["teilnehmer_id"],
                empfaenger_id=welt["ids"]["psm_zustaendig"],
                umfang=WohlbefindenFreigabeUmfang.alle,
                widerrufen_am=datetime.utcnow(),
            )
        )
        await session.commit()

    await _als(client, welt, "psm_zustaendig")
    resp = await client.get(f"/wohlbefinden/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 403


async def test_abgelaufene_freigabe_sperrt_wieder(client, welt, session_maker):
    from datetime import date, timedelta

    from app.models.wohlbefinden import WohlbefindenFreigabe, WohlbefindenFreigabeUmfang

    async with session_maker() as session:
        session.add(
            WohlbefindenFreigabe(
                teilnehmer_id=welt["teilnehmer_id"],
                empfaenger_id=welt["ids"]["psm_zustaendig"],
                umfang=WohlbefindenFreigabeUmfang.zeitraum,
                gueltig_bis=date.today() - timedelta(days=1),
            )
        )
        await session.commit()

    await _als(client, welt, "psm_zustaendig")
    resp = await client.get(f"/wohlbefinden/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 403


async def test_einzelfreigabe_zeigt_nur_den_freigegebenen_tag(client, welt, session_maker):
    """umfang=einzeln darf ausschließlich den einen freigegebenen Tag
    sichtbar machen - der Rest des Tagebuchs bleibt zu."""
    from datetime import date, timedelta

    from app.models.wohlbefinden import TagebuchEintrag, WohlbefindenFreigabe, WohlbefindenFreigabeUmfang

    async with session_maker() as session:
        geteilt = TagebuchEintrag(
            teilnehmer_id=welt["teilnehmer_id"], datum=date.today(), dankbarkeit_1="GETEILTER-TAG"
        )
        privat = TagebuchEintrag(
            teilnehmer_id=welt["teilnehmer_id"],
            datum=date.today() - timedelta(days=1),
            dankbarkeit_1="PRIVATER-TAG",
        )
        session.add(geteilt)
        session.add(privat)
        await session.commit()
        await session.refresh(geteilt)

        session.add(
            WohlbefindenFreigabe(
                teilnehmer_id=welt["teilnehmer_id"],
                empfaenger_id=welt["ids"]["psm_zustaendig"],
                umfang=WohlbefindenFreigabeUmfang.einzeln,
                tagebuch_eintrag_id=geteilt.id,
            )
        )
        await session.commit()

    await _als(client, welt, "psm_zustaendig")
    resp = await client.get(f"/wohlbefinden/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 200
    assert "GETEILTER-TAG" in resp.text
    assert "PRIVATER-TAG" not in resp.text


async def test_teilnehmer_kommt_nicht_an_fremdes_tagebuch(client, welt):
    """Auch die PSM-Route selbst darf für eine andere Teilnehmer:in nicht
    offenstehen - die Rollenprüfung greift vor der Freigabeprüfung."""
    await _als(client, welt, "fremder")
    resp = await client.get(f"/wohlbefinden/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 403


async def test_trainer_kommt_nicht_an_tagebuch(client, welt):
    """Wohlbefinden ist ausschließlich für PSM freigebbar - ein Trainer darf
    dort auch mit Zuordnung nicht hinein (Berechtigungsmatrix CLAUDE.md §4)."""
    await _als(client, welt, "trainer_zustaendig")
    resp = await client.get(f"/wohlbefinden/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 403


# ----------------------------------------------------------------- Bewerbungen


async def test_trainer_ohne_freigabe_sieht_bewerbungen_nicht(client, welt):
    await _als(client, welt, "trainer_zustaendig")
    resp = await client.get(f"/bewerbungen/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 403


async def test_trainer_ohne_zuordnung_sieht_bewerbungen_nicht_mit_freigabe(client, welt, session_maker):
    from app.models.bewerbung import BewerbungsFreigabe, BewerbungsFreigabeUmfang

    async with session_maker() as session:
        session.add(
            BewerbungsFreigabe(
                teilnehmer_id=welt["teilnehmer_id"],
                empfaenger_id=welt["ids"]["trainer_fremd"],
                umfang=BewerbungsFreigabeUmfang.alle,
            )
        )
        await session.commit()

    await _als(client, welt, "trainer_fremd")
    resp = await client.get(f"/bewerbungen/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 403


async def test_trainer_mit_zuordnung_und_freigabe_darf_bewerbungen_lesen(client, welt, session_maker):
    from app.models.bewerbung import Bewerbung, BewerbungsFreigabe, BewerbungsFreigabeUmfang, BewerbungStatus

    async with session_maker() as session:
        session.add(
            Bewerbung(
                teilnehmer_id=welt["teilnehmer_id"],
                firma="Sichtbar GmbH",
                position="Testposition",
                status=BewerbungStatus.versendet,
            )
        )
        session.add(
            BewerbungsFreigabe(
                teilnehmer_id=welt["teilnehmer_id"],
                empfaenger_id=welt["ids"]["trainer_zustaendig"],
                umfang=BewerbungsFreigabeUmfang.alle,
            )
        )
        await session.commit()

    await _als(client, welt, "trainer_zustaendig")
    resp = await client.get(f"/bewerbungen/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 200
    assert "Sichtbar GmbH" in resp.text


async def test_einzelfreigabe_bewerbung_zeigt_nur_diese(client, welt, session_maker):
    from app.models.bewerbung import Bewerbung, BewerbungsFreigabe, BewerbungsFreigabeUmfang, BewerbungStatus

    async with session_maker() as session:
        geteilt = Bewerbung(
            teilnehmer_id=welt["teilnehmer_id"],
            firma="GETEILTE-FIRMA",
            position="P",
            status=BewerbungStatus.versendet,
        )
        privat = Bewerbung(
            teilnehmer_id=welt["teilnehmer_id"],
            firma="PRIVATE-FIRMA",
            position="P",
            status=BewerbungStatus.versendet,
        )
        session.add(geteilt)
        session.add(privat)
        await session.commit()
        await session.refresh(geteilt)

        session.add(
            BewerbungsFreigabe(
                teilnehmer_id=welt["teilnehmer_id"],
                empfaenger_id=welt["ids"]["trainer_zustaendig"],
                umfang=BewerbungsFreigabeUmfang.einzeln,
                bewerbung_id=geteilt.id,
            )
        )
        await session.commit()

    await _als(client, welt, "trainer_zustaendig")
    resp = await client.get(f"/bewerbungen/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 200
    assert "GETEILTE-FIRMA" in resp.text
    assert "PRIVATE-FIRMA" not in resp.text


# ---------------------------------------------------------------------- Kanban


async def _persoenliches_board(session_maker, teilnehmer_id):
    from app.models.kanban import Board, BoardTyp, Karte, KartenSichtbarkeit, Spalte

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

        spalte = Spalte(board_id=board.id, name="Offen", reihenfolge=0)
        session.add(spalte)
        await session.commit()
        await session.refresh(spalte)

        session.add(
            Karte(
                spalte_id=spalte.id,
                titel="PRIVATE-KARTE",
                ersteller_id=teilnehmer_id,
                sichtbarkeit=KartenSichtbarkeit.privat,
            )
        )
        session.add(
            Karte(
                spalte_id=spalte.id,
                titel="TEAM-KARTE",
                ersteller_id=teilnehmer_id,
                sichtbarkeit=KartenSichtbarkeit.team,
            )
        )
        await session.commit()
        return board.id


async def test_fremder_teilnehmer_kommt_nicht_an_persoenliches_board(client, welt, session_maker):
    board_id = await _persoenliches_board(session_maker, welt["teilnehmer_id"])
    await _als(client, welt, "fremder")
    resp = await client.get(f"/kanban/boards/{board_id}")
    assert resp.status_code == 403


async def test_trainer_ohne_zuordnung_kommt_nicht_an_persoenliches_board(client, welt, session_maker):
    board_id = await _persoenliches_board(session_maker, welt["teilnehmer_id"])
    await _als(client, welt, "trainer_fremd")
    resp = await client.get(f"/kanban/boards/{board_id}")
    assert resp.status_code == 403


async def test_zustaendiger_trainer_sieht_private_karten_nicht(client, welt, session_maker):
    """Kern der IDOR-Absicherung aus VB-001: ein zuständiger Trainer darf das
    Personen-Board sehen, aber private Karten bleiben der Person vorbehalten
    (CLAUDE.md §24 "Keine Überwachung")."""
    board_id = await _persoenliches_board(session_maker, welt["teilnehmer_id"])
    await _als(client, welt, "trainer_zustaendig")
    resp = await client.get(f"/kanban/boards/{board_id}")
    assert resp.status_code == 200
    assert "TEAM-KARTE" in resp.text
    assert "PRIVATE-KARTE" not in resp.text


async def test_owner_sieht_eigene_private_karten(client, welt, session_maker, seed_data):
    board_id = await _persoenliches_board(session_maker, welt["teilnehmer_id"])
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    resp = await client.get(f"/kanban/boards/{board_id}")
    assert resp.status_code == 200
    assert "PRIVATE-KARTE" in resp.text
    assert "TEAM-KARTE" in resp.text


# ----------------------------------------------------------------------- Admin


async def test_nicht_admin_kommt_nicht_in_benutzerverwaltung(client, welt):
    for rolle in ("trainer_zustaendig", "psm_zustaendig", "fremder"):
        await _als(client, welt, rolle)
        resp = await client.get("/admin/benutzer")
        assert resp.status_code == 403, f"{rolle} durfte /admin/benutzer öffnen"


async def test_admin_darf_benutzerverwaltung(client, welt):
    await _als(client, welt, "admin")
    resp = await client.get("/admin/benutzer")
    assert resp.status_code == 200


async def test_admin_kommt_nicht_an_tagebuch_inhalte(client, welt, session_maker):
    """Einrichtungs-Admin verwaltet Accounts, hat aber laut
    Berechtigungsmatrix keinen inhaltlichen Zugriff (CLAUDE.md §4)."""
    from datetime import date

    from app.models.wohlbefinden import TagebuchEintrag

    async with session_maker() as session:
        session.add(TagebuchEintrag(teilnehmer_id=welt["teilnehmer_id"], datum=date.today(), dankbarkeit_1="X"))
        await session.commit()

    await _als(client, welt, "admin")
    resp = await client.get(f"/wohlbefinden/teilnehmer/{welt['teilnehmer_id']}")
    assert resp.status_code == 403


# ------------------------------------------------------------ Wochenberichte


async def test_trainer_ohne_zuordnung_sieht_fremden_wochenbericht_nicht(client, welt, session_maker):
    from datetime import datetime

    from app.models.wochenbericht import Wochenbericht, WochenberichtStatus, leere_tage

    async with session_maker() as session:
        tage = leere_tage()
        tage["montag"] = {"start": "08:00", "ende": "16:00", "taetigkeiten": "GEHEIMER-BERICHT"}
        session.add(
            Wochenbericht(
                teilnehmer_id=welt["teilnehmer_id"],
                kw_jahr=2026,
                kw_nummer=32,
                tage=tage,
                status=WochenberichtStatus.abgegeben,
                abgegeben_am=datetime.utcnow(),
            )
        )
        await session.commit()

    await _als(client, welt, "trainer_fremd")
    resp = await client.get("/wochenberichte")
    assert resp.status_code == 200
    assert "GEHEIMER-BERICHT" not in resp.text


async def test_wochenbericht_zugriff_wird_protokolliert(client, welt, session_maker):
    """CA-002: Fremdzugriff auf Wochenberichte muss im Audit-Log landen."""
    from datetime import datetime

    from sqlmodel import select

    from app.models.audit import AuditAktion, AuditLogEintrag
    from app.models.wochenbericht import Wochenbericht, WochenberichtStatus, leere_tage

    async with session_maker() as session:
        session.add(
            Wochenbericht(
                teilnehmer_id=welt["teilnehmer_id"],
                kw_jahr=2026,
                kw_nummer=32,
                tage=leere_tage(),
                status=WochenberichtStatus.abgegeben,
                abgegeben_am=datetime.utcnow(),
            )
        )
        await session.commit()

    await _als(client, welt, "trainer_zustaendig")
    resp = await client.get("/wochenberichte")
    assert resp.status_code == 200

    async with session_maker() as session:
        result = await session.execute(
            select(AuditLogEintrag).where(AuditLogEintrag.aktion == AuditAktion.wochenbericht_gelesen)
        )
        eintraege = list(result.scalars().all())
    assert len(eintraege) == 1
    assert eintraege[0].akteur_id == welt["ids"]["trainer_zustaendig"]
    assert eintraege[0].ziel_teilnehmer_id == welt["teilnehmer_id"]


async def test_datenexport_wird_protokolliert(client, seed_data, session_maker):
    """CA-002: Selbstauskunft nach Art. 15 DSGVO wird protokolliert."""
    from sqlmodel import select

    from app.models.audit import AuditAktion, AuditLogEintrag

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    resp = await client.get("/konto/export")
    assert resp.status_code == 200

    async with session_maker() as session:
        result = await session.execute(
            select(AuditLogEintrag).where(AuditLogEintrag.aktion == AuditAktion.daten_exportiert)
        )
        eintraege = list(result.scalars().all())
    assert len(eintraege) == 1
    assert eintraege[0].akteur_id == seed_data["teilnehmer_id"]


# ------------------------------------------------------ Deaktivierte Accounts


async def test_deaktivierter_account_wird_sofort_ausgesperrt(client, welt, session_maker):
    """`aktiv=False` muss auch eine bereits laufende Session beenden, nicht
    erst den nächsten Login blockieren (siehe app/core/deps.py)."""
    from app.models.user import User

    await _als(client, welt, "trainer_zustaendig")
    assert (await client.get("/")).status_code == 200

    async with session_maker() as session:
        user = await session.get(User, welt["ids"]["trainer_zustaendig"])
        user.aktiv = False
        session.add(user)
        await session.commit()

    resp = await client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
