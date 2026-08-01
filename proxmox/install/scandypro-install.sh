#!/usr/bin/env bash

# ScandyPro - eigenes Installer-Skript im Projekt-Repo, geschrieben im Stil
# der community-scripts-Konvention (ct/*.sh + install/*-install.sh), nutzt
# deren geteilte Helper-Funktionen (setup_postgresql, setup_postgresql_db,
# msg_info/msg_ok, ...) aus misc/tools.func + misc/install.func. KEIN
# offizieller community-scripts-Eintrag - läuft nur gegen dieses Repo
# (https://github.com/Woschj/scandypro).
#
# 1:1 nach dem Vorbild von Scandy-Lite (proxmox/install/scandy-lite-install.sh)
# gebaut, mit zwei bewussten Abweichungen:
#   - nur EIN systemd-Dienst/Port (8000): ScandyPro hat kein Kamera-Scan-
#     Feature, das zwingend HTTPS bräuchte (Scandy-Lite braucht dafür einen
#     zweiten uvicorn-Prozess mit selbstsigniertem Zertifikat) - auch das
#     Docker-Compose-Setup von ScandyPro hat nur einen HTTP-Port.
#   - Admin-Bootstrap läuft NICHT über ein separates Skript, sondern
#     automatisch beim ersten App-Start (siehe app/main.py:lifespan,
#     app/core/seed.py:seed_admin) - einfach ADMIN_EMAIL/ADMIN_PASSWORD in
#     der .env setzen, kein zusätzlicher Aufruf nötig.
#
# Läuft innerhalb der frisch erstellten LXC (per `pct exec` aufgerufen von
# proxmox/ct/scandypro.sh). Lädt misc/install.func selbst nach - anders als
# bei einem offiziellen community-scripts-Eintrag steht FUNCTIONS_FILE_PATH
# hier NICHT schon vorbereitet zur Verfügung (das würde build_container()
# übernehmen, die wir bewusst nicht nutzen - siehe ct/scandypro.sh).
# misc/install.func lädt intern (über update_os) automatisch noch
# misc/tools.func nach, das ist derselbe Ablauf wie in jedem offiziellen
# install/*-install.sh.

# VERBOSE=yes schaltet den $STD-Wrapper der geteilten Bibliothek ab (der
# leitet apt/pip/etc. sonst standardmaessig still in eine Logdatei um, siehe
# misc/core.func::set_std_mode) - ohne die eigene build.func/das Advanced-
# Settings-Menu des offiziellen Frontends gibt es keinen anderen Weg, den
# Fortschritt live zu sehen. Muss VOR dem Sourcen von install.func gesetzt
# sein, das liest VERBOSE beim Laden einmalig aus.
export VERBOSE=yes

source <(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/misc/install.func)
color
verb_ip6
catch_errors
setting_up_container
network_check
update_os

msg_info "Installing Dependencies"
# sudo wird von setup_postgresql_db() intern gebraucht (sudo -u postgres
# psql ...) - im offiziellen community-scripts-Ablauf schon Teil des
# Basis-Pakets aus build_container(), das wir hier bewusst nicht nutzen
# (siehe ct/scandypro.sh). Die minimale Debian-Vorlage bringt es nicht mit.
$STD apt-get install -y sudo git openssl python3 python3-venv python3-pip
msg_ok "Installed Dependencies"

PG_VERSION="16" setup_postgresql
PG_DB_NAME="scandypro" PG_DB_USER="scandypro" setup_postgresql_db

msg_info "Cloning ScandyPro"
git clone -q --branch main https://github.com/Woschj/scandypro.git /opt/scandypro
msg_ok "Cloned ScandyPro"

msg_info "Setting up Python environment (kann etwas dauern)"
cd /opt/scandypro
python3 -m venv venv
$STD venv/bin/pip install --upgrade pip
# --prefer-binary: alle Pakete liefern fertige Wheels für linux/amd64+arm64,
# verhindert einen versehentlichen Kompilier-Versuch (langsam, bräuchte
# zusätzlich build-essential) bei einer neueren, nur-als-Source verfügbaren
# Version.
$STD venv/bin/pip install --prefer-binary -r requirements.txt
mkdir -p uploads
msg_ok "Setup Python environment"

msg_info "Configuring ScandyPro"
SECRET_KEY="$(openssl rand -hex 32)"
ADMIN_PASSWORD="$(openssl rand -hex 8)"
# Fernet-Key = 32 zufällige Bytes, URL-safe Base64-kodiert (identisch zu
# cryptography.fernet.Fernet.generate_key()) - siehe app/core/crypto.py.
FIELD_ENCRYPTION_KEY="$(openssl rand -base64 32 | tr '+/' '-_')"
cat <<EOF >/opt/scandypro/.env
POSTGRES_USER=${PG_DB_USER}
POSTGRES_PASSWORD=${PG_DB_PASS}
POSTGRES_DB=${PG_DB_NAME}
DATABASE_URL=postgresql+asyncpg://${PG_DB_USER}:${PG_DB_PASS}@localhost:5432/${PG_DB_NAME}
SECRET_KEY=$SECRET_KEY
FIELD_ENCRYPTION_KEY=$FIELD_ENCRYPTION_KEY
SEED_DEMO_DATA=false
ADMIN_EMAIL=admin@scandypro.local
ADMIN_PASSWORD=$ADMIN_PASSWORD
EOF
set -a
. /opt/scandypro/.env
set +a
msg_ok "Configured ScandyPro"

msg_info "Applying database migrations"
$STD /opt/scandypro/venv/bin/alembic upgrade head
msg_ok "Applied database migrations"

# Admin-Account entsteht automatisch beim ersten Start der App (lifespan in
# app/main.py liest ADMIN_EMAIL/ADMIN_PASSWORD aus der Umgebung, siehe
# app/core/seed.py:seed_admin) - kein separater Aufruf hier nötig.

cat <<EOF >/root/scandypro.creds
ScandyPro Admin-Zugangsdaten
=============================
URL: http://<container-ip>:8000

E-Mail:   admin@scandypro.local
Passwort: $ADMIN_PASSWORD

Passwort danach über die Benutzerverwaltung ändern und ADMIN_PASSWORD aus
/opt/scandypro/.env entfernen (liegt aktuell im Klartext, wird nach dem
ersten Start nicht erneut gebraucht - das Admin-Konto existiert dann schon).
Diese Datei danach löschen (rm /root/scandypro.creds).
EOF
chmod 600 /root/scandypro.creds

msg_info "Creating Service"
cat <<EOF >/etc/systemd/system/scandypro.service
[Unit]
Description=ScandyPro
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
WorkingDirectory=/opt/scandypro
EnvironmentFile=/opt/scandypro/.env
ExecStart=/opt/scandypro/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl enable -q --now scandypro
msg_ok "Created Service"

motd_ssh
customize
cleanup_lxc
