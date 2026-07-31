"""Demo-Daten für die Prototyp-Bewertung.

Wird nur ausgeführt, wenn SEED_DEMO_DATA=true UND die User-Tabelle leer ist.
Erzeugt für jede Rolle einen Login sowie eine Beispiel-Organisationsstruktur
(Abteilung, Handlungsfeld mit Leitung, Teilnehmergruppe, freigegebenes
Board, PSM-Zuordnung, ein abgegebener Wochenbericht), damit die
Kernfunktionalität ohne manuelles Anlegen von Grunddaten durchgeklickt
werden kann.
"""

import logging
from datetime import datetime, timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import hash_password
from app.models.kanban import Board, BoardFreigabe, BoardTyp, Karte, KartenSichtbarkeit, KartenZuweisung, Spalte, Unteraufgabe
from app.models.organisation import (
    Abteilung,
    BerufstrainerZuordnung,
    Handlungsfeld,
    HandlungsfeldLeitung,
    HandlungsfeldMitglied,
    PsmZuordnung,
    Teilnehmergruppe,
    TeilnehmergruppeMitglied,
)
from app.models.user import RoleEnum, User
from app.models.wochenbericht import Wochenbericht, WochenberichtStatus, leere_tage
from app.models.wohlbefinden import WohlbefindenEintrag

logger = logging.getLogger(__name__)

DEMO_PASSWORD = "demo1234"

ABTEILUNGEN = ["Medien & Digital", "Technik", "Service", "Kaufmännisches"]

DEMO_USERS = [
    ("Tanja Teilnehmer", "teilnehmer@demo.local", RoleEnum.teilnehmer, "Medien & Digital"),
    ("Klaus Kollege", "teilnehmer2@demo.local", RoleEnum.teilnehmer, "Medien & Digital"),
    ("Bernd Berufstrainer", "trainer@demo.local", RoleEnum.berufstrainer, None),
    ("Petra Psychosozial", "psycho@demo.local", RoleEnum.psychosoziale_mitarbeit, None),
    ("Anna Admin", "admin@demo.local", RoleEnum.einrichtungs_admin, None),
]

STANDARD_SPALTEN = ["Offen", "In Arbeit", "Wartet", "Erledigt"]


async def seed_demo_data(session: AsyncSession) -> None:
    existing = await session.execute(select(User))
    if existing.first() is not None:
        return

    logger.warning("SEED_DEMO_DATA aktiv: lege Demo-Daten an (Passwort: %s)", DEMO_PASSWORD)

    abteilung_by_name: dict[str, Abteilung] = {}
    for name in ABTEILUNGEN:
        abteilung = Abteilung(name=name)
        session.add(abteilung)
        abteilung_by_name[name] = abteilung
    await session.flush()

    users: dict[str, User] = {}
    for name, email, role, abteilung_name in DEMO_USERS:
        abteilung_id = abteilung_by_name[abteilung_name].id if abteilung_name else None
        user = User(
            name=name,
            email=email,
            password_hash=hash_password(DEMO_PASSWORD),
            role=role,
            abteilung_id=abteilung_id,
        )
        session.add(user)
        users[email] = user
    await session.flush()

    medien = abteilung_by_name["Medien & Digital"]
    trainer = users["trainer@demo.local"]

    handlungsfeld = Handlungsfeld(name="Video-Projekte", abteilung_id=medien.id)
    session.add(handlungsfeld)
    await session.flush()

    session.add(HandlungsfeldLeitung(handlungsfeld_id=handlungsfeld.id, berufstrainer_id=trainer.id))

    gruppe = Teilnehmergruppe(name="Projektteam Video", handlungsfeld_id=handlungsfeld.id, erstellt_von=trainer.id)
    session.add(gruppe)
    await session.flush()

    for email in ("teilnehmer@demo.local", "teilnehmer2@demo.local"):
        session.add(HandlungsfeldMitglied(handlungsfeld_id=handlungsfeld.id, teilnehmer_id=users[email].id))
        session.add(TeilnehmergruppeMitglied(gruppe_id=gruppe.id, teilnehmer_id=users[email].id))

    board = Board(titel="Imagefilm Werkstatt", handlungsfeld_id=handlungsfeld.id, ersteller_id=trainer.id)
    session.add(board)
    await session.flush()

    session.add(BoardFreigabe(board_id=board.id, gruppe_id=gruppe.id))

    spalten = []
    for i, spalten_name in enumerate(STANDARD_SPALTEN):
        spalte = Spalte(board_id=board.id, name=spalten_name, reihenfolge=i)
        session.add(spalte)
        spalten.append(spalte)
    await session.flush()

    heute = datetime.utcnow().date()
    tanja = users["teilnehmer@demo.local"]
    klaus = users["teilnehmer2@demo.local"]
    offen, in_arbeit, wartet, erledigt = spalten

    karten_plan = [
        (
            offen,
            "Drehbuch abstimmen",
            "Mit beiden im Team besprechen",
            heute + timedelta(days=4),
            [tanja.id, klaus.id],
            [("Szenen 1-5 gegenlesen", True), ("Dialoge abstimmen", False)],
        ),
        (offen, "Location Scouting", "Zwei bis drei mögliche Drehorte finden.", heute + timedelta(days=9), [klaus.id], []),
        (offen, "Sprecher:in casten", None, None, [], []),
        (
            in_arbeit,
            "Kameraequipment reservieren",
            None,
            heute - timedelta(days=2),
            [tanja.id],
            [("Kamera anfragen", True), ("Stativ anfragen", True), ("Mikrofon anfragen", False)],
        ),
        (
            in_arbeit,
            "Storyboard zeichnen",
            "Grobe Skizzen für die ersten drei Szenen.",
            heute + timedelta(days=2),
            [tanja.id, klaus.id],
            [],
        ),
        (
            wartet,
            "Genehmigung Drehort",
            "Rückmeldung der Location steht noch aus.",
            heute + timedelta(days=6),
            [klaus.id],
            [],
        ),
        (erledigt, "Kickoff-Meeting", "Alle Beteiligten abgeholt.", None, [tanja.id, klaus.id], [("Termin gefunden", True), ("Agenda verschickt", True)]),
        (erledigt, "Konzept genehmigt", None, None, [tanja.id], []),
    ]

    for spalte, titel, beschreibung, faelligkeit, zugewiesene, unteraufgaben in karten_plan:
        karte = Karte(
            spalte_id=spalte.id,
            titel=titel,
            beschreibung=beschreibung,
            faelligkeit=faelligkeit,
            ersteller_id=trainer.id,
            reihenfolge=0,
        )
        session.add(karte)
        await session.flush()

        for teilnehmer_id in zugewiesene:
            session.add(KartenZuweisung(karte_id=karte.id, teilnehmer_id=teilnehmer_id))
        for i, (ua_titel, ua_erledigt) in enumerate(unteraufgaben):
            session.add(Unteraufgabe(karte_id=karte.id, titel=ua_titel, erledigt=ua_erledigt, reihenfolge=i))

    persoenliches_board = Board(
        titel="Meine Aufgaben",
        typ=BoardTyp.person,
        person_teilnehmer_id=tanja.id,
        ersteller_id=tanja.id,
    )
    session.add(persoenliches_board)
    await session.flush()

    persoenliche_spalten = []
    for i, spalten_name in enumerate(STANDARD_SPALTEN):
        persoenliche_spalte = Spalte(board_id=persoenliches_board.id, name=spalten_name, reihenfolge=i)
        session.add(persoenliche_spalte)
        persoenliche_spalten.append(persoenliche_spalte)
    await session.flush()

    session.add(
        Karte(
            spalte_id=persoenliche_spalten[0].id,
            titel="Bewerbungsunterlagen aktualisieren",
            beschreibung="Lebenslauf auf den neuesten Stand bringen.",
            faelligkeit=heute + timedelta(days=5),
            ersteller_id=tanja.id,
            sichtbarkeit=KartenSichtbarkeit.privat,
            reihenfolge=0,
        )
    )
    session.add(
        Karte(
            spalte_id=persoenliche_spalten[1].id,
            titel="Praktikumsbericht vorbereiten",
            beschreibung="Trainer hat um eine kurze Zusammenfassung gebeten.",
            ersteller_id=trainer.id,
            sichtbarkeit=KartenSichtbarkeit.team,
            reihenfolge=0,
        )
    )

    session.add(PsmZuordnung(psm_id=users["psycho@demo.local"].id, teilnehmer_id=tanja.id))
    session.add(BerufstrainerZuordnung(berufstrainer_id=trainer.id, teilnehmer_id=klaus.id))

    letzte_kw = datetime.utcnow() - timedelta(days=7)
    demo_tage = leere_tage()
    demo_tage["montag"] = {"start": "08:00", "ende": "16:00", "taetigkeiten": "Drehbuch mit dem Team abgestimmt."}
    demo_tage["dienstag"] = {"start": "08:00", "ende": "16:00", "taetigkeiten": "Erste Szenenliste erstellt."}
    demo_tage["mittwoch"] = {"start": "08:00", "ende": "12:00", "taetigkeiten": "Kameraequipment recherchiert."}
    session.add(
        Wochenbericht(
            teilnehmer_id=users["teilnehmer@demo.local"].id,
            kw_jahr=letzte_kw.isocalendar().year,
            kw_nummer=letzte_kw.isocalendar().week,
            tage=demo_tage,
            besonderheiten="Kameraequipment muss noch reserviert werden.",
            status=WochenberichtStatus.abgegeben,
            abgegeben_am=datetime.utcnow(),
        )
    )

    demo_werte = [
        (6, 5, 6, None),
        (5, 6, 5, None),
        (4, 3, 2, "Anstrengender Tag im Praktikum, aber gut durchgehalten."),
        (3, 6, 6, None),
        (2, 7, 6, None),
        (1, 8, 7, "Gutes Gespräch mit dem Berufstrainer."),
        (0, 7, 8, None),
    ]
    for tage_zurueck, stimmung, belastbarkeit, kommentar in demo_werte:
        session.add(
            WohlbefindenEintrag(
                teilnehmer_id=tanja.id,
                datum=heute - timedelta(days=tage_zurueck),
                stimmung=stimmung,
                belastbarkeit=belastbarkeit,
                kommentar=kommentar,
            )
        )

    await session.commit()
