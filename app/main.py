import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select
from starlette.middleware.sessions import SessionMiddleware

from app.core.access import hat_wohlbefinden_freigabe
from app.core.config import settings
from app.core.database import async_session_factory, init_db
from app.core.deps import SessionDep, get_current_user_optional
from app.core.seed import seed_demo_data
from app.core.templating import templates
from app.models.bewerbung import BewerbungsFreigabe
from app.models.organisation import BerufstrainerZuordnung, PsmZuordnung
from app.models.user import RoleEnum, User
from app.routers import admin, auth, bewerbungen, freigaben, kanban, kanban_karten, wochenberichte, wohlbefinden

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.seed_demo_data:
        async with async_session_factory() as session:
            await seed_demo_data(session)
    yield


app = FastAPI(title="ScandyPro", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(kanban.router)
app.include_router(kanban_karten.router)
app.include_router(wohlbefinden.router)
app.include_router(bewerbungen.router)
app.include_router(wochenberichte.router)
app.include_router(admin.router)
app.include_router(freigaben.router)


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    return RedirectResponse(url="/login", status_code=303)


@app.get("/")
async def dashboard(request: Request, session: SessionDep):
    current_user = await get_current_user_optional(request, session)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    psm_kontakt = None
    trainer_kontakt = None
    betreute_teilnehmer: list[User] = []
    freigegebene_wohlbefinden_ids: set[int] = set()
    freigegebene_bewerbungen_ids: set[int] = set()

    if current_user.role == RoleEnum.teilnehmer:
        result = await session.execute(select(PsmZuordnung).where(PsmZuordnung.teilnehmer_id == current_user.id))
        zuordnung = result.scalar_one_or_none()
        if zuordnung is not None:
            psm_kontakt = await session.get(User, zuordnung.psm_id)

        trainer_result = await session.execute(
            select(BerufstrainerZuordnung).where(BerufstrainerZuordnung.teilnehmer_id == current_user.id)
        )
        trainer_zuordnung = trainer_result.scalar_one_or_none()
        if trainer_zuordnung is not None:
            trainer_kontakt = await session.get(User, trainer_zuordnung.berufstrainer_id)
    elif current_user.role == RoleEnum.psychosoziale_mitarbeit:
        result = await session.execute(select(PsmZuordnung).where(PsmZuordnung.psm_id == current_user.id))
        teilnehmer_ids = [z.teilnehmer_id for z in result.scalars().all()]
        if teilnehmer_ids:
            teilnehmer_result = await session.execute(select(User).where(User.id.in_(teilnehmer_ids)))
            betreute_teilnehmer = list(teilnehmer_result.scalars().all())
            for teilnehmer_id in teilnehmer_ids:
                if await hat_wohlbefinden_freigabe(session, current_user.id, teilnehmer_id):
                    freigegebene_wohlbefinden_ids.add(teilnehmer_id)
    elif current_user.role == RoleEnum.berufstrainer:
        result = await session.execute(
            select(BerufstrainerZuordnung).where(BerufstrainerZuordnung.berufstrainer_id == current_user.id)
        )
        teilnehmer_ids = [z.teilnehmer_id for z in result.scalars().all()]
        if teilnehmer_ids:
            teilnehmer_result = await session.execute(select(User).where(User.id.in_(teilnehmer_ids)))
            betreute_teilnehmer = list(teilnehmer_result.scalars().all())

            heute = date.today()
            freigaben_result = await session.execute(
                select(BewerbungsFreigabe).where(
                    BewerbungsFreigabe.empfaenger_id == current_user.id,
                    BewerbungsFreigabe.teilnehmer_id.in_(teilnehmer_ids),
                    BewerbungsFreigabe.widerrufen_am.is_(None),
                )
            )
            for freigabe in freigaben_result.scalars().all():
                if freigabe.gueltig_bis is None or freigabe.gueltig_bis >= heute:
                    freigegebene_bewerbungen_ids.add(freigabe.teilnehmer_id)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "current_user": current_user,
            "psm_kontakt": psm_kontakt,
            "trainer_kontakt": trainer_kontakt,
            "betreute_teilnehmer": betreute_teilnehmer,
            "freigegebene_wohlbefinden_ids": freigegebene_wohlbefinden_ids,
            "freigegebene_bewerbungen_ids": freigegebene_bewerbungen_ids,
        },
    )
