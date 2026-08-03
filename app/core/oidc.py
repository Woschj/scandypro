"""Optionales Single Sign-On über einen externen OIDC-Provider (z.B.
Authentik) - siehe app/routers/oidc.py für die HTTP-Routen und CLAUDE.md
§26/Referenzdateien. Nach dem Vorbild des Schwestermoduls Scandy-Lite
(dort: app/core/oidc.py, bereits produktiv gegen Authentik im Einsatz),
damit beide Apps langfristig gegen denselben Identity-Provider laufen
können, ohne dass ihre fachlich unterschiedlichen User-Modelle vereinheit-
licht werden müssten.

Grundprinzip: der Provider klärt nur "wer ist das" (stabile `sub`-Kennung,
Name, E-Mail). Was die Person in ScandyPro darf, bleibt eine bewusste,
lokale Entscheidung einer Einrichtungs-Admin - ein per SSO neu erkannter
Account wird IMMER inaktiv und ohne Rolle angelegt (siehe
app/models/user.py:User, app/routers/admin.py:benutzer_freischalten) statt
Rollen/Gruppen automatisch vom Provider zu übernehmen (CLAUDE.md §8).
"""

from authlib.integrations.starlette_client import OAuth
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.models.user import AuthSource, User

oauth = OAuth()

if settings.oidc_enabled:
    oauth.register(
        name="oidc",
        server_metadata_url=f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        client_kwargs={"scope": "openid email profile"},
    )


async def finde_oder_lege_an(session: AsyncSession, claims: dict) -> User:
    """Ordnet einen erfolgreichen OIDC-Login einem lokalen Account zu.

    Reihenfolge:
    1. `external_id` (OIDC `sub`) bereits bekannt -> dieser Account, unab-
       hängig von zwischenzeitlichen Namens-/E-Mail-Änderungen beim Provider.
    2. E-Mail passt zu einem bestehenden lokalen Account -> verknüpfen
       (external_id nachtragen), statt einen Duplikat-Account anzulegen;
       das bestehende Passwort bleibt als zusätzlicher Login-Weg gültig.
    3. Sonst: neuer, noch nicht freigeschalteter Account (aktiv=False,
       role=None) - siehe Moduldocstring.
    """
    sub = claims["sub"]

    bestehend = await session.execute(select(User).where(User.external_id == sub))
    user = bestehend.scalar_one_or_none()
    if user is not None:
        return user

    email = (claims.get("email") or "").strip().lower()
    if email:
        per_email = await session.execute(select(User).where(User.email == email))
        user = per_email.scalar_one_or_none()
        if user is not None:
            user.external_id = sub
            session.add(user)
            await session.commit()
            return user

    name = claims.get("name") or email or f"Neue Person ({sub[:8]})"
    neuer_nutzer = User(
        name=name,
        email=email or f"{sub}@sso.lokal",
        password_hash=None,
        role=None,
        auth_source=AuthSource.sso,
        external_id=sub,
        aktiv=False,
    )
    session.add(neuer_nutzer)
    await session.commit()
    await session.refresh(neuer_nutzer)
    return neuer_nutzer
