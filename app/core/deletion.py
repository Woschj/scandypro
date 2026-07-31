"""Kaskadierende Hard-Delete-Routinen für Wohlbefinden- und Bewerbungsdaten
(siehe CLAUDE.md §10, DATENSCHUTZ_UND_BERECHTIGUNGEN.md §5).

Löscht das Konto (User-Zeile) selbst NICHT - Kanban-Karten referenzieren
`ersteller_id` ohne Kaskade-Handling, eine vollständige Konto-Löschung
inkl. Login ist bewusst auf die später geplante zentrale Benutzerver-
waltung verschoben (siehe README, "Bekannte Lücken"). Hier werden nur die
Inhaltsdaten der jeweiligen Domäne entfernt.
"""

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.uploads import datei_loeschen
from app.models.bewerbung import Bewerbung, BewerbungsFreigabe, Bewerbungsunterlage
from app.models.wohlbefinden import WohlbefindenEintrag, WohlbefindenFreigabe


async def loesche_alle_wohlbefinden_daten(session: AsyncSession, teilnehmer_id: int) -> None:
    eintraege_result = await session.execute(
        select(WohlbefindenEintrag).where(WohlbefindenEintrag.teilnehmer_id == teilnehmer_id)
    )
    for eintrag in eintraege_result.scalars().all():
        await session.delete(eintrag)

    freigaben_result = await session.execute(
        select(WohlbefindenFreigabe).where(WohlbefindenFreigabe.teilnehmer_id == teilnehmer_id)
    )
    for freigabe in freigaben_result.scalars().all():
        await session.delete(freigabe)

    await session.commit()


async def loesche_alle_bewerbungsdaten(session: AsyncSession, teilnehmer_id: int) -> None:
    unterlagen_result = await session.execute(
        select(Bewerbungsunterlage).where(Bewerbungsunterlage.teilnehmer_id == teilnehmer_id)
    )
    for unterlage in unterlagen_result.scalars().all():
        datei_loeschen(unterlage.speicherpfad)
        await session.delete(unterlage)
    await session.flush()

    freigaben_result = await session.execute(
        select(BewerbungsFreigabe).where(BewerbungsFreigabe.teilnehmer_id == teilnehmer_id)
    )
    for freigabe in freigaben_result.scalars().all():
        await session.delete(freigabe)
    await session.flush()

    bewerbungen_result = await session.execute(select(Bewerbung).where(Bewerbung.teilnehmer_id == teilnehmer_id))
    for bewerbung in bewerbungen_result.scalars().all():
        await session.delete(bewerbung)

    await session.commit()
