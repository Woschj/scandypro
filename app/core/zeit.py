"""Einheitliche Zeitquelle für gespeicherte Zeitstempel.

`datetime.utcnow()` ist seit Python 3.12 deprecated und entfällt in einer
künftigen Version - es erzeugte in jedem Testlauf dutzende Warnungen und
hätte die echten darunter begraben (siehe
tasks/codebase-audit/README.md, CA-007).

Der naheliegende Ersatz `datetime.now(UTC)` liefert allerdings ein
*zeitzonenbewusstes* Objekt, während sämtliche Spalten im Schema als
`sa.DateTime()` ohne Zeitzone angelegt sind (siehe alembic/versions/).
Ein Mischbetrieb aus naiven und bewussten Werten führt beim Vergleich zu
`TypeError: can't compare offset-naive and offset-aware datetimes` - genau
die Art Fehler, die erst spät und dann in einer Randfunktion auffällt.

`jetzt()` ist deshalb bewusst ein exakter Ersatz für das bisherige
Verhalten: UTC-basiert, aber naiv - identischer Wert wie
`datetime.utcnow()`, nur ohne Deprecation. Eine spätere Umstellung des
gesamten Schemas auf `timestamptz` bliebe damit ein eigener, bewusster
Schritt und passiert nicht versehentlich nebenbei.
"""

from datetime import UTC, datetime


def jetzt() -> datetime:
    """Aktueller UTC-Zeitpunkt ohne Zeitzoneninfo (naiv) - passend zu den
    `sa.DateTime()`-Spalten des Schemas."""
    return datetime.now(UTC).replace(tzinfo=None)
