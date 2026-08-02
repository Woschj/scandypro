"""5-Minuten-Tagebuch (siehe app/routers/wohlbefinden.py, app/models/wohlbefinden.py:
TagebuchEintrag): Morgen-/Abend-Eintrag speichern, Löschen mit Ownership-Check,
deterministischer Tages-Impuls."""
import re
from datetime import date

from tests.conftest import login


async def _csrf_token(client):
    konto_seite = await client.get("/konto")
    match = re.search(r'name="csrf_token" value="([^"]+)"', konto_seite.text)
    assert match
    return match.group(1)


async def test_morgen_eintrag_speichern_und_anzeigen(client, seed_data):
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()

    resp = await client.post(
        "/wohlbefinden/morgen",
        data={
            "csrf_token": token,
            "datum": heute,
            "dankbarkeit_1": "Sonnenschein",
            "dankbarkeit_2": "Ein guter Kaffee",
            "dankbarkeit_3": "Ruhige Fahrt zur Arbeit",
            "morgen_impuls_frage": "Testfrage?",
            "morgen_impuls_antwort": "Testantwort.",
        },
    )
    assert resp.status_code == 303

    seite = await client.get("/wohlbefinden")
    assert seite.status_code == 200
    assert "Sonnenschein" in seite.text
    assert "Testantwort." in seite.text


async def test_abend_eintrag_speichern_und_anzeigen(client, seed_data):
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()

    resp = await client.post(
        "/wohlbefinden/abend",
        data={
            "csrf_token": token,
            "datum": heute,
            "highlight_1": "Gutes Gespräch geführt",
            "highlight_2": "",
            "highlight_3": "",
            "abend_impuls_frage": "Testfrage abends?",
            "abend_impuls_antwort": "Testantwort abends.",
        },
    )
    assert resp.status_code == 303

    seite = await client.get("/wohlbefinden")
    assert seite.status_code == 200
    assert "Gutes Gespräch geführt" in seite.text
    assert "Testantwort abends." in seite.text


async def test_tag_loeschen_entfernt_eintrag(client, seed_data, session_maker):
    from app.models.wohlbefinden import TagebuchEintrag

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()

    await client.post(
        "/wohlbefinden/morgen",
        data={"csrf_token": token, "datum": heute, "dankbarkeit_1": "Etwas"},
    )

    resp = await client.post(
        "/wohlbefinden/tag/loeschen",
        data={"csrf_token": token, "datum": heute},
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        from sqlmodel import select

        result = await session.execute(
            select(TagebuchEintrag).where(
                TagebuchEintrag.teilnehmer_id == seed_data["teilnehmer_id"],
                TagebuchEintrag.datum == date.today(),
            )
        )
        assert result.scalar_one_or_none() is None


async def test_tag_loeschen_fremder_eintrag_wird_abgelehnt(client, seed_data, session_maker):
    """Ownership-Check (CLAUDE.md §15/§20): eine andere Person darf einen
    fremden Tagebuch-Eintrag nicht löschen können."""
    from app.core.security import hash_password
    from app.models.user import RoleEnum, User
    from app.models.wohlbefinden import TagebuchEintrag

    async with session_maker() as session:
        andere = User(
            name="Andere Person",
            email="andere@test.local",
            password_hash=hash_password("anderespasswort123"),
            role=RoleEnum.teilnehmer,
        )
        session.add(andere)
        await session.commit()
        await session.refresh(andere)

        session.add(TagebuchEintrag(teilnehmer_id=andere.id, datum=date.today(), dankbarkeit_1="Fremder Eintrag"))
        await session.commit()

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)

    resp = await client.post(
        "/wohlbefinden/tag/loeschen",
        data={"csrf_token": token, "datum": date.today().isoformat()},
    )
    # Der Ownership-Check greift nur, wenn ein Eintrag der eingeloggten Person
    # existiert; da hier keiner existiert, gibt es nichts zu löschen (kein
    # Fehler) - der eigentliche Schutz zeigt sich daran, dass der fremde
    # Eintrag unangetastet bleibt.
    assert resp.status_code == 303
    async with session_maker() as session:
        from sqlmodel import select

        result = await session.execute(
            select(TagebuchEintrag).where(TagebuchEintrag.teilnehmer_id == andere.id)
        )
        assert result.scalar_one_or_none() is not None


def test_impuls_des_tages_ist_deterministisch_und_stabil():
    from app.core.tagebuch_prompts import abend_impuls_des_tages, morgen_impuls_des_tages

    heute = date.today()
    assert morgen_impuls_des_tages(1, heute) == morgen_impuls_des_tages(1, heute)
    assert abend_impuls_des_tages(1, heute) == abend_impuls_des_tages(1, heute)
