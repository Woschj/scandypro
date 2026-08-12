#!/usr/bin/env bash
# Prueft Rotation und Generationen-Markierung von scripts/backup.sh isoliert,
# ohne Datenbank - die Logik wird dazu aus dem Skript nachgebildet und gegen
# dieselben Muster gefahren.
set -euo pipefail

PROJEKT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FEHLER=0

pruefe() {
  local beschreibung="$1" erwartet="$2" tatsaechlich="$3"
  if [[ "$erwartet" == "$tatsaechlich" ]]; then
    echo "  OK    $beschreibung"
  else
    echo "  FALSCH $beschreibung"
    echo "         erwartet:     $erwartet"
    echo "         tatsaechlich: $tatsaechlich"
    FEHLER=$((FEHLER + 1))
  fi
}

# --- Die zu pruefenden Funktionen, wortgleich aus scripts/backup.sh ---------
log() { :; }

markiere_generation() {
  local praefix="$1"
  local verzeichnis dateiname ziel
  verzeichnis="$(dirname "$ARCHIV")"
  dateiname="$(basename "$ARCHIV")"
  ziel="$verzeichnis/scandypro-$praefix-${dateiname#scandypro-}"
  if ln -f "$ARCHIV" "$ziel" 2>/dev/null; then
    log "verlinkt"
  elif cp "$ARCHIV" "$ziel"; then
    log "kopiert"
  else
    log "WARNUNG"
  fi
  echo "$ziel"
}

rotiere() {
  local muster="$1" behalten="$2"
  local dateien=()
  local datei
  # shellcheck disable=SC2012,SC2086
  while IFS= read -r datei; do
    [[ -n "$datei" ]] && dateien+=("$datei")
  done < <(ls -1t "$BACKUP_DIR"/$muster 2>/dev/null || true)
  local anzahl=${#dateien[@]}
  if (( anzahl > behalten )); then
    local i
    for (( i = behalten; i < anzahl; i++ )); do rm -f "${dateien[$i]}"; done
  fi
}

# --- Fall 1: Zielpfad bei heiklen Verzeichnisnamen -------------------------
echo "1) Generationen-Pfad bei verschiedenen BACKUP_DIR-Namen"
for dir in /mnt/backup/scandypro /mnt/nas/scandypro-backups /srv/scandypro-daten; do
  ARCHIV="$dir/scandypro-2026-08-01T03-00-00.tar.gz.enc"
  verzeichnis="$(dirname "$ARCHIV")"
  dateiname="$(basename "$ARCHIV")"
  ziel="$verzeichnis/scandypro-monatlich-${dateiname#scandypro-}"
  pruefe "$dir" \
    "$dir/scandypro-monatlich-2026-08-01T03-00-00.tar.gz.enc" \
    "$ziel"
done

# --- Fall 2: Hardlink real, inkl. Rotation ---------------------------------
echo
echo "2) Hardlink ueberlebt Wegrotieren des Tagesstands"
BACKUP_DIR="$(mktemp -d)"
ARCHIV="$BACKUP_DIR/scandypro-2026-08-01T03-00-00.tar.gz.enc"
echo "NUTZDATEN" > "$ARCHIV"
ziel="$(markiere_generation monatlich)"
rm -f "$ARCHIV"
pruefe "Monatsstand existiert nach rm des Tagesstands" "NUTZDATEN" "$(cat "$ziel" 2>/dev/null || echo FEHLT)"

# --- Fall 3: Muster sind disjunkt ------------------------------------------
echo
echo "3) Tages-Rotation loescht keine Wochen-/Monatsstaende"
BACKUP_DIR="$(mktemp -d)"
for i in 1 2 3 4 5 6 7 8 9; do
  printf 'tag%s' "$i" > "$BACKUP_DIR/scandypro-2026-08-0${i}T03-00-00.tar.gz.enc"
  sleep 0.01
done
printf 'woche' > "$BACKUP_DIR/scandypro-woechentlich-2026-08-02T03-00-00.tar.gz.enc"
printf 'monat' > "$BACKUP_DIR/scandypro-monatlich-2026-08-01T03-00-00.tar.gz.enc"

rotiere 'scandypro-2*' 7
pruefe "7 Tagesstaende uebrig" "7" "$(ls -1 "$BACKUP_DIR"/scandypro-2* 2>/dev/null | wc -l | tr -d ' ')"
pruefe "Wochenstand unberuehrt" "1" "$(ls -1 "$BACKUP_DIR"/scandypro-woechentlich-* 2>/dev/null | wc -l | tr -d ' ')"
pruefe "Monatsstand unberuehrt" "1" "$(ls -1 "$BACKUP_DIR"/scandypro-monatlich-* 2>/dev/null | wc -l | tr -d ' ')"

# --- Fall 4: aeltester zuerst weg ------------------------------------------
echo
echo "4) Rotation entfernt die aeltesten, nicht die neuesten"
pruefe "juengster Stand noch da" "ja" "$([[ -f "$BACKUP_DIR/scandypro-2026-08-09T03-00-00.tar.gz.enc" ]] && echo ja || echo nein)"
pruefe "aeltester Stand entfernt" "ja" "$([[ ! -f "$BACKUP_DIR/scandypro-2026-08-01T03-00-00.tar.gz.enc" ]] && echo ja || echo nein)"

# --- Fall 5: Leeres Verzeichnis / weniger als behalten ---------------------
echo
echo "5) Robustheit"
BACKUP_DIR="$(mktemp -d)"
rotiere 'scandypro-2*' 7
pruefe "leeres Verzeichnis ohne Fehler" "0" "$?"
printf 'x' > "$BACKUP_DIR/scandypro-2026-08-01T03-00-00.tar.gz.enc"
rotiere 'scandypro-2*' 7
pruefe "einziger Stand bleibt" "1" "$(ls -1 "$BACKUP_DIR"/scandypro-2* 2>/dev/null | wc -l | tr -d ' ')"

echo
if (( FEHLER == 0 )); then echo "ALLE ROTATIONS-FAELLE KORREKT"; else echo "*** $FEHLER FEHLER ***"; exit 1; fi
