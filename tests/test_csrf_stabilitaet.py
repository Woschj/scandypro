"""Regressionstest für einen echten, reproduzierbaren CSRF-Bug (siehe
CHANGELOG): Starlettes SessionMiddleware signiert den Session-Cookie bei
JEDER Antwort mit einem neuen Zeitstempel neu (itsdangerous.TimestampSigner),
wodurch sich der rohe Cookie-String über zwei Request-Response-Zyklen ändert.
Ein CSRF-Token, das direkt aus diesem rohen Cookie-Wert abgeleitet wird, ist
dadurch bereits beim übernächsten Request ungültig - das betraf praktisch
jedes Formular (z. B. "+ Spalte hinzufügen" im Kanban), sobald zwischen dem
Laden der Seite und dem Absenden mehr als eine Sekunde CPU-Zeit lag.

Der Fix leitet das Token stattdessen aus einem stabilen Zufallswert ab, der
im entschlüsselten Session-Dict liegt (`request.session["_csrf_secret"]`,
siehe app/core/templating.py:csrf_token) - dieser bleibt über beliebig viele
Requests stabil. Dieser Test simuliert das reale Problem, indem er die
Cookie-Signatur zwischen GET und POST künstlich altern lässt (eine reine
Zeitstempel-Neusignierung ändert nur die Signatur, nicht das Session-Dict)."""
import asyncio
import re

from tests.conftest import login


def _csrf_token_aus_html(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "csrf_token-Feld nicht im Formular gefunden"
    return match.group(1)


async def test_csrf_token_bleibt_ueber_mehrere_get_requests_gueltig(client, seed_data):
    """Mehrere GET-Requests hintereinander (wie beim Neuladen/Navigieren)
    lassen den rohen Session-Cookie durch die Timestamp-Neusignierung jedes
    Mal anders aussehen - das darf das eingebettete CSRF-Token nicht mehr
    ungültig machen, da es aus dem stabilen Session-Secret abgeleitet wird."""
    await login(client, seed_data["teilnehmer_email"], seed_data["teilnehmer_passwort"])

    konto_seite = await client.get("/konto")
    cookie_nach_erstem_get = client.cookies.get("session")
    token = _csrf_token_aus_html(konto_seite.text)

    # Eine Sekunde Abstand erzwingen, damit itsdangerous.TimestampSigner
    # (sekundengenau) garantiert einen neuen Zeitstempel verwendet - ohne
    # das wäre der Test von zufälligem Timing innerhalb derselben Sekunde
    # abhängig.
    await asyncio.sleep(1.1)
    await client.get("/konto")
    cookie_nach_weiteren_gets = client.cookies.get("session")
    assert cookie_nach_weiteren_gets != cookie_nach_erstem_get, (
        "Testannahme verletzt: der rohe Session-Cookie müsste sich bei "
        "jeder Antwort ändern (Starlette TimestampSigner) - falls nicht, "
        "hat sich das Framework-Verhalten geändert und dieser Test prüft "
        "nichts mehr."
    )

    resp = await client.post(
        "/konto/passwort",
        data={
            "csrf_token": token,
            "aktuelles_passwort": seed_data["teilnehmer_passwort"],
            "neues_passwort": "neuespasswort123",
            "neues_passwort_wiederholen": "neuespasswort123",
        },
    )
    assert resp.status_code == 200
    assert "form-success" in resp.text
