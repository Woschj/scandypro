"""Einfacher In-Memory-Schutz gegen Brute-Force-Login-Versuche (siehe
app/routers/auth.py, docs/DATENSCHUTZ_UND_BERECHTIGUNGEN.md).

Bewusst kein Redis/keine externe Abhängigkeit - ScandyPro läuft als
Single-Tenant-Deployment mit einem Anwendungsprozess (siehe compose.yaml),
ein Prozess-lokaler Zähler reicht dafür aus. Schlüssel ist (E-Mail, IP)
gemeinsam, damit weder verteiltes Raten über viele IPs bei derselben E-Mail
noch verteiltes Raten über viele E-Mails von derselben IP unbegrenzt bleibt.
"""

from datetime import datetime, timedelta
from app.core.zeit import jetzt

MAX_VERSUCHE = 5
FENSTER = timedelta(minutes=5)
SPERRDAUER = timedelta(minutes=5)

_fehlversuche: dict[str, list[datetime]] = {}
_gesperrt_bis: dict[str, datetime] = {}


def _schluessel(email: str, ip: str) -> str:
    return f"{email.strip().lower()}:{ip}"


def ist_gesperrt(email: str, ip: str) -> bool:
    bis = _gesperrt_bis.get(_schluessel(email, ip))
    return bis is not None and bis > jetzt()


def registriere_fehlversuch(email: str, ip: str) -> None:
    schluessel = _schluessel(email, ip)
    zeitpunkt = jetzt()
    versuche = [t for t in _fehlversuche.get(schluessel, []) if zeitpunkt - t < FENSTER]
    versuche.append(zeitpunkt)
    _fehlversuche[schluessel] = versuche
    if len(versuche) >= MAX_VERSUCHE:
        _gesperrt_bis[schluessel] = zeitpunkt + SPERRDAUER


def zuruecksetzen(email: str, ip: str) -> None:
    schluessel = _schluessel(email, ip)
    _fehlversuche.pop(schluessel, None)
    _gesperrt_bis.pop(schluessel, None)
