"""Schreibt Audit-Log-Einträge bei jedem Fremdzugriff auf sensible Daten.

Siehe app/models/audit.py:AuditLogEintrag - nur Metadaten, keine Inhalte.
"""

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.audit import AuditAktion, AuditLogEintrag, AuditZieltyp


async def protokolliere(
    session: AsyncSession,
    akteur_id: int,
    aktion: AuditAktion,
    zieltyp: AuditZieltyp,
    ziel_teilnehmer_id: int,
    grundlage_freigabe_id: int | None = None,
) -> None:
    session.add(
        AuditLogEintrag(
            akteur_id=akteur_id,
            aktion=aktion,
            zieltyp=zieltyp,
            ziel_teilnehmer_id=ziel_teilnehmer_id,
            grundlage_freigabe_id=grundlage_freigabe_id,
        )
    )
    await session.commit()
