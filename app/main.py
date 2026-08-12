import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from sqlmodel import select
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.database import async_session_factory, init_db
from app.core.deps import SessionDep, get_current_user_optional
from app.core.faellige_karten import faellige_karten
from app.core.fortschritt import woechentliche_schritte, woechentliche_tagebuch_tage
from app.core.seed import seed_admin, seed_demo_data
from app.core.static_cache import CachedStaticFiles
from app.core.templating import templates
from app.core.zeit import jetzt
from app.models.bewerbung import Bewerbung, BewerbungsFreigabe, BewerbungStatus
from app.models.kanban import Board, Karte, KartenBewegung, Spalte
from app.models.organisation import BerufstrainerZuordnung, PsmZuordnung
from app.models.user import RoleEnum, User
from app.models.wohlbefinden import TagebuchEintrag, Unterstuetzungsanfrage, WohlbefindenFreigabe
from app.routers import admin, auth, bewerbungen, freigaben, kanban, kanban_karten, oidc, wochenberichte, wohlbefinden

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.seed_demo_data or (settings.admin_email and settings.admin_password):
        async with async_session_factory() as session:
            if settings.seed_demo_data:
                await seed_demo_data(session)
            if settings.admin_email and settings.admin_password:
                await seed_admin(session, settings.admin_email, settings.admin_password)
    yield


app = FastAPI(title="ScandyPro", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=settings.session_cookie_secure
)
# Versionierte Assets (?v={{ asset_version }}, siehe app/core/templating.py)
# dürfen ein Jahr unverändert im Browser bleiben, da sich bei einem Release
# die URL selbst ändert; unversionierte Treffer (z.B. Icons) bekommen nur
# eine kurze, revalidierende Cache-Dauer. KEIN eigener /uploads-Mount (siehe
# docs/KONZEPT.md, Abschnitt 2.3: Downloads laufen ausschließlich über
# authentifizierte, Owner-geprüfte Routen, kein öffentlicher Static-Mount).
app.mount(
    "/static",
    CachedStaticFiles(directory="app/static", cache_control="public, max-age=3600", versioned_cache_control="public, max-age=31536000, immutable"),
    name="static",
)

app.include_router(auth.router)
app.include_router(oidc.router)
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


_FEHLER_TITEL = {
    400: "Das hat nicht geklappt",
    403: "Kein Zugriff",
    404: "Nicht gefunden",
    409: "Das hat nicht geklappt",
    422: "Das hat nicht geklappt",
}
_FEHLER_STANDARDTEXT = {
    400: "Bitte prüfe deine Eingabe und versuch es noch einmal.",
    403: "Für diesen Bereich hast du keine Berechtigung.",
    404: "Diese Seite oder dieser Eintrag wurde nicht gefunden.",
    409: "Das hat gerade nicht geklappt. Bitte versuch es noch einmal.",
    422: "Bitte prüfe deine Eingabe und versuch es noch einmal.",
}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Einheitliche, sanft formulierte Fehlerseite im ScandyPro-Layout statt
    einer rohen {"detail": ...}-JSON-Antwort (siehe tasks/uiux-audit/UI-002.md).
    401 bleibt beim spezialisierten Redirect-Handler oben."""
    async with async_session_factory() as session:
        current_user = await get_current_user_optional(request, session)

    titel = _FEHLER_TITEL.get(exc.status_code, "Da ist etwas schiefgelaufen")
    nachricht = exc.detail if isinstance(exc.detail, str) and exc.detail else _FEHLER_STANDARDTEXT.get(
        exc.status_code, "Bitte versuch es gleich noch einmal."
    )
    return templates.TemplateResponse(
        request,
        "error.html",
        {"current_user": current_user, "titel": titel, "nachricht": nachricht},
        status_code=exc.status_code,
    )


async def _dashboard_teilnehmer(session: SessionDep, current_user: User, was_steht_an: list[dict]) -> dict:
    """Dashboard-Kontext fuer Teilnehmer:innen: Kontaktpersonen, Wochen-
    Rueckblick und die konkreten Ankuepfungspunkte darunter.

    Alle Rueckblick-Werte sind bewusst reine Zaehlwerte plus ein positiv
    formulierter Anknuepfungspunkt - nie Quoten oder Bewertungen (CLAUDE.md
    Abschnitt 24/25)."""
    kontext: dict = {}

    zuordnung = (
        await session.execute(select(PsmZuordnung).where(PsmZuordnung.teilnehmer_id == current_user.id))
    ).scalar_one_or_none()
    kontext["psm_kontakt"] = await session.get(User, zuordnung.psm_id) if zuordnung else None

    trainer_zuordnung = (
        await session.execute(
            select(BerufstrainerZuordnung).where(BerufstrainerZuordnung.teilnehmer_id == current_user.id)
        )
    ).scalar_one_or_none()
    kontext["trainer_kontakt"] = (
        await session.get(User, trainer_zuordnung.berufstrainer_id) if trainer_zuordnung else None
    )

    schritte = await woechentliche_schritte(session, current_user.id)
    kontext["schritte_diese_woche"] = schritte
    kontext["tagebuch_tage_woche"] = await woechentliche_tagebuch_tage(session, current_user.id)
    kontext.update(await _bewerbungs_rueckblick(session, current_user.id))
    kontext["letzte_kanban_aktivitaet"] = await _letzte_kanban_aktivitaet(
        session, current_user.id, schritte, was_steht_an
    )
    kontext["letztes_tagebuch_wort"] = (
        await session.execute(
            select(TagebuchEintrag.wort_des_tages)
            .where(TagebuchEintrag.teilnehmer_id == current_user.id, TagebuchEintrag.wort_des_tages.is_not(None))
            .order_by(TagebuchEintrag.datum.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return kontext


async def _bewerbungs_rueckblick(session: SessionDep, teilnehmer_id: int) -> dict:
    """Sanfter Bewerbungs-Ueberblick: bewusst nur Zaehlwerte, keine Ruecklauf-
    quote/Bewertung; "aktiv" schliesst Entwuerfe aus, die noch keine eigene
    Handlung der Person waren."""
    aktive = (
        await session.execute(
            select(Bewerbung.id).where(
                Bewerbung.teilnehmer_id == teilnehmer_id, Bewerbung.status != BewerbungStatus.entwurf
            )
        )
    ).scalars().all()
    if not aktive:
        return {"bewerbungen_uebersicht": None, "letzte_aktive_bewerbung": None}

    wartend = (
        await session.execute(
            select(Bewerbung.id).where(
                Bewerbung.teilnehmer_id == teilnehmer_id,
                Bewerbung.status.in_([BewerbungStatus.versendet, BewerbungStatus.rueckmeldung_offen]),
            )
        )
    ).scalars().all()
    letzte = (
        await session.execute(
            select(Bewerbung.firma)
            .where(Bewerbung.teilnehmer_id == teilnehmer_id, Bewerbung.status != BewerbungStatus.entwurf)
            .order_by(Bewerbung.erstellt_am.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return {
        "bewerbungen_uebersicht": {"aktiv": len(list(aktive)), "wartend": len(list(wartend))},
        "letzte_aktive_bewerbung": letzte,
    }


async def _letzte_kanban_aktivitaet(
    session: SessionDep, teilnehmer_id: int, schritte: int, was_steht_an: list[dict]
) -> dict | None:
    """Konkreter Anknuepfungspunkt unter der Schritte-Kachel: zuletzt bewegte
    Karte, oder - wenn diese Woche noch nichts bewegt wurde - das naechste
    Anstehende als Vorschlag statt einer Mahnung."""
    if not schritte:
        return was_steht_an[0] if was_steht_an else None

    treffer = (
        await session.execute(
            select(Karte.titel, Board.id, Board.titel)
            .select_from(KartenBewegung)
            .join(Karte, Karte.id == KartenBewegung.karte_id)
            .join(Spalte, Spalte.id == Karte.spalte_id)
            .join(Board, Board.id == Spalte.board_id)
            .where(
                KartenBewegung.bewegt_von_id == teilnehmer_id,
                KartenBewegung.bewegt_am >= jetzt() - timedelta(days=7),
            )
            .order_by(KartenBewegung.bewegt_am.desc())
            .limit(1)
        )
    ).first()
    if treffer is None:
        return None
    karten_titel, board_id, board_titel = treffer
    return {"titel": karten_titel, "link": f"/kanban/boards/{board_id}", "kontext": board_titel}


async def _neu_geteilt_fuer_trainer(session: SessionDep, trainer_id: int, stichtag: datetime) -> list[dict]:
    freigaben = (
        await session.execute(
            select(BewerbungsFreigabe)
            .where(
                BewerbungsFreigabe.empfaenger_id == trainer_id,
                BewerbungsFreigabe.widerrufen_am.is_(None),
                BewerbungsFreigabe.erstellt_am >= stichtag,
            )
            .order_by(BewerbungsFreigabe.erstellt_am.desc())
        )
    ).scalars().all()
    return [
        {
            "teilnehmer": await session.get(User, freigabe.teilnehmer_id),
            "text": "hat dir Bewerbungsdaten freigegeben",
            "erstellt_am": freigabe.erstellt_am,
            "link": f"/bewerbungen/teilnehmer/{freigabe.teilnehmer_id}",
        }
        for freigabe in freigaben
    ]


async def _neu_geteilt_fuer_psm(session: SessionDep, psm_id: int, stichtag: datetime) -> list[dict]:
    freigaben = (
        await session.execute(
            select(WohlbefindenFreigabe)
            .where(
                WohlbefindenFreigabe.empfaenger_id == psm_id,
                WohlbefindenFreigabe.widerrufen_am.is_(None),
                WohlbefindenFreigabe.erstellt_am >= stichtag,
            )
            .order_by(WohlbefindenFreigabe.erstellt_am.desc())
        )
    ).scalars().all()
    return [
        {
            "teilnehmer": await session.get(User, freigabe.teilnehmer_id),
            "text": (
                "hat dir einen einzelnen Tag freigegeben"
                if freigabe.umfang.value == "einzeln"
                else "hat dir 'Mein Tag' freigegeben"
            ),
            "erstellt_am": freigabe.erstellt_am,
            "link": f"/wohlbefinden/teilnehmer/{freigabe.teilnehmer_id}",
        }
        for freigabe in freigaben
    ]


async def _offene_anfragen_fuer_psm(session: SessionDep, psm_id: int) -> list[dict]:
    anfragen = (
        await session.execute(
            select(Unterstuetzungsanfrage)
            .where(
                Unterstuetzungsanfrage.empfaenger_id == psm_id,
                Unterstuetzungsanfrage.gesehen_am.is_(None),
            )
            .order_by(Unterstuetzungsanfrage.erstellt_am.desc())
        )
    ).scalars().all()
    return [
        {"anfrage": anfrage, "teilnehmer": await session.get(User, anfrage.teilnehmer_id)}
        for anfrage in anfragen
    ]


@app.get("/")
async def dashboard(request: Request, session: SessionDep):
    """Rollenabhaengige Startseite - die eigentliche Datenbeschaffung liegt in
    den _dashboard_*/_neu_geteilt_*-Helfern darueber, damit hier nur die
    Rollenverzweigung selbst steht."""
    current_user = await get_current_user_optional(request, session)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    kontext: dict = {
        "current_user": current_user,
        "psm_kontakt": None,
        "trainer_kontakt": None,
        "schritte_diese_woche": None,
        "tagebuch_tage_woche": None,
        "bewerbungen_uebersicht": None,
        "letzte_kanban_aktivitaet": None,
        "letztes_tagebuch_wort": None,
        "letzte_aktive_bewerbung": None,
        "was_steht_an": [],
        "neu_geteilt": [],
        "offene_unterstuetzungsanfragen": [],
    }

    if current_user.role in (RoleEnum.teilnehmer, RoleEnum.berufstrainer):
        kontext["was_steht_an"] = await faellige_karten(session, current_user)

    # "Neu geteilt" ist bewusst nur ein schmaler Hinweis auf die letzten 14
    # Tage, kein Postfach/Ungelesen-System - siehe CLAUDE.md Abschnitt 24
    # "keine automatischen Eskalationen".
    stichtag_neu = jetzt() - timedelta(days=14)

    if current_user.role == RoleEnum.teilnehmer:
        kontext.update(await _dashboard_teilnehmer(session, current_user, kontext["was_steht_an"]))
    elif current_user.role == RoleEnum.berufstrainer:
        kontext["neu_geteilt"] = await _neu_geteilt_fuer_trainer(session, current_user.id, stichtag_neu)
    elif current_user.role == RoleEnum.psychosoziale_mitarbeit:
        kontext["neu_geteilt"] = await _neu_geteilt_fuer_psm(session, current_user.id, stichtag_neu)
        kontext["offene_unterstuetzungsanfragen"] = await _offene_anfragen_fuer_psm(session, current_user.id)

    return templates.TemplateResponse(request, "dashboard.html", kontext)
