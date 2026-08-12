#!/usr/bin/env bash
#
# ScandyPro - Backup von Datenbank und Uploads (siehe tasks/produktivreife,
# PR-001). Erzeugt EIN verschlüsseltes Archiv pro Lauf und räumt alte
# Stände nach einem Generationen-Schema auf.
#
# Warum verschlüsselt: der pg_dump enthält zwar die Art.-9-Felder in ihrer
# Fernet-verschlüsselten Form, daneben aber Klartext-Stammdaten (Namen,
# E-Mail-Adressen, Rollen, Zuordnungen) und die Passwort-Hashes. Ein
# unverschlüsselter Dump auf einem Netzlaufwerk wäre damit selbst der
# Datenschutzvorfall, den das Backup verhindern soll.
#
# Aufruf:
#   ./scripts/backup.sh                  # nutzt .env im Projektverzeichnis
#   BACKUP_DIR=/mnt/nas/scandypro ./scripts/backup.sh
#
# Wiederherstellung: siehe ./scripts/restore.sh und docs/BACKUP.md.

set -euo pipefail

PROJEKT_VERZEICHNIS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJEKT_VERZEICHNIS"

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

ENV_DATEI="${ENV_DATEI:-$PROJEKT_VERZEICHNIS/.env}"
if [[ -f "$ENV_DATEI" ]]; then
  # shellcheck disable=SC1090
  set -a && . "$ENV_DATEI" && set +a
fi

BACKUP_DIR="${BACKUP_DIR:-$PROJEKT_VERZEICHNIS/backups}"
BEHALTE_TAEGLICH="${BEHALTE_TAEGLICH:-7}"
BEHALTE_WOECHENTLICH="${BEHALTE_WOECHENTLICH:-4}"
BEHALTE_MONATLICH="${BEHALTE_MONATLICH:-6}"

POSTGRES_USER="${POSTGRES_USER:-scandypro}"
POSTGRES_DB="${POSTGRES_DB:-scandypro}"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
fehler() { printf '%s  FEHLER: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Verschlüsselung: ohne Passphrase wird bewusst abgebrochen statt still
# unverschlüsselt zu schreiben. Wer die Verschlüsselung auf Speicherebene
# löst (z.B. LUKS, verschlüsseltes NAS-Share), setzt BACKUP_UNVERSCHLUESSELT=ja.
# ---------------------------------------------------------------------------

if [[ -z "${BACKUP_PASSPHRASE:-}" ]]; then
  if [[ "${BACKUP_UNVERSCHLUESSELT:-nein}" == "ja" ]]; then
    log "WARNUNG: BACKUP_UNVERSCHLUESSELT=ja - Archiv wird NICHT verschlüsselt."
    log "         Nur vertretbar, wenn das Ziel selbst verschlüsselt ist."
    VERSCHLUESSELN=nein
  else
    fehler "BACKUP_PASSPHRASE ist nicht gesetzt.
  Der Dump enthält personenbezogene Daten (Namen, E-Mail-Adressen,
  Passwort-Hashes) und darf nicht unverschlüsselt abgelegt werden.
  Passphrase erzeugen und in die .env eintragen:
      echo \"BACKUP_PASSPHRASE=\$(openssl rand -base64 48)\" >> .env
  Diese Passphrase getrennt vom Backup aufbewahren - ohne sie ist das
  Archiv nicht wiederherstellbar."
  fi
else
  VERSCHLUESSELN=ja
  command -v openssl >/dev/null || fehler "openssl wird für die Verschlüsselung benötigt."
fi

# ---------------------------------------------------------------------------
# Betriebsart erkennen: Docker Compose oder direkte Installation (Proxmox-LXC,
# siehe proxmox/install/scandypro-install.sh - dort läuft PostgreSQL lokal
# und die Uploads liegen im Projektverzeichnis).
# ---------------------------------------------------------------------------

if [[ -n "${BACKUP_MODUS:-}" ]]; then
  MODUS="$BACKUP_MODUS"
elif command -v docker >/dev/null 2>&1 && docker compose ps --status running 2>/dev/null | grep -q ' db '; then
  MODUS=docker
elif command -v pg_dump >/dev/null 2>&1; then
  MODUS=lokal
else
  fehler "Weder ein laufender Docker-'db'-Dienst noch ein lokales pg_dump gefunden.
  Betriebsart notfalls explizit vorgeben: BACKUP_MODUS=docker|lokal"
fi
log "Betriebsart: $MODUS"

# ---------------------------------------------------------------------------
# Arbeitsverzeichnis
# ---------------------------------------------------------------------------

ZEITSTEMPEL="$(date '+%Y-%m-%dT%H-%M-%S')"
ARBEIT="$(mktemp -d)"
trap 'rm -rf "$ARBEIT"' EXIT

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# ---------------------------------------------------------------------------
# 1. Datenbank
# ---------------------------------------------------------------------------

log "Sichere Datenbank '$POSTGRES_DB' …"
if [[ "$MODUS" == "docker" ]]; then
  docker compose exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --format=custom --no-owner --no-privileges > "$ARBEIT/datenbank.dump"
else
  PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_dump \
    -h "${POSTGRES_HOST:-localhost}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    --format=custom --no-owner --no-privileges > "$ARBEIT/datenbank.dump"
fi

DUMP_GROESSE="$(wc -c < "$ARBEIT/datenbank.dump" | tr -d ' ')"
[[ "$DUMP_GROESSE" -gt 1024 ]] || fehler "Dump ist nur ${DUMP_GROESSE} Bytes groß - das kann nicht stimmen."
log "  Dump: $((DUMP_GROESSE / 1024)) KiB"

# ---------------------------------------------------------------------------
# 2. Uploads (verschlüsselte Bewerbungsunterlagen, siehe app/core/uploads.py)
# ---------------------------------------------------------------------------

log "Sichere Uploads …"
if [[ "$MODUS" == "docker" ]]; then
  # Über einen Wegwerf-Container, damit der Volume-Name nicht geraten werden
  # muss und das Backup auch bei gestoppter App funktioniert.
  UPLOAD_VOLUME="$(docker compose config --volumes | grep -x 'scandypro_uploads' || true)"
  if [[ -n "$UPLOAD_VOLUME" ]]; then
    PROJEKT_NAME="$(docker compose config --format json 2>/dev/null | sed -n 's/.*"name": *"\([^"]*\)".*/\1/p' | head -1)"
    PROJEKT_NAME="${PROJEKT_NAME:-$(basename "$PROJEKT_VERZEICHNIS")}"
    docker run --rm \
      -v "${PROJEKT_NAME}_${UPLOAD_VOLUME}:/uploads:ro" \
      -v "$ARBEIT:/sicherung" \
      alpine:3 tar -czf /sicherung/uploads.tar.gz -C /uploads . 2>/dev/null \
      || fehler "Uploads-Volume ${PROJEKT_NAME}_${UPLOAD_VOLUME} konnte nicht gelesen werden."
  fi
else
  UPLOAD_PFAD="${UPLOAD_DIR:-$PROJEKT_VERZEICHNIS/uploads}"
  if [[ -d "$UPLOAD_PFAD" ]]; then
    tar -czf "$ARBEIT/uploads.tar.gz" -C "$UPLOAD_PFAD" .
  fi
fi

if [[ -f "$ARBEIT/uploads.tar.gz" ]]; then
  log "  Uploads: $(( $(wc -c < "$ARBEIT/uploads.tar.gz") / 1024 )) KiB"
else
  log "  Keine Uploads gefunden - überspringe."
  : > "$ARBEIT/uploads-fehlen.hinweis"
fi

# ---------------------------------------------------------------------------
# 3. Metadaten - damit beim Restore erkennbar ist, was da eigentlich liegt
# ---------------------------------------------------------------------------

{
  echo "erstellt_am=$(date -Iseconds)"
  echo "betriebsart=$MODUS"
  echo "datenbank=$POSTGRES_DB"
  echo "migrationsdateien=$(find alembic/versions -name '*.py' 2>/dev/null | wc -l | tr -d ' ')"
  echo "quelle_host=$(hostname)"
} > "$ARBEIT/backup.info"

# ---------------------------------------------------------------------------
# 4. Zusammenpacken und verschlüsseln
# ---------------------------------------------------------------------------

ARCHIV="$BACKUP_DIR/scandypro-$ZEITSTEMPEL.tar.gz"
tar -czf "$ARCHIV" -C "$ARBEIT" .

if [[ "$VERSCHLUESSELN" == "ja" ]]; then
  openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
    -in "$ARCHIV" -out "$ARCHIV.enc" -pass env:BACKUP_PASSPHRASE
  rm -f "$ARCHIV"
  ARCHIV="$ARCHIV.enc"
fi

chmod 600 "$ARCHIV"
log "Archiv: $ARCHIV ($(( $(wc -c < "$ARCHIV") / 1024 )) KiB)"

# ---------------------------------------------------------------------------
# 5. Rotation - taeglich/woechentlich/monatlich getrennt zaehlen, damit ein
#    stiller Ausfall nicht innerhalb weniger Tage alle Generationen wegrotiert.
# ---------------------------------------------------------------------------

rotiere() {
  local muster="$1" behalten="$2" bezeichnung="$3"
  # Bewusst ohne mapfile/readarray: die gibt es erst ab Bash 4, und auf
  # macOS ist /bin/bash noch 3.2 - das Skript soll auch dort laufen, wo
  # entwickelt wird, nicht nur auf dem Debian-Zielsystem.
  local dateien=()
  local datei
  # Globbing ist hier gewollt ($muster ist ein Dateimuster), Sortierung nach
  # Änderungszeit absteigend.
  # shellcheck disable=SC2012,SC2086
  while IFS= read -r datei; do
    [[ -n "$datei" ]] && dateien+=("$datei")
  done < <(ls -1t "$BACKUP_DIR"/$muster 2>/dev/null || true)

  local anzahl=${#dateien[@]}
  if (( anzahl > behalten )); then
    local i
    for (( i = behalten; i < anzahl; i++ )); do
      rm -f "${dateien[$i]}"
      log "  entfernt ($bezeichnung): $(basename "${dateien[$i]}")"
    done
  fi
}

# Monats- und Wochenstände markieren, bevor die Tagesstände rotieren.
#
# Bewusst über dirname/basename statt über eine Ersetzung im vollen Pfad:
# ${ARCHIV/scandypro-/...} würde bei einem BACKUP_DIR wie
# /mnt/nas/scandypro-backups den *Verzeichnisnamen* treffen und den Link in
# ein nicht existierendes Verzeichnis legen - stillschweigend, weil ln
# fehlschlägt und der Fehler unterdrückt wird. Es gäbe dann nie einen
# Monatsstand, ohne dass das jemandem auffällt.
markiere_generation() {
  local praefix="$1"
  local verzeichnis dateiname ziel
  verzeichnis="$(dirname "$ARCHIV")"
  dateiname="$(basename "$ARCHIV")"
  ziel="$verzeichnis/scandypro-$praefix-${dateiname#scandypro-}"

  # Erst Hardlink versuchen (kostet keinen zusätzlichen Speicher). Scheitert
  # das - etwa auf SMB/NFS-Zielen, die keine Hardlinks können, und genau
  # solche Netzlaufwerke empfehlen wir als Ablageort - wird kopiert. Lieber
  # doppelter Speicherverbrauch als eine fehlende Generation.
  if ln -f "$ARCHIV" "$ziel" 2>/dev/null; then
    log "  $praefix-Stand verlinkt: $(basename "$ziel")"
  elif cp "$ARCHIV" "$ziel"; then
    log "  $praefix-Stand kopiert (Hardlinks nicht möglich): $(basename "$ziel")"
  else
    log "  WARNUNG: $praefix-Stand konnte nicht angelegt werden ($ziel)"
  fi
}

TAG_IM_MONAT="$(date '+%d')"
WOCHENTAG="$(date '+%u')"
if [[ "$TAG_IM_MONAT" == "01" ]]; then
  markiere_generation "monatlich"
elif [[ "$WOCHENTAG" == "7" ]]; then
  markiere_generation "woechentlich"
fi

log "Rotation …"
rotiere 'scandypro-2*'             "$BEHALTE_TAEGLICH"      "täglich"
rotiere 'scandypro-woechentlich-*' "$BEHALTE_WOECHENTLICH"  "wöchentlich"
rotiere 'scandypro-monatlich-*'    "$BEHALTE_MONATLICH"     "monatlich"

log "Fertig."
log ""
log "Erinnerung: ein Backup, das nie zurückgespielt wurde, ist kein Backup."
log "Restore mindestens einmal proben - siehe docs/BACKUP.md."
