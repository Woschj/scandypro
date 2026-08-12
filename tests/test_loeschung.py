"""Löschtests für die Hard-Delete-Pfade (app/core/deletion.py).

CLAUDE.md §10 verlangt vollständige, kaskadierende Löschung inklusive
Dateien; §20 nennt Löschtests als Pflicht. Bis zu diesem Modul war
`deletion.py` ungetestet (siehe tasks/codebase-audit/README.md, CA-003).

Der Kern jedes Tests: nach dem Löschen darf weder eine DB-Zeile noch eine
**Datei auf der Platte** übrig bleiben. Gerade Letzteres fällt im Betrieb
sonst nie auf - die verschlüsselten Uploads liegen einfach weiter im
Upload-Verzeichnis. Jedes neue Dateifeld muss an zwei Stellen nachgetragen
werden (Router und deletion.py); diese Tests schlagen an, wenn eine davon
vergessen wird.
"""
import re
from datetime import date

from app.core.uploads import voller_pfad
from tests.conftest import login

# Gültiges Mini-PNG - die Upload-Validierung prüft Magic Bytes
# (app/core/uploads.py:_signatur_passt), ein Dummy-String reicht nicht.
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
_PNG_DATEN_URL = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


async def _csrf_token(client):
    seite = await client.get("/konto")
    match = re.search(r'name="csrf_token" value="([^"]+)"', seite.text)
    assert match
    return match.group(1)


async def test_wohlbefinden_loeschen_entfernt_zeilen_und_dateien(client, seed_data, session_maker):
    """Deckt alle vier Dateifelder eines TagebuchEintrags gleichzeitig ab -
    Zeichnung, Dankbarkeitsfoto und die beiden generischen Übungs-Uploads."""
    from sqlmodel import select

    from app.models.wohlbefinden import TagebuchEintrag, WohlbefindenFreigabe

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()

    # Morgen-Teil mit generischem Upload
    await client.post(
        "/wohlbefinden/morgen",
        data={"csrf_token": token, "datum": heute, "dankbarkeit_1": "Etwas"},
        files={"morgen_uebung_datei": ("m.png", _PNG, "image/png")},
    )
    # Abend-Teil mit Zeichnung, Dankbarkeitsfoto und generischem Upload
    await client.post(
        "/wohlbefinden/abend",
        data={"csrf_token": token, "datum": heute, "zeichnung_daten": _PNG_DATEN_URL},
        files={
            "dankbarkeitsfoto": ("d.png", _PNG, "image/png"),
            "abend_uebung_datei": ("a.png", _PNG, "image/png"),
        },
    )

    async with session_maker() as session:
        eintrag = (
            await session.execute(
                select(TagebuchEintrag).where(TagebuchEintrag.teilnehmer_id == seed_data["teilnehmer_id"])
            )
        ).scalar_one()
        pfade = [
            eintrag.zeichnung_pfad,
            eintrag.dankbarkeitsfoto_pfad,
            eintrag.morgen_uebung_datei_pfad,
            eintrag.abend_uebung_datei_pfad,
        ]
    assert all(pfade), f"Test-Vorbedingung: alle vier Uploads müssen angelegt sein, war {pfade}"
    assert all(voller_pfad(p).exists() for p in pfade)

    resp = await client.post(
        "/freigaben/konto/wohlbefinden-loeschen",
        data={"csrf_token": token, "bestaetigung": "LÖSCHEN"},
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        rest = (
            await session.execute(
                select(TagebuchEintrag).where(TagebuchEintrag.teilnehmer_id == seed_data["teilnehmer_id"])
            )
        ).scalars().all()
        freigaben = (
            await session.execute(
                select(WohlbefindenFreigabe).where(
                    WohlbefindenFreigabe.teilnehmer_id == seed_data["teilnehmer_id"]
                )
            )
        ).scalars().all()
    assert list(rest) == []
    assert list(freigaben) == []
    for p in pfade:
        assert not voller_pfad(p).exists(), f"Verwaiste Datei nach Löschung: {p}"


async def test_tag_loeschen_entfernt_alle_dateien_des_tages(client, seed_data, session_maker):
    """Das Löschen eines *einzelnen* Tages muss dieselben vier Dateifelder
    aufräumen wie die Komplettlöschung - hier lag der Fehler zuletzt."""
    from sqlmodel import select

    from app.models.wohlbefinden import TagebuchEintrag

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()

    await client.post(
        "/wohlbefinden/morgen",
        data={"csrf_token": token, "datum": heute},
        files={"morgen_uebung_datei": ("m.png", _PNG, "image/png")},
    )
    await client.post(
        "/wohlbefinden/abend",
        data={"csrf_token": token, "datum": heute, "zeichnung_daten": _PNG_DATEN_URL},
        files={
            "dankbarkeitsfoto": ("d.png", _PNG, "image/png"),
            "abend_uebung_datei": ("a.png", _PNG, "image/png"),
        },
    )

    async with session_maker() as session:
        eintrag = (
            await session.execute(
                select(TagebuchEintrag).where(TagebuchEintrag.teilnehmer_id == seed_data["teilnehmer_id"])
            )
        ).scalar_one()
        pfade = [
            eintrag.zeichnung_pfad,
            eintrag.dankbarkeitsfoto_pfad,
            eintrag.morgen_uebung_datei_pfad,
            eintrag.abend_uebung_datei_pfad,
        ]
    assert all(pfade)

    resp = await client.post(
        "/wohlbefinden/tag/loeschen", data={"csrf_token": token, "datum": heute}
    )
    assert resp.status_code == 303

    for p in pfade:
        assert not voller_pfad(p).exists(), f"Verwaiste Datei nach Tag-Löschung: {p}"


async def test_zeichnung_ersetzen_laesst_keine_datei_zurueck(client, seed_data, session_maker):
    """Auch das *Ersetzen* eines Uploads muss die alte Datei entfernen -
    sonst sammeln sich verschlüsselte Altstände an."""
    from sqlmodel import select

    from app.models.wohlbefinden import TagebuchEintrag

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    heute = date.today().isoformat()

    await client.post(
        "/wohlbefinden/abend",
        data={"csrf_token": token, "datum": heute},
        files={"dankbarkeitsfoto": ("erst.png", _PNG, "image/png")},
    )
    async with session_maker() as session:
        erster_pfad = (
            await session.execute(
                select(TagebuchEintrag.dankbarkeitsfoto_pfad).where(
                    TagebuchEintrag.teilnehmer_id == seed_data["teilnehmer_id"]
                )
            )
        ).scalar_one()
    assert voller_pfad(erster_pfad).exists()

    await client.post(
        "/wohlbefinden/abend",
        data={"csrf_token": token, "datum": heute},
        files={"dankbarkeitsfoto": ("zweit.png", _PNG, "image/png")},
    )
    async with session_maker() as session:
        zweiter_pfad = (
            await session.execute(
                select(TagebuchEintrag.dankbarkeitsfoto_pfad).where(
                    TagebuchEintrag.teilnehmer_id == seed_data["teilnehmer_id"]
                )
            )
        ).scalar_one()

    assert zweiter_pfad != erster_pfad
    assert voller_pfad(zweiter_pfad).exists()
    assert not voller_pfad(erster_pfad).exists(), "Alte Datei blieb beim Ersetzen liegen"


async def test_bewerbungen_loeschen_entfernt_zeilen_und_dateien(client, seed_data, session_maker):
    from sqlmodel import select

    from app.models.bewerbung import Bewerbung, BewerbungsNotiz, Bewerbungsunterlage

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)

    await client.post(
        "/bewerbungen",
        data={"csrf_token": token, "firma": "Test GmbH", "position": "Testposition"},
    )
    await client.post(
        "/bewerbungen/unterlagen",
        data={"csrf_token": token, "kategorie": "lebenslauf"},
        files={"datei": ("lebenslauf.png", _PNG, "image/png")},
    )

    async with session_maker() as session:
        unterlage = (
            await session.execute(
                select(Bewerbungsunterlage).where(
                    Bewerbungsunterlage.teilnehmer_id == seed_data["teilnehmer_id"]
                )
            )
        ).scalar_one()
        pfad = unterlage.speicherpfad
    assert voller_pfad(pfad).exists()

    resp = await client.post(
        "/freigaben/konto/bewerbungen-loeschen",
        data={"csrf_token": token, "bestaetigung": "LÖSCHEN"},
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        bewerbungen = (
            await session.execute(
                select(Bewerbung).where(Bewerbung.teilnehmer_id == seed_data["teilnehmer_id"])
            )
        ).scalars().all()
        unterlagen = (
            await session.execute(
                select(Bewerbungsunterlage).where(
                    Bewerbungsunterlage.teilnehmer_id == seed_data["teilnehmer_id"]
                )
            )
        ).scalars().all()
        notizen = (await session.execute(select(BewerbungsNotiz))).scalars().all()
    assert list(bewerbungen) == []
    assert list(unterlagen) == []
    assert list(notizen) == []
    assert not voller_pfad(pfad).exists(), f"Verwaiste Bewerbungsdatei: {pfad}"


async def test_persoenliches_kanban_loeschen_kaskadiert(client, seed_data, session_maker):
    """Persönliches Board muss inkl. Spalten, Karten, Zuweisungen,
    Unteraufgaben und Bewegungen verschwinden - ohne Fremdschlüsselfehler."""
    from sqlmodel import select

    from app.models.kanban import (
        Board,
        BoardTyp,
        Karte,
        KartenBewegung,
        KartenZuweisung,
        Spalte,
        Unteraufgabe,
    )

    teilnehmer_id = seed_data["teilnehmer_id"]
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
        for i, name in enumerate(("Offen", "Erledigt")):
            s = Spalte(board_id=board.id, name=name, reihenfolge=i, ist_system_erledigt=(i == 1))
            session.add(s)
            spalten.append(s)
        await session.commit()
        for s in spalten:
            await session.refresh(s)

        karte = Karte(spalte_id=spalten[0].id, titel="Karte", ersteller_id=teilnehmer_id)
        session.add(karte)
        await session.commit()
        await session.refresh(karte)

        session.add(KartenZuweisung(karte_id=karte.id, teilnehmer_id=teilnehmer_id))
        session.add(Unteraufgabe(karte_id=karte.id, titel="Unteraufgabe", reihenfolge=0))
        session.add(KartenBewegung(karte_id=karte.id, bewegt_von_id=teilnehmer_id))
        await session.commit()

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    resp = await client.post(
        "/freigaben/konto/kanban-loeschen",
        data={"csrf_token": token, "bestaetigung": "LÖSCHEN"},
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        assert list((await session.execute(select(Board).where(Board.id == board.id))).scalars().all()) == []
        assert list((await session.execute(select(Spalte).where(Spalte.board_id == board.id))).scalars().all()) == []
        assert list((await session.execute(select(Karte).where(Karte.id == karte.id))).scalars().all()) == []
        for modell in (KartenZuweisung, Unteraufgabe, KartenBewegung):
            rest = (
                await session.execute(select(modell).where(modell.karte_id == karte.id))
            ).scalars().all()
            assert list(rest) == [], f"{modell.__name__} nicht mitgelöscht"


async def test_loeschen_braucht_bestaetigung(client, seed_data, session_maker):
    """Ohne exaktes Bestätigungswort darf nichts gelöscht werden."""
    from sqlmodel import select

    from app.models.wohlbefinden import TagebuchEintrag

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    token = await _csrf_token(client)
    await client.post(
        "/wohlbefinden/morgen",
        data={"csrf_token": token, "datum": date.today().isoformat(), "dankbarkeit_1": "Bleibt"},
    )

    resp = await client.post(
        "/freigaben/konto/wohlbefinden-loeschen",
        data={"csrf_token": token, "bestaetigung": "loeschen bitte"},
    )
    assert resp.status_code == 400

    async with session_maker() as session:
        rest = (
            await session.execute(
                select(TagebuchEintrag).where(TagebuchEintrag.teilnehmer_id == seed_data["teilnehmer_id"])
            )
        ).scalars().all()
    assert len(list(rest)) == 1, "Eintrag wurde trotz falscher Bestätigung gelöscht"


async def test_fremder_kann_nicht_fuer_andere_loeschen(client, seed_data, session_maker):
    """Die Löschrouten wirken ausschließlich auf die eigenen Daten - eine
    andere Person darf damit nichts von jemand anderem entfernen."""
    from sqlmodel import select

    from app.core.security import hash_password
    from app.models.user import RoleEnum, User
    from app.models.wohlbefinden import TagebuchEintrag

    async with session_maker() as session:
        session.add(
            TagebuchEintrag(
                teilnehmer_id=seed_data["teilnehmer_id"], datum=date.today(), dankbarkeit_1="Fremd"
            )
        )
        andere = User(
            name="Andere",
            email="loesch-andere@test.local",
            password_hash=hash_password("anderespasswort123"),
            role=RoleEnum.teilnehmer,
        )
        session.add(andere)
        await session.commit()

    await login(client, "loesch-andere@test.local", "anderespasswort123")
    token = await _csrf_token(client)
    resp = await client.post(
        "/freigaben/konto/wohlbefinden-loeschen",
        data={"csrf_token": token, "bestaetigung": "LÖSCHEN"},
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        rest = (
            await session.execute(
                select(TagebuchEintrag).where(TagebuchEintrag.teilnehmer_id == seed_data["teilnehmer_id"])
            )
        ).scalars().all()
    assert len(list(rest)) == 1, "Fremde Daten wurden mitgelöscht"
