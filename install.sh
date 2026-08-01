#!/bin/sh
# ScandyPro Erstinstallation (Linux/Mac) - analog zum install.sh von
# Scandy-Lite, damit beide Tools im Parallelbetrieb auf demselben Host
# dieselbe Bedienung haben.
#
# Macht aus einem frischen "git clone" eine laufende Instanz:
#   1. Prüft Docker/Docker Compose
#   2. Erzeugt .env mit zufälligen Secrets, falls noch keine existiert
#      (idempotent - ein erneuter Lauf verändert eine bestehende .env NICHT)
#   3. Baut und startet den Stack
#   4. Wartet, bis die App tatsächlich antwortet
#   5. Zeigt Zugangs-URL an (+ Admin-Zugangsdaten, falls gerade neu erzeugt)
#
# Nutzung:
#   ./install.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== ScandyPro Installation ==="
echo ""

# --- 1. Voraussetzungen ---------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "FEHLER: Docker wurde nicht gefunden. Installation: https://docs.docker.com/get-docker/" >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "FEHLER: 'docker compose' (Compose V2) ist nicht verfügbar." >&2
  echo "        Ältere docker-compose-Standalone-Installationen reichen nicht - Docker Desktop/Engine aktualisieren." >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "FEHLER: openssl wird zum Erzeugen der Zugangsdaten gebraucht, ist aber nicht installiert." >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "FEHLER: curl wird für die Start-Überprüfung gebraucht, ist aber nicht installiert." >&2
  exit 1
fi

# --- 2. .env erzeugen (nur falls noch keine existiert) --------------------
NEUE_ENV=0
if [ -f .env ]; then
  echo ".env existiert bereits - wird unverändert weiterverwendet."
else
  NEUE_ENV=1
  echo "Erzeuge .env mit zufällig generierten Zugangsdaten..."
  SECRET_KEY="$(openssl rand -hex 32)"
  POSTGRES_PASSWORD="$(openssl rand -hex 24)"
  ADMIN_PASSWORD="$(openssl rand -hex 8)"
  # Fernet-Key = 32 zufällige Bytes, URL-safe Base64-kodiert (identisch zu
  # cryptography.fernet.Fernet.generate_key()) - bewusst ohne Python-
  # Abhängigkeit auf dem Host erzeugt, nur mit openssl/tr.
  FIELD_ENCRYPTION_KEY="$(openssl rand -base64 32 | tr '+/' '-_')"

  cat > .env <<ENVEOF
# Automatisch von install.sh generiert am $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Zufällige, sichere Werte - siehe README.md für die Bedeutung der einzelnen
# Variablen. ADMIN_PASSWORD nach dem ersten erfolgreichen Login idealerweise
# aus dieser Datei entfernen (liegt aktuell im Klartext).
POSTGRES_USER=scandypro
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=scandypro
DATABASE_URL=postgresql+asyncpg://scandypro:$POSTGRES_PASSWORD@db:5432/scandypro
SECRET_KEY=$SECRET_KEY
FIELD_ENCRYPTION_KEY=$FIELD_ENCRYPTION_KEY
SEED_DEMO_DATA=false
ADMIN_EMAIL=admin@scandypro.local
ADMIN_PASSWORD=$ADMIN_PASSWORD
APP_PORT=8080
ENVEOF
  echo ".env erzeugt."
fi

# .env für die Werte unten einlesen (funktioniert unabhängig davon, ob sie
# gerade neu erzeugt oder schon vorhanden war)
# shellcheck disable=SC1091
set -a
. ./.env
set +a

# --- 3. Bauen und starten --------------------------------------------------
echo ""
echo "Baue und starte Container (kann beim allerersten Mal 1-2 Minuten dauern)..."
docker compose up -d --build

# --- 4. Auf tatsächlich antwortende App warten -----------------------------
echo ""
echo "Warte auf App-Start..."
ATTEMPTS=0
MAX_ATTEMPTS=60
until curl -sf "http://localhost:${APP_PORT:-8080}/login" >/dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]; then
    echo "" >&2
    echo "App antwortet nach 2 Minuten immer noch nicht. Logs prüfen mit:" >&2
    echo "  docker compose logs app" >&2
    exit 1
  fi
  sleep 2
done

# --- 5. Zusammenfassung -----------------------------------------------------
echo ""
echo "=== Fertig! ==="
echo ""
echo "App erreichbar unter:  http://localhost:${APP_PORT:-8080}"
if [ "$NEUE_ENV" -eq 1 ]; then
  echo "Login:                 ${ADMIN_EMAIL:-admin@scandypro.local} / ${ADMIN_PASSWORD}"
  echo ""
  echo "Passwort danach über \"Mein Konto\" (/konto) ändern und ADMIN_PASSWORD aus"
  echo ".env entfernen (liegt aktuell im Klartext, wird beim nächsten Start nicht"
  echo "erneut gebraucht - das Admin-Konto existiert dann schon)."
else
  echo "Login mit den Zugangsdaten aus der bestehenden .env (ADMIN_EMAIL/ADMIN_PASSWORD)."
fi
