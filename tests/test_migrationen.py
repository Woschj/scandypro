"""Strukturtests der Alembic-Migrationskette.

Hintergrund: Die Tests bauen ihr Schema über `SQLModel.metadata.create_all`
(siehe tests/conftest.py) - Alembic läuft dabei **nie**. Die Migrationen
werden also erst beim Start der echten App ausgeführt
(`app/core/database.py:init_db`), und wenn dort etwas nicht stimmt, startet
die Anwendung gar nicht.

Genau das ist bereits passiert: eine neue Migration bekam versehentlich
dieselbe Revision-ID wie eine ältere, Alembic fand daraufhin zwei Heads und
brach ab - der Fehler fiel erst auf dem Server auf.

Diese Tests prüfen die Kette deshalb statisch, ohne Datenbank. Sie ersetzen
keinen echten `alembic upgrade head` gegen PostgreSQL (Postgres-spezifisches
SQL wie `ALTER TYPE ... ADD VALUE` lässt sich hier nicht ausführen), fangen
aber die Fehlerklasse ab, die tatsächlich zum Ausfall geführt hat.
"""
import pathlib
import re

VERSIONEN = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _revisionen() -> dict[str, dict]:
    """Liest revision/down_revision aus allen Migrationsdateien."""
    gefunden: dict[str, dict] = {}
    for pfad in sorted(VERSIONEN.glob("*.py")):
        text = pfad.read_text(encoding="utf-8")
        rev = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', text, re.M)
        down = re.search(r'^down_revision(?::[^=]+)?=\s*(?:["\']([^"\']+)["\']|None)', text, re.M)
        assert rev, f"{pfad.name}: keine revision gefunden"
        assert down, f"{pfad.name}: kein down_revision gefunden"
        gefunden.setdefault(rev.group(1), {"dateien": [], "down": down.group(1)})
        gefunden[rev.group(1)]["dateien"].append(pfad.name)
    return gefunden


def test_keine_doppelten_revision_ids():
    """Der Fehler, der die App schon einmal lahmgelegt hat: zwei Dateien mit
    derselben Revision-ID -> Alembic meldet "Multiple head revisions"."""
    doppelt = {rev: d["dateien"] for rev, d in _revisionen().items() if len(d["dateien"]) > 1}
    assert doppelt == {}, f"Revision-IDs mehrfach vergeben: {doppelt}"


def test_genau_ein_head():
    revisionen = _revisionen()
    referenziert = {d["down"] for d in revisionen.values() if d["down"]}
    heads = sorted(set(revisionen) - referenziert)
    assert len(heads) == 1, f"Erwartet genau einen Head, gefunden: {heads}"


def test_genau_eine_wurzel_und_lueckenlose_kette():
    revisionen = _revisionen()
    wurzeln = [rev for rev, d in revisionen.items() if d["down"] is None]
    assert len(wurzeln) == 1, f"Erwartet genau eine Wurzelmigration, gefunden: {wurzeln}"

    # Jedes down_revision muss auf eine existierende Revision zeigen.
    unbekannt = {
        rev: d["down"] for rev, d in revisionen.items() if d["down"] and d["down"] not in revisionen
    }
    assert unbekannt == {}, f"down_revision zeigt ins Leere: {unbekannt}"

    # Von der Wurzel aus muss jede Revision erreichbar sein (keine Insel).
    nachfolger: dict[str, str] = {d["down"]: rev for rev, d in revisionen.items() if d["down"]}
    kette, aktuell = [wurzeln[0]], wurzeln[0]
    while aktuell in nachfolger:
        aktuell = nachfolger[aktuell]
        kette.append(aktuell)
    assert len(kette) == len(revisionen), (
        f"Kette erreicht nur {len(kette)} von {len(revisionen)} Migrationen - "
        f"nicht erreichbar: {sorted(set(revisionen) - set(kette))}"
    )


def test_alembic_selbst_findet_einen_head():
    """Gegenprobe mit Alembics eigenem Parser statt unserer Regex - fängt
    Fälle ab, in denen die Datei zwar regex-konform aussieht, Alembic sie
    aber anders liest."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    skripte = ScriptDirectory.from_config(Config(str(VERSIONEN.parent.parent / "alembic.ini")))
    heads = skripte.get_heads()
    assert len(heads) == 1, f"Alembic meldet mehrere Heads: {heads}"


def test_modellfelder_haben_eine_migration():
    """Grober Drift-Check: Die Tests bauen ihr Schema aus den Modellen, die
    Produktion aus den Migrationen - beide können auseinanderlaufen, ohne
    dass es auffällt. Hier wird stichprobenartig geprüft, dass jede Spalte
    von TagebuchEintrag irgendwo in den Migrationen vorkommt.

    Kein Ersatz für einen echten Migrationslauf, aber es fängt den
    häufigsten Fall: Feld am Modell ergänzt, Migration vergessen."""
    import app.models  # noqa: F401  (registriert alle Tabellen)
    from app.models.wohlbefinden import TagebuchEintrag

    alle_migrationen = "\n".join(p.read_text(encoding="utf-8") for p in VERSIONEN.glob("*.py"))
    fehlend = [
        name
        for name in TagebuchEintrag.model_fields
        if f'"{name}"' not in alle_migrationen and f"'{name}'" not in alle_migrationen
    ]
    assert fehlend == [], f"Modellfelder ohne Migration: {fehlend}"
