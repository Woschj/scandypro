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


def test_atemuebung_des_tages_ist_deterministisch_und_im_pool():
    from app.core.atemuebungen import ATEMUEBUNGEN_POOL, atemuebung_des_tages

    heute = date.today()
    name = atemuebung_des_tages(1, heute)
    assert name == atemuebung_des_tages(1, heute)
    assert name in {u["name"] for u in ATEMUEBUNGEN_POOL}


def test_atemuebungen_pool_hat_mindestens_zehn_varianten_mit_sinnvollen_halten_zeiten():
    from app.core.atemuebungen import ATEMUEBUNGEN_POOL

    assert len(ATEMUEBUNGEN_POOL) >= 10
    for uebung in ATEMUEBUNGEN_POOL:
        for _label, halten_sekunden in uebung["schritte"]:
            assert halten_sekunden == 0 or 5 <= halten_sekunden <= 6


def test_atemuebung_punkte_layout_passt_zur_schrittanzahl():
    from app.core.atemuebungen import ATEMUEBUNGEN_POOL, atemuebung_punkte

    for uebung in ATEMUEBUNGEN_POOL:
        punkte = atemuebung_punkte(uebung["name"])
        assert len(punkte) == len(uebung["schritte"])
        for p in punkte:
            assert "cx" in p and "cy" in p and "label" in p


async def test_atemuebung_name_wird_gespeichert(client, seed_data, session_maker):
    from app.models.wohlbefinden import TagebuchEintrag

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()

    resp = await client.post(
        "/wohlbefinden/morgen",
        data={"csrf_token": token, "datum": heute, "atemuebung_name": "Box-Atmung"},
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        from sqlmodel import select

        result = await session.execute(
            select(TagebuchEintrag).where(TagebuchEintrag.teilnehmer_id == seed_data["teilnehmer_id"])
        )
        assert result.scalar_one().atemuebung_name == "Box-Atmung"


# Ein winziges, gültiges 1x1-PNG (base64) als Stand-in für eine im Canvas
# gezeichnete Skizze - Inhalt ist irrelevant, nur das Format muss stimmen.
_PNG_1X1_BASE64 = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


async def test_energie_level_wird_gespeichert_und_angezeigt(client, seed_data):
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()

    resp = await client.post(
        "/wohlbefinden/morgen",
        data={"csrf_token": token, "datum": heute, "energie_level": "3"},
    )
    assert resp.status_code == 303

    seite = await client.get("/wohlbefinden")
    assert 'name="energie_level" value="3"' in seite.text


async def test_energie_level_ausserhalb_bereich_wird_abgelehnt(client, seed_data):
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()

    resp = await client.post(
        "/wohlbefinden/morgen",
        data={"csrf_token": token, "datum": heute, "energie_level": "7"},
    )
    assert resp.status_code == 400


async def test_atemuebung_erledigt_wird_gespeichert(client, seed_data, session_maker):
    from app.models.wohlbefinden import TagebuchEintrag

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()

    resp = await client.post(
        "/wohlbefinden/morgen",
        data={"csrf_token": token, "datum": heute, "atemuebung_erledigt": "true"},
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        from sqlmodel import select

        result = await session.execute(
            select(TagebuchEintrag).where(TagebuchEintrag.teilnehmer_id == seed_data["teilnehmer_id"])
        )
        eintrag = result.scalar_one()
        assert eintrag.atemuebung_erledigt_am is not None


async def test_checkliste_wird_gespeichert_und_angezeigt(client, seed_data):
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()

    resp = await client.post(
        "/wohlbefinden/abend",
        data={"csrf_token": token, "datum": heute, "check_pause_gemacht": "true"},
    )
    assert resp.status_code == 303

    seite = await client.get("/wohlbefinden")
    assert 'name="check_pause_gemacht" value="true" checked' in seite.text


async def test_zeichnung_hochladen_anzeigen_und_loeschen(client, seed_data, session_maker):
    from app.models.wohlbefinden import TagebuchEintrag

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()

    resp = await client.post(
        "/wohlbefinden/abend",
        data={"csrf_token": token, "datum": heute, "zeichnung_daten": _PNG_1X1_BASE64},
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        from sqlmodel import select

        result = await session.execute(
            select(TagebuchEintrag).where(TagebuchEintrag.teilnehmer_id == seed_data["teilnehmer_id"])
        )
        eintrag = result.scalar_one()
        assert eintrag.zeichnung_pfad is not None
        eintrag_id = eintrag.id

    bild_resp = await client.get(f"/wohlbefinden/zeichnung/{eintrag_id}")
    assert bild_resp.status_code == 200
    assert bild_resp.headers["content-type"] == "image/png"

    # Ersetzen entfernt die alte Datei von der Platte (siehe
    # app/routers/wohlbefinden.py:abend_speichern) - kein verwaister Upload.
    await client.post(
        "/wohlbefinden/abend",
        data={"csrf_token": token, "datum": heute, "zeichnung_entfernen": "true"},
    )
    async with session_maker() as session:
        aktualisiert = await session.get(TagebuchEintrag, eintrag_id)
        assert aktualisiert.zeichnung_pfad is None


async def test_zeichnung_download_nur_fuer_owner(client, seed_data, session_maker):
    """Ownership-Check analog zu Bewerbungsunterlagen (app/routers/bewerbungen.py):
    eine andere Person darf die Zeichnung nicht abrufen können."""
    from app.core.security import hash_password
    from app.models.user import RoleEnum, User
    from app.models.wohlbefinden import TagebuchEintrag

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()
    await client.post(
        "/wohlbefinden/abend",
        data={"csrf_token": token, "datum": heute, "zeichnung_daten": _PNG_1X1_BASE64},
    )

    async with session_maker() as session:
        from sqlmodel import select

        result = await session.execute(
            select(TagebuchEintrag).where(TagebuchEintrag.teilnehmer_id == seed_data["teilnehmer_id"])
        )
        eintrag_id = result.scalar_one().id

        andere = User(
            name="Andere Person",
            email="andere-zeichnung@test.local",
            password_hash=hash_password("anderespasswort123"),
            role=RoleEnum.teilnehmer,
        )
        session.add(andere)
        await session.commit()
        await session.refresh(andere)

    await client.post("/logout", data={"csrf_token": token})
    await login(client, "andere-zeichnung@test.local", "anderespasswort123")
    resp = await client.get(f"/wohlbefinden/zeichnung/{eintrag_id}")
    assert resp.status_code == 403
