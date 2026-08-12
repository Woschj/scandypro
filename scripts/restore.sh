#!/usr/bin/env bash
#
# ScandyPro - Wiederherstellung aus einem Backup-Archiv (siehe
# tasks/produktivreife, PR-001 und docs/BACKUP.md).
#
# Aufruf:
#   ./scripts/restore.sh backups/scandypro-2026-08-12T03-00-00.tar.gz.enc
#   ./scripts/restore.sh --pruefen <archiv>   # nur entpacken und anschauen,
#                                             # nichts überschreiben
#
# Der Restore ist bewusst destruktiv und fragt einmal explizit nach: er
# ersetzt den kompletten Inhalt der Zieldatenbank und der Uploads.

set -euo pipefail

PROJEKT_VERZEICHNIS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJEKT_VERZEICHNIS"

NUR_PRUEFEN=nein
if [[ "${1:-}" == "--pruefen" ]]; then
  NUR_PRUEFEN=ja
  shift
fi

ARCHIV="${1:-}"
[[ -n "$ARCHIV" ]] || {
  echo "Aufruf: $0 [--pruefen] <archiv>" >&2
  echo "Vorhandene Archive:" >&2
  # shellcheck disable=SC2012  # Sortierung nach Änderungszeit ist hier der Zweck
  ls -1t "${BACKUP_DIR:-$PROJEKT_VERZEICHNIS/backups}"/scandypro-* 2>/dev/null | head -10 >&2 || echo "  (keine)" >&2
  exit 1
}
[[ -f "$ARCHIV" ]] || { echo "Archiv nicht gefunden: $ARCHIV" >&2; exit 1; }

ENV_DATEI="${ENV_DATEI:-$PROJEKT_VERZEICHNIS/.env}"
if [[ -f "$ENV_DATEI" ]]; then
  # shellcheck disable=SC1090
  set -a && . "$ENV_DATEI" && set +a
fi

POSTGRES_USER="${POSTGRES_USER:-scandypro}"
POSTGRES_DB="${POSTGRES_DB:-scandypro}"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
fehler() { printf 'FEHLER: %s\n' "$*" >&2; exit 1; }

ARBEIT="$(mktemp -d)"
trap 'rm -rf "$ARBEIT"' EXIT

# ---------------------------------------------------------------------------
# 1. Entschlüsseln und entpacken
# ---------------------------------------------------------------------------

if [[ "$ARCHIV" == *.enc ]]; then
  [[ -n "${BACKUP_PASSPHRASE:-}" ]] || fehler "BACKUP_PASSPHRASE nicht gesetzt - ohne sie ist das Archiv nicht lesbar."
  log "Entschlüssele …"
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -in "$ARCHIV" -out "$ARBEIT/archiv.tar.gz" -pass env:BACKUP_PASSPHRASE \
    || fehler "Entschlüsselung fehlgeschlagen - falsche Passphrase oder beschädigtes Archiv."
else
  cp "$ARCHIV" "$ARBEIT/archiv.tar.gz"
fi

tar -xzf "$ARBEIT/archiv.tar.gz" -C "$ARBEIT" || fehler "Archiv ist beschädigt."
[[ -f "$ARBEIT/datenbank.dump" ]] || fehler "Im Archiv fehlt datenbank.dump."

log "Archiv-Inhalt:"
[[ -f "$ARBEIT/backup.info" ]] && sed 's/^/    /' "$ARBEIT/backup.info"
log "    datenbank.dump: $(( $(wc -c < "$ARBEIT/datenbank.dump") / 1024 )) KiB"
[[ -f "$ARBEIT/uploads.tar.gz" ]] && log "    uploads.tar.gz: $(( $(wc -c < "$ARBEIT/uploads.tar.gz") / 1024 )) KiB"

if [[ "$NUR_PRUEFEN" == "ja" ]]; then
  log ""
  log "Prüfmodus - Archiv ist lesbar und vollständig. Nichts verändert."
  exit 0
fi

# ---------------------------------------------------------------------------
# 2. Betriebsart + Sicherheitsabfrage
# ---------------------------------------------------------------------------

if [[ -n "${BACKUP_MODUS:-}" ]]; then
  MODUS="$BACKUP_MODUS"
elif command -v docker >/dev/null 2>&1 && docker compose ps --status running 2>/dev/null | grep -q ' db '; then
  MODUS=docker
else
  MODUS=lokal
fi

cat <<WARNUNG

  ============================================================
   Dieser Vorgang ERSETZT den gesamten Inhalt von:
     Datenbank : $POSTGRES_DB  (Betriebsart: $MODUS)
     Uploads   : alle vorhandenen Dateien
   Alle Daten, die nach dem Backup entstanden sind, gehen verloren.
  ============================================================

WARNUNG
read -r -p "Zum Fortfahren 'WIEDERHERSTELLEN' eingeben: " bestaetigung
[[ "$bestaetigung" == "WIEDERHERSTELLEN" ]] || { echo "Abgebrochen."; exit 1; }

# ---------------------------------------------------------------------------
# 3. App anhalten, damit nicht parallel geschrieben wird
# ---------------------------------------------------------------------------

if [[ "$MODUS" == "docker" ]]; then
  log "Halte App an …"
  docker compose stop app >/dev/null 2>&1 || true
else
  log "Halte Dienst an …"
  systemctl stop scandypro scandypro-https 2>/dev/null || true
fi

wieder_starten() {
  if [[ "$MODUS" == "docker" ]]; then
    docker compose start app >/dev/null 2>&1 || true
  else
    systemctl start scandypro 2>/dev/null || true
    systemctl start scandypro-https 2>/dev/null || true
  fi
}
trap 'rm -rf "$ARBEIT"; wieder_starten' EXIT

# ---------------------------------------------------------------------------
# 4. Datenbank zurückspielen
# ---------------------------------------------------------------------------

log "Spiele Datenbank zurück …"
if [[ "$MODUS" == "docker" ]]; then
  docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --clean --if-exists --no-owner --no-privileges < "$ARBEIT/datenbank.dump"
else
  PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_restore \
    -h "${POSTGRES_HOST:-localhost}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --clean --if-exists --no-owner --no-privileges < "$ARBEIT/datenbank.dump"
fi
log "  Datenbank wiederhergestellt."

# ---------------------------------------------------------------------------
# 5. Uploads zurückspielen
# ---------------------------------------------------------------------------

if [[ -f "$ARBEIT/uploads.tar.gz" ]]; then
  log "Spiele Uploads zurück …"
  if [[ "$MODUS" == "docker" ]]; then
    PROJEKT_NAME="$(docker compose config --format json 2>/dev/null | sed -n 's/.*"name": *"\([^"]*\)".*/\1/p' | head -1)"
    PROJEKT_NAME="${PROJEKT_NAME:-$(basename "$PROJEKT_VERZEICHNIS")}"
    docker run --rm \
      -v "${PROJEKT_NAME}_scandypro_uploads:/uploads" \
      -v "$ARBEIT:/sicherung:ro" \
      alpine:3 sh -c 'rm -rf /uploads/* && tar -xzf /sicherung/uploads.tar.gz -C /uploads'
  else
    UPLOAD_PFAD="${UPLOAD_DIR:-$PROJEKT_VERZEICHNIS/uploads}"
    mkdir -p "$UPLOAD_PFAD"
    rm -rf "${UPLOAD_PFAD:?}"/*
    tar -xzf "$ARBEIT/uploads.tar.gz" -C "$UPLOAD_PFAD"
  fi
  log "  Uploads wiederhergestellt."
else
  log "Keine Uploads im Archiv - überspringe."
fi

# ---------------------------------------------------------------------------
# 6. Migrationen nachziehen (falls der Code neuer ist als das Backup)
# ---------------------------------------------------------------------------

log "Starte App (führt 'alembic upgrade head' aus) …"
wieder_starten
trap 'rm -rf "$ARBEIT"' EXIT

cat <<HINWEIS

  Wiederherstellung abgeschlossen.

  Bitte jetzt prüfen:
    - Login funktioniert
    - Ein Bewerbungs-Dokument lässt sich herunterladen und öffnen
      (belegt, dass FIELD_ENCRYPTION_KEY zum Backup passt)
    - Ein Tagebuch-Eintrag ist im Klartext lesbar

  Wichtig: Der FIELD_ENCRYPTION_KEY in der .env muss derselbe sein wie zum
  Zeitpunkt des Backups. Mit einem anderen Schlüssel startet die App zwar,
  aber alle verschlüsselten Felder und Dateien bleiben unlesbar.

HINWEIS
