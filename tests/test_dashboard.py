"""Dashboard-Rückblick (Schritte/Stimmung/Bewerbungen, siehe app/main.py,
app/core/fortschritt.py) - deckt die neuen Felder mit echten Daten ab,
über den reinen Leer-Zustand (siehe test_login.py) hinaus."""
from datetime import date

from tests.conftest import login


async def test_dashboard_zeigt_stimmung_und_bewerbungen(client, seed_data, session_maker):
    from app.models.bewerbung import Bewerbung, BewerbungStatus
    from app.models.wohlbefinden import WohlbefindenEintrag

    async with session_maker() as session:
        session.add(
            WohlbefindenEintrag(
                teilnehmer_id=seed_data["teilnehmer_id"],
                datum=date.today(),
                stimmung=8,
                belastbarkeit=7,
            )
        )
        session.add(
            Bewerbung(
                teilnehmer_id=seed_data["teilnehmer_id"],
                firma="Test GmbH",
                position="Testposition",
                status=BewerbungStatus.versendet,
            )
        )
        await session.commit()

    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Deine Woche im Rückblick" in resp.text
    assert "Laufende Bewerbung" in resp.text
    assert "Schnellzugriff" in resp.text
