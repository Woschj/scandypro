import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

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


@app.get("/")
async def dashboard(request: Request, session: SessionDep):
    current_user = await get_current_user_optional(request, session)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=303)

    psm_kontakt = None
    trainer_kontakt = None
    schritte_diese_woche: int | None = None
    tagebuch_tage_woche: int | None = None
    bewerbungen_uebersicht: dict | None = None
    was_steht_an: list[dict] = []
    letzte_kanban_aktivitaet: dict | None = None
    letztes_tagebuch_wort: str | None = None
    letzte_aktive_bewerbung: str | None = None
    neu_geteilt: list[dict] = []
    offene_unterstuetzungsanfragen: list[dict] = []

    if current_user.role in (RoleEnum.teilnehmer, RoleEnum.berufstrainer):
        was_steht_an = await faellige_karten(session, current_user)

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

        schritte_diese_woche = await woechentliche_schritte(session, current_user.id)
        tagebuch_tage_woche = await woechentliche_tagebuch_tage(session, current_user.id)

        # Sanfter Bewerbungs-Überblick fürs Dashboard (siehe CLAUDE.md Abschnitt
        # 25 "positive Verstärkung") - bewusst nur Zählwerte, keine Rücklauf-
        # quote/Bewertung; "aktiv" schließt Entwürfe aus, die noch keine
        # eigene Handlung der Person waren.
        aktive_result = await session.execute(
            select(Bewerbung.id).where(
                Bewerbung.teilnehmer_id == current_user.id, Bewerbung.status != BewerbungStatus.entwurf
            )
        )
        anzahl_aktiv = len(list(aktive_result.scalars().all()))
        wartend_result = await session.execute(
            select(Bewerbung.id).where(
                Bewerbung.teilnehmer_id == current_user.id,
                Bewerbung.status.in_([BewerbungStatus.versendet, BewerbungStatus.rueckmeldung_offen]),
            )
        )
        anzahl_wartend = len(list(wartend_result.scalars().all()))
        if anzahl_aktiv > 0:
            bewerbungen_uebersicht = {"aktiv": anzahl_aktiv, "wartend": anzahl_wartend}
            letzte_bewerbung_result = await session.execute(
                select(Bewerbung.firma)
                .where(Bewerbung.teilnehmer_id == current_user.id, Bewerbung.status != BewerbungStatus.entwurf)
                .order_by(Bewerbung.erstellt_am.desc())
                .limit(1)
            )
            letzte_aktive_bewerbung = letzte_bewerbung_result.scalar_one_or_none()

        # Persönliche Anknüpfungspunkte für die Rückblick-Kacheln (siehe
        # dashboard.html) - zeigen konkret, was zuletzt/als Nächstes ansteht,
        # statt nur abstrakter Zahlen; bewusst nur positiv formuliert, nie als
        # Mahnung (CLAUDE.md §24).
        if schritte_diese_woche:
            seit = datetime.utcnow() - timedelta(days=7)
            letzte_bewegung_result = await session.execute(
                select(Karte.titel, Board.id, Board.titel)
                .select_from(KartenBewegung)
                .join(Karte, Karte.id == KartenBewegung.karte_id)
                .join(Spalte, Spalte.id == Karte.spalte_id)
                .join(Board, Board.id == Spalte.board_id)
                .where(KartenBewegung.bewegt_von_id == current_user.id, KartenBewegung.bewegt_am >= seit)
                .order_by(KartenBewegung.bewegt_am.desc())
                .limit(1)
            )
            treffer = letzte_bewegung_result.first()
            if treffer is not None:
                karten_titel, board_id, board_titel = treffer
                letzte_kanban_aktivitaet = {
                    "titel": karten_titel,
                    "link": f"/kanban/boards/{board_id}",
                    "kontext": board_titel,
                }
        elif was_steht_an:
            letzte_kanban_aktivitaet = was_steht_an[0]

        letztes_wort_result = await session.execute(
            select(TagebuchEintrag.wort_des_tages)
            .where(TagebuchEintrag.teilnehmer_id == current_user.id, TagebuchEintrag.wort_des_tages.is_not(None))
            .order_by(TagebuchEintrag.datum.desc())
            .limit(1)
        )
        letztes_tagebuch_wort = letztes_wort_result.scalar_one_or_none()

    # "Neu geteilt" fürs Dashboard von Berufstrainer:in/PSM: bewusst nur ein
    # schmaler Hinweis (letzte 14 Tage, jederzeit widerrufbare Freigabe),
    # kein separates Postfach/Ungelesen-System - passend zu CLAUDE.md
    # Abschnitt 24 "keine automatischen Eskalationen".
    stichtag_neu = datetime.utcnow() - timedelta(days=14)
    if current_user.role == RoleEnum.berufstrainer:
        freigaben_result = await session.execute(
            select(BewerbungsFreigabe)
            .where(
                BewerbungsFreigabe.empfaenger_id == current_user.id,
                BewerbungsFreigabe.widerrufen_am.is_(None),
                BewerbungsFreigabe.erstellt_am >= stichtag_neu,
            )
            .order_by(BewerbungsFreigabe.erstellt_am.desc())
        )
        for freigabe in freigaben_result.scalars().all():
            teilnehmer = await session.get(User, freigabe.teilnehmer_id)
            neu_geteilt.append(
                {
                    "teilnehmer": teilnehmer,
                    "text": "hat dir Bewerbungsdaten freigegeben",
                    "erstellt_am": freigabe.erstellt_am,
                    "link": f"/bewerbungen/teilnehmer/{freigabe.teilnehmer_id}",
                }
            )
    elif current_user.role == RoleEnum.psychosoziale_mitarbeit:
        freigaben_result = await session.execute(
            select(WohlbefindenFreigabe)
            .where(
                WohlbefindenFreigabe.empfaenger_id == current_user.id,
                WohlbefindenFreigabe.widerrufen_am.is_(None),
                WohlbefindenFreigabe.erstellt_am >= stichtag_neu,
            )
            .order_by(WohlbefindenFreigabe.erstellt_am.desc())
        )
        for freigabe in freigaben_result.scalars().all():
            teilnehmer = await session.get(User, freigabe.teilnehmer_id)
            text = (
                "hat dir einen einzelnen Tag freigegeben"
                if freigabe.umfang.value == "einzeln"
                else "hat dir 'Mein Tag' freigegeben"
            )
            neu_geteilt.append(
                {
                    "teilnehmer": teilnehmer,
                    "text": text,
                    "erstellt_am": freigabe.erstellt_am,
                    "link": f"/wohlbefinden/teilnehmer/{freigabe.teilnehmer_id}",
                }
            )

        anfragen_result = await session.execute(
            select(Unterstuetzungsanfrage)
            .where(
                Unterstuetzungsanfrage.empfaenger_id == current_user.id,
                Unterstuetzungsanfrage.gesehen_am.is_(None),
            )
            .order_by(Unterstuetzungsanfrage.erstellt_am.desc())
        )
        for anfrage in anfragen_result.scalars().all():
            teilnehmer = await session.get(User, anfrage.teilnehmer_id)
            offene_unterstuetzungsanfragen.append({"anfrage": anfrage, "teilnehmer": teilnehmer})

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "current_user": current_user,
            "psm_kontakt": psm_kontakt,
            "trainer_kontakt": trainer_kontakt,
            "schritte_diese_woche": schritte_diese_woche,
            "tagebuch_tage_woche": tagebuch_tage_woche,
            "bewerbungen_uebersicht": bewerbungen_uebersicht,
            "letzte_kanban_aktivitaet": letzte_kanban_aktivitaet,
            "letztes_tagebuch_wort": letztes_tagebuch_wort,
            "letzte_aktive_bewerbung": letzte_aktive_bewerbung,
            "was_steht_an": was_steht_an,
            "neu_geteilt": neu_geteilt,
            "offene_unterstuetzungsanfragen": offene_unterstuetzungsanfragen,
        },
    )
