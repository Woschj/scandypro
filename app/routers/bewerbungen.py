from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlmodel import select

from app.core.access import require_owner
from app.core.audit import protokolliere
from app.core.deps import CurrentUser, SessionDep, verify_csrf
from app.core.pdf_merge import unterlagen_zu_pdf
from app.core.templating import templates
from app.core.uploads import datei_lesen_entschluesselt, datei_loeschen, datei_speichern
from app.models.audit import AuditAktion, AuditZieltyp
from app.models.bewerbung import (
    Bewerbung,
    BewerbungsFreigabe,
    BewerbungsFreigabeUmfang,
    Bewerbungsunterlage,
    BewerbungStatus,
    UnterlagenKategorie,
)
from app.models.organisation import BerufstrainerZuordnung
from app.models.user import RoleEnum, User

router = APIRouter(prefix="/bewerbungen", tags=["bewerbungen"], dependencies=[Depends(verify_csrf)])

STAMM_KATEGORIEN = (UnterlagenKategorie.lebenslauf, UnterlagenKategorie.zeugnis)
WARTET_AUF_RUECKMELDUNG = (BewerbungStatus.versendet, BewerbungStatus.rueckmeldung_offen)
EINBETTBARE_ENDUNGEN = (".pdf", ".jpg", ".jpeg", ".png")


def _ist_einbettbar(dateiname: str) -> bool:
    """Nur PDF/Bild lassen sich ins Gesamt-PDF einbetten (siehe
    app/core/pdf_merge.py) - Word-Dokumente werden dort übersprungen. Dient
    hier nur der sichtbaren Warnung in der Übersicht, damit ein Anschreiben
    nie stillschweigend aus dem Export fehlt."""
    return dateiname.lower().endswith(EINBETTBARE_ENDUNGEN)


def _ausstehende_rueckmeldungen(bewerbungen: list[Bewerbung]) -> list[dict]:
    """Bewerbungen, bei denen noch eine Rückmeldung aussteht - für die
    Übersicht gebündelt, damit Teilnehmer:innen nicht den Überblick
    verlieren, worauf sie noch warten (keine Alarm-Optik, siehe
    CLAUDE.md §24 "Emotionale Sicherheit")."""
    heute = date.today()
    eintraege = []
    for bewerbung in bewerbungen:
        if bewerbung.status not in WARTET_AUF_RUECKMELDUNG:
            continue
        tage_seit_versand = (heute - bewerbung.beworben_am).days if bewerbung.beworben_am else None
        tage_bis_termin = (bewerbung.naechster_termin - heute).days if bewerbung.naechster_termin else None
        if bewerbung.naechster_termin is not None:
            sortierschluessel = (0, bewerbung.naechster_termin)
        else:
            sortierschluessel = (1, bewerbung.beworben_am or date.min)
        eintraege.append(
            {
                "bewerbung": bewerbung,
                "tage_seit_versand": tage_seit_versand,
                "tage_bis_termin": tage_bis_termin,
                "sortierschluessel": sortierschluessel,
            }
        )
    eintraege.sort(key=lambda e: e["sortierschluessel"])
    return eintraege


@router.get("", response_class=HTMLResponse)
async def uebersicht(request: Request, current_user: CurrentUser, session: SessionDep):
    if current_user.role != RoleEnum.teilnehmer:
        return templates.TemplateResponse(
            request,
            "bewerbungen/kein_zugriff.html",
            {"current_user": current_user},
            status_code=403,
        )

    result = await session.execute(
        select(Bewerbung)
        .where(Bewerbung.teilnehmer_id == current_user.id)
        .order_by(Bewerbung.erstellt_am.desc())
    )
    bewerbungen = list(result.scalars().all())

    unterlagen_result = await session.execute(
        select(Bewerbungsunterlage)
        .where(Bewerbungsunterlage.teilnehmer_id == current_user.id)
        .order_by(Bewerbungsunterlage.reihenfolge, Bewerbungsunterlage.id)
    )
    alle_unterlagen = list(unterlagen_result.scalars().all())
    stammunterlagen = [u for u in alle_unterlagen if u.kategorie in STAMM_KATEGORIEN]
    anschreiben_by_bewerbung: dict[int, list[Bewerbungsunterlage]] = {}
    deckblatt_by_bewerbung: dict[int, list[Bewerbungsunterlage]] = {}
    for u in alle_unterlagen:
        if u.bewerbung_id is None:
            continue
        if u.kategorie == UnterlagenKategorie.anschreiben:
            anschreiben_by_bewerbung.setdefault(u.bewerbung_id, []).append(u)
        elif u.kategorie == UnterlagenKategorie.deckblatt:
            deckblatt_by_bewerbung.setdefault(u.bewerbung_id, []).append(u)

    nicht_einbettbare_ids = {u.id for u in alle_unterlagen if not _ist_einbettbar(u.original_dateiname)}

    freigaben_result = await session.execute(
        select(BewerbungsFreigabe)
        .where(BewerbungsFreigabe.teilnehmer_id == current_user.id, BewerbungsFreigabe.widerrufen_am.is_(None))
        .order_by(BewerbungsFreigabe.erstellt_am.desc())
    )
    freigaben = list(freigaben_result.scalars().all())

    trainer_result = await session.execute(
        select(BerufstrainerZuordnung).where(BerufstrainerZuordnung.teilnehmer_id == current_user.id)
    )
    trainer_zuordnung = trainer_result.scalar_one_or_none()
    trainer_kontakt = await session.get(User, trainer_zuordnung.berufstrainer_id) if trainer_zuordnung else None

    bewerbung_by_id = {b.id: b for b in bewerbungen}

    return templates.TemplateResponse(
        request,
        "bewerbungen/uebersicht.html",
        {
            "current_user": current_user,
            "bewerbungen": bewerbungen,
            "bewerbung_by_id": bewerbung_by_id,
            "status_optionen": list(BewerbungStatus),
            "stammunterlagen": stammunterlagen,
            "anschreiben_by_bewerbung": anschreiben_by_bewerbung,
            "deckblatt_by_bewerbung": deckblatt_by_bewerbung,
            "nicht_einbettbare_ids": nicht_einbettbare_ids,
            "ausstehende_rueckmeldungen": _ausstehende_rueckmeldungen(bewerbungen),
            "freigaben": freigaben,
            "trainer_kontakt": trainer_kontakt,
        },
    )


@router.post("")
async def bewerbung_erstellen(
    current_user: CurrentUser,
    session: SessionDep,
    firma: str = Form(...),
    position: str = Form(...),
    beworben_am: str = Form(""),
    naechster_termin: str = Form(""),
    notizen: str = Form(""),
    deckblatt: UploadFile | None = None,
    anschreiben: UploadFile | None = None,
):
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    bewerbung = Bewerbung(
        teilnehmer_id=current_user.id,
        firma=firma,
        position=position,
        beworben_am=date.fromisoformat(beworben_am) if beworben_am else None,
        naechster_termin=date.fromisoformat(naechster_termin) if naechster_termin else None,
        notizen=notizen or None,
    )
    session.add(bewerbung)
    await session.flush()

    for datei, kategorie in (
        (deckblatt, UnterlagenKategorie.deckblatt),
        (anschreiben, UnterlagenKategorie.anschreiben),
    ):
        if datei is not None and datei.filename:
            original_dateiname, speicherpfad, groesse = await datei_speichern(datei, f"bewerbungen/{current_user.id}")
            session.add(
                Bewerbungsunterlage(
                    teilnehmer_id=current_user.id,
                    kategorie=kategorie,
                    bewerbung_id=bewerbung.id,
                    original_dateiname=original_dateiname,
                    speicherpfad=speicherpfad,
                    groesse_bytes=groesse,
                )
            )

    await session.commit()
    return RedirectResponse(url="/bewerbungen", status_code=303)


@router.post("/{bewerbung_id}/status")
async def status_aendern(
    bewerbung_id: int, current_user: CurrentUser, session: SessionDep, status_wert: BewerbungStatus = Form(...)
):
    bewerbung = await session.get(Bewerbung, bewerbung_id)
    if bewerbung is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, bewerbung.teilnehmer_id, "Kein Zugriff auf diese Bewerbung.")
    bewerbung.status = status_wert
    session.add(bewerbung)
    await session.commit()
    return RedirectResponse(url="/bewerbungen", status_code=303)


@router.post("/{bewerbung_id}/loeschen")
async def bewerbung_loeschen(bewerbung_id: int, current_user: CurrentUser, session: SessionDep):
    bewerbung = await session.get(Bewerbung, bewerbung_id)
    if bewerbung is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, bewerbung.teilnehmer_id, "Kein Zugriff auf diese Bewerbung.")

    unterlagen_result = await session.execute(
        select(Bewerbungsunterlage).where(Bewerbungsunterlage.bewerbung_id == bewerbung_id)
    )
    for unterlage in unterlagen_result.scalars().all():
        datei_loeschen(unterlage.speicherpfad)
        await session.delete(unterlage)
    await session.flush()

    await session.delete(bewerbung)
    await session.commit()
    return RedirectResponse(url="/bewerbungen", status_code=303)


@router.post("/freigaben")
async def freigabe_erstellen(
    current_user: CurrentUser,
    session: SessionDep,
    empfaenger_id: int = Form(...),
    umfang: BewerbungsFreigabeUmfang = Form(BewerbungsFreigabeUmfang.alle),
    bewerbung_id: str = Form(""),
    gueltig_bis: str = Form(""),
):
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    empfaenger = await session.get(User, empfaenger_id)
    if empfaenger is None or empfaenger.role != RoleEnum.berufstrainer:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Empfänger:in.")

    ziel_bewerbung_id = None
    if umfang == BewerbungsFreigabeUmfang.einzeln:
        if not bewerbung_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bitte eine Bewerbung auswählen.")
        bewerbung = await session.get(Bewerbung, int(bewerbung_id))
        if bewerbung is None or bewerbung.teilnehmer_id != current_user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Bewerbung.")
        ziel_bewerbung_id = bewerbung.id

    session.add(
        BewerbungsFreigabe(
            teilnehmer_id=current_user.id,
            empfaenger_id=empfaenger_id,
            umfang=umfang,
            bewerbung_id=ziel_bewerbung_id,
            gueltig_bis=date.fromisoformat(gueltig_bis) if gueltig_bis else None,
        )
    )
    await session.commit()
    return RedirectResponse(url="/bewerbungen", status_code=303)


@router.post("/freigaben/{freigabe_id}/widerrufen")
async def freigabe_widerrufen(freigabe_id: int, current_user: CurrentUser, session: SessionDep):
    freigabe = await session.get(BewerbungsFreigabe, freigabe_id)
    if freigabe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, freigabe.teilnehmer_id, "Kein Zugriff auf diese Freigabe.")

    freigabe.widerrufen_am = datetime.utcnow()
    session.add(freigabe)
    await session.commit()
    return RedirectResponse(url="/bewerbungen", status_code=303)


@router.get("/teilnehmer/{teilnehmer_id}", response_class=HTMLResponse)
async def teilnehmer_ansicht(request: Request, teilnehmer_id: int, current_user: CurrentUser, session: SessionDep):
    """Rein lesende Ansicht für Berufstrainer - erfordert sowohl eine
    organisatorische BerufstrainerZuordnung als auch eine aktive Freigabe.
    Zeigt bei Umfang 'einzeln' nur die freigegebenen Bewerbungen, keine
    Dateien (Dokument-Zugriff bleibt in dieser Version beim Owner)."""
    if current_user.role != RoleEnum.berufstrainer:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur Berufstrainer:innen nutzen diese Ansicht.")

    zuordnung_result = await session.execute(
        select(BerufstrainerZuordnung).where(
            BerufstrainerZuordnung.berufstrainer_id == current_user.id,
            BerufstrainerZuordnung.teilnehmer_id == teilnehmer_id,
        )
    )
    if zuordnung_result.first() is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Diese Person ist dir nicht zugeordnet.")

    heute = date.today()
    freigaben_result = await session.execute(
        select(BewerbungsFreigabe).where(
            BewerbungsFreigabe.teilnehmer_id == teilnehmer_id,
            BewerbungsFreigabe.empfaenger_id == current_user.id,
            BewerbungsFreigabe.widerrufen_am.is_(None),
        )
    )
    freigaben = [
        f for f in freigaben_result.scalars().all() if f.gueltig_bis is None or f.gueltig_bis >= heute
    ]
    if not freigaben:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Keine aktive Freigabe für diese Person.")

    teilnehmer = await session.get(User, teilnehmer_id)
    if teilnehmer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    hat_alle = any(f.umfang == BewerbungsFreigabeUmfang.alle for f in freigaben)
    einzeln_ids = {f.bewerbung_id for f in freigaben if f.umfang == BewerbungsFreigabeUmfang.einzeln}

    alle_bewerbungen_result = await session.execute(
        select(Bewerbung).where(Bewerbung.teilnehmer_id == teilnehmer_id).order_by(Bewerbung.erstellt_am.desc())
    )
    alle_bewerbungen = list(alle_bewerbungen_result.scalars().all())
    sichtbare_bewerbungen = alle_bewerbungen if hat_alle else [b for b in alle_bewerbungen if b.id in einzeln_ids]

    await protokolliere(
        session,
        akteur_id=current_user.id,
        aktion=AuditAktion.bewerbung_gelesen,
        zieltyp=AuditZieltyp.bewerbung,
        ziel_teilnehmer_id=teilnehmer_id,
        grundlage_freigabe_id=freigaben[0].id,
    )

    return templates.TemplateResponse(
        request,
        "bewerbungen/teilnehmer_ansicht.html",
        {
            "current_user": current_user,
            "teilnehmer": teilnehmer,
            "bewerbungen": sichtbare_bewerbungen,
        },
    )


@router.post("/unterlagen")
async def unterlage_hochladen(
    current_user: CurrentUser,
    session: SessionDep,
    datei: UploadFile,
    kategorie: UnterlagenKategorie = Form(...),
):
    if current_user.role != RoleEnum.teilnehmer:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    if kategorie not in STAMM_KATEGORIEN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Kategorie für diesen Upload.")

    max_reihenfolge_result = await session.execute(
        select(Bewerbungsunterlage.reihenfolge)
        .where(
            Bewerbungsunterlage.teilnehmer_id == current_user.id,
            Bewerbungsunterlage.kategorie.in_(STAMM_KATEGORIEN),
        )
        .order_by(Bewerbungsunterlage.reihenfolge.desc())
    )
    naechste_reihenfolge = (max_reihenfolge_result.scalars().first() or 0) + 1

    original_dateiname, speicherpfad, groesse = await datei_speichern(datei, f"bewerbungen/{current_user.id}")
    session.add(
        Bewerbungsunterlage(
            teilnehmer_id=current_user.id,
            kategorie=kategorie,
            original_dateiname=original_dateiname,
            speicherpfad=speicherpfad,
            groesse_bytes=groesse,
            reihenfolge=naechste_reihenfolge,
        )
    )
    await session.commit()
    return RedirectResponse(url="/bewerbungen", status_code=303)


async def _stammunterlage_verschieben(
    session: SessionDep, current_user: CurrentUser, unterlage_id: int, richtung: int
) -> None:
    unterlage = await session.get(Bewerbungsunterlage, unterlage_id)
    if unterlage is None or unterlage.kategorie not in STAMM_KATEGORIEN:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, unterlage.teilnehmer_id, "Kein Zugriff auf diese Datei.")

    result = await session.execute(
        select(Bewerbungsunterlage)
        .where(
            Bewerbungsunterlage.teilnehmer_id == current_user.id,
            Bewerbungsunterlage.kategorie.in_(STAMM_KATEGORIEN),
        )
        .order_by(Bewerbungsunterlage.reihenfolge, Bewerbungsunterlage.id)
    )
    liste = list(result.scalars().all())
    index = next(i for i, u in enumerate(liste) if u.id == unterlage_id)
    nachbar_index = index + richtung
    if 0 <= nachbar_index < len(liste):
        liste[index], liste[nachbar_index] = liste[nachbar_index], liste[index]
        for i, u in enumerate(liste):
            u.reihenfolge = i
            session.add(u)
        await session.commit()


@router.post("/unterlagen/{unterlage_id}/nach-oben")
async def unterlage_nach_oben(unterlage_id: int, current_user: CurrentUser, session: SessionDep):
    await _stammunterlage_verschieben(session, current_user, unterlage_id, richtung=-1)
    return RedirectResponse(url="/bewerbungen", status_code=303)


@router.post("/unterlagen/{unterlage_id}/nach-unten")
async def unterlage_nach_unten(unterlage_id: int, current_user: CurrentUser, session: SessionDep):
    await _stammunterlage_verschieben(session, current_user, unterlage_id, richtung=1)
    return RedirectResponse(url="/bewerbungen", status_code=303)


@router.post("/{bewerbung_id}/anschreiben")
async def anschreiben_hochladen(
    bewerbung_id: int, current_user: CurrentUser, session: SessionDep, datei: UploadFile
):
    bewerbung = await session.get(Bewerbung, bewerbung_id)
    if bewerbung is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, bewerbung.teilnehmer_id, "Kein Zugriff auf diese Bewerbung.")

    original_dateiname, speicherpfad, groesse = await datei_speichern(datei, f"bewerbungen/{current_user.id}")
    session.add(
        Bewerbungsunterlage(
            teilnehmer_id=current_user.id,
            kategorie=UnterlagenKategorie.anschreiben,
            bewerbung_id=bewerbung_id,
            original_dateiname=original_dateiname,
            speicherpfad=speicherpfad,
            groesse_bytes=groesse,
        )
    )
    await session.commit()
    return RedirectResponse(url="/bewerbungen", status_code=303)


@router.post("/{bewerbung_id}/deckblatt")
async def deckblatt_hochladen(
    bewerbung_id: int, current_user: CurrentUser, session: SessionDep, datei: UploadFile
):
    bewerbung = await session.get(Bewerbung, bewerbung_id)
    if bewerbung is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, bewerbung.teilnehmer_id, "Kein Zugriff auf diese Bewerbung.")

    original_dateiname, speicherpfad, groesse = await datei_speichern(datei, f"bewerbungen/{current_user.id}")
    session.add(
        Bewerbungsunterlage(
            teilnehmer_id=current_user.id,
            kategorie=UnterlagenKategorie.deckblatt,
            bewerbung_id=bewerbung_id,
            original_dateiname=original_dateiname,
            speicherpfad=speicherpfad,
            groesse_bytes=groesse,
        )
    )
    await session.commit()
    return RedirectResponse(url="/bewerbungen", status_code=303)


@router.get("/unterlagen/{unterlage_id}/download")
async def unterlage_herunterladen(unterlage_id: int, current_user: CurrentUser, session: SessionDep):
    unterlage = await session.get(Bewerbungsunterlage, unterlage_id)
    if unterlage is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, unterlage.teilnehmer_id, "Kein Zugriff auf diese Datei.")

    inhalt = await datei_lesen_entschluesselt(unterlage.speicherpfad)
    return Response(
        content=inhalt,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{unterlage.original_dateiname}"'},
    )


@router.get("/{bewerbung_id}/pdf")
async def bewerbung_pdf_erzeugen(bewerbung_id: int, current_user: CurrentUser, session: SessionDep):
    bewerbung = await session.get(Bewerbung, bewerbung_id)
    if bewerbung is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, bewerbung.teilnehmer_id, "Kein Zugriff auf diese Bewerbung.")

    deckblatt_result = await session.execute(
        select(Bewerbungsunterlage)
        .where(
            Bewerbungsunterlage.bewerbung_id == bewerbung_id,
            Bewerbungsunterlage.kategorie == UnterlagenKategorie.deckblatt,
        )
        .order_by(Bewerbungsunterlage.hochgeladen_am.desc())
    )
    deckblatt = deckblatt_result.scalars().first()

    anschreiben_result = await session.execute(
        select(Bewerbungsunterlage)
        .where(
            Bewerbungsunterlage.bewerbung_id == bewerbung_id,
            Bewerbungsunterlage.kategorie == UnterlagenKategorie.anschreiben,
        )
        .order_by(Bewerbungsunterlage.hochgeladen_am.desc())
    )
    anschreiben = anschreiben_result.scalars().first()

    stammunterlagen_result = await session.execute(
        select(Bewerbungsunterlage)
        .where(
            Bewerbungsunterlage.teilnehmer_id == current_user.id,
            Bewerbungsunterlage.kategorie.in_(STAMM_KATEGORIEN),
        )
        .order_by(Bewerbungsunterlage.reihenfolge, Bewerbungsunterlage.id)
    )
    stammunterlagen = list(stammunterlagen_result.scalars().all())

    # Deckblatt vor Anschreiben vor den vom Teilnehmer sortierten Lebenslauf-/
    # Zeugnis-Unterlagen (siehe Docstring Bewerbungsunterlage.reihenfolge).
    unterlagen_in_reihenfolge = [u for u in (deckblatt, anschreiben) if u is not None] + stammunterlagen
    if not unterlagen_in_reihenfolge:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Keine Unterlagen vorhanden - lade zuerst Anschreiben, Lebenslauf oder Zeugnisse hoch.",
        )

    entschluesselte_dateien = [
        (u.original_dateiname, await datei_lesen_entschluesselt(u.speicherpfad)) for u in unterlagen_in_reihenfolge
    ]
    pdf_bytes, uebersprungen = unterlagen_zu_pdf(entschluesselte_dateien)

    dateiname = f"Bewerbung_{bewerbung.firma}.pdf".replace(" ", "_")
    headers = {"Content-Disposition": f'attachment; filename="{dateiname}"'}
    if uebersprungen:
        headers["X-Nicht-Eingebunden"] = ", ".join(uebersprungen)
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@router.post("/unterlagen/{unterlage_id}/loeschen")
async def unterlage_loeschen(unterlage_id: int, current_user: CurrentUser, session: SessionDep):
    unterlage = await session.get(Bewerbungsunterlage, unterlage_id)
    if unterlage is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_owner(current_user, unterlage.teilnehmer_id, "Kein Zugriff auf diese Datei.")

    datei_loeschen(unterlage.speicherpfad)
    await session.delete(unterlage)
    await session.commit()
    return RedirectResponse(url="/bewerbungen", status_code=303)
