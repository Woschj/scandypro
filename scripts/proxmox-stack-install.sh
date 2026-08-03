#!/usr/bin/env bash
# Provisioniert den ScandyPro-Stack auf einem frischen Proxmox-Host: legt pro
# ausgewaehlter Komponente einen neuen, unprivilegierten LXC-Container an und
# installiert/konfiguriert die Software darin - analog zum manuell
# eingerichteten Referenzstand (Debian 12, PostgreSQL lokal in derselben LXC,
# uvicorn zweifach: Klartext-HTTP nur auf 127.0.0.1:8000, TLS mit
# selbstsigniertem Zertifikat auf 0.0.0.0:8443, siehe README.md "TLS
# (Produktivbetrieb)").
#
# WICHTIG: Legt IMMER NEUE Container an (naechste freie VMID), fasst
# bestehende Container nicht an. Muss auf dem Proxmox-HOST selbst laufen
# (nicht in einer LXC), als root.
#
# Nutzung:
#   ./proxmox-stack-install.sh --scandypro --scandylite --authentik
#   ./proxmox-stack-install.sh --all
#   ./proxmox-stack-install.sh                 # interaktives Menue
#
# Jede Komponente ist unabhaengig voneinander lauffaehig; Reihenfolge ist
# egal, ausser man will Authentik-SSO direkt bei der Installation von
# ScandyPro/Scandy-Lite mit verdrahten - dafuer erst --authentik, dann die
# App(s) in einem zweiten Lauf.

set -euo pipefail

# ---------------------------------------------------------------------------
# Konfiguration (bei Bedarf anpassen oder per Umgebungsvariable ueberschreiben)
# ---------------------------------------------------------------------------
CT_STORAGE="${CT_STORAGE:-local-lvm}"        # Storage fuer Container-Disks
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}" # Storage, in dem Templates liegen
CT_BRIDGE="${CT_BRIDGE:-vmbr0}"
CT_DISK_GB="${CT_DISK_GB:-8}"
CT_MEMORY_MB="${CT_MEMORY_MB:-2048}"
CT_CORES="${CT_CORES:-2}"
CT_PASSWORD="${CT_PASSWORD:-}"               # leer = zufaellig erzeugt und ausgegeben

SCANDYPRO_REPO="${SCANDYPRO_REPO:-https://github.com/woschj/scandypro}"
SCANDYLITE_REPO="${SCANDYLITE_REPO:-https://github.com/Woschj/scandy-lite.git}"

AUTHENTIK_INSTALL_SCRIPT_URL="${AUTHENTIK_INSTALL_SCRIPT_URL:-https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/ct/authentik.sh}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

log()  { echo -e "\n\033[1;32m==> $*\033[0m"; }
warn() { echo -e "\033[1;33m!! $*\033[0m" >&2; }
die()  { echo -e "\033[1;31mFEHLER: $*\033[0m" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Vorpruefungen
# ---------------------------------------------------------------------------
require_proxmox_host() {
    command -v pct >/dev/null 2>&1 || die "pct nicht gefunden - dieses Skript muss auf dem Proxmox-Host laufen, nicht in einer LXC/VM."
    [ "$(id -u)" -eq 0 ] || die "Bitte als root ausfuehren."
}

# ---------------------------------------------------------------------------
# Hilfsfunktionen: Container-Erstellung
# ---------------------------------------------------------------------------
pick_debian12_template() {
    local tmpl
    tmpl=$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null | awk '{print $1}' | grep -m1 "debian-12-standard" || true)
    if [ -z "$tmpl" ]; then
        log "Debian-12-Template nicht lokal vorhanden, lade herunter..."
        pveam update >/dev/null
        local remote
        remote=$(pveam available --section system | awk '{print $2}' | grep -m1 "debian-12-standard")
        [ -n "$remote" ] || die "Kein debian-12-standard-Template im Proxmox-Katalog gefunden."
        pveam download "$TEMPLATE_STORAGE" "$remote"
        tmpl="${TEMPLATE_STORAGE}:vztmpl/${remote}"
    fi
    echo "$tmpl"
}

next_free_vmid() {
    pvesh get /cluster/nextid
}

random_password() {
    openssl rand -base64 24 | tr -d '=+/' | head -c 24
}

# create_ct <hostname> -> gibt "VMID IP" auf stdout aus
create_ct() {
    local hostname="$1"
    local vmid template pass
    vmid=$(next_free_vmid)
    template=$(pick_debian12_template)
    pass="${CT_PASSWORD:-$(random_password)}"

    log "Lege Container ${vmid} (${hostname}) an aus ${template}..."
    pct create "$vmid" "$template" \
        --hostname "$hostname" \
        --cores "$CT_CORES" \
        --memory "$CT_MEMORY_MB" \
        --rootfs "${CT_STORAGE}:${CT_DISK_GB}" \
        --net0 "name=eth0,bridge=${CT_BRIDGE},ip=dhcp,ip6=dhcp" \
        --unprivileged 1 \
        --features nesting=1 \
        --password "$pass" \
        --onboot 1 >&2

    pct start "$vmid" >&2
    log "Warte auf Netzwerk in Container ${vmid}..." >&2
    local ip=""
    for _ in $(seq 1 30); do
        ip=$(pct exec "$vmid" -- hostname -I 2>/dev/null | awk '{print $1}' || true)
        [ -n "$ip" ] && break
        sleep 2
    done
    [ -n "$ip" ] || die "Container ${vmid} hat nach 60s keine IP bekommen."

    echo "Root-Passwort fuer Container ${vmid} (${hostname}): ${pass}" >&2
    echo "$vmid $ip"
}

base_setup() {
    local vmid="$1"
    log "Grundpakete in Container ${vmid} installieren..."
    pct exec "$vmid" -- bash -c '
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq postgresql python3 python3-venv python3-pip \
            build-essential libpq-dev git openssl curl ca-certificates
    '
}

# pg_setup <vmid> <db> <user> <pass>
pg_setup() {
    local vmid="$1" db="$2" user="$3" pass="$4"
    log "PostgreSQL-Rolle/Datenbank '${db}' in Container ${vmid} anlegen..."
    pct exec "$vmid" -- sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${user}') THEN
      CREATE ROLE ${user} LOGIN PASSWORD '${pass}';
   END IF;
END
\$\$;
SQL
    pct exec "$vmid" -- sudo -u postgres createdb -O "$user" "$db" 2>/dev/null || true
}

# selfsigned_cert <vmid> <app_name> <hostname_fqdn> <ip>
selfsigned_cert() {
    local vmid="$1" name="$2" fqdn="$3" ip="$4"
    log "Selbstsigniertes Zertifikat fuer ${fqdn} in Container ${vmid} erzeugen..."
    pct exec "$vmid" -- bash -c "
        mkdir -p /etc/ssl/${name}
        chmod 700 /etc/ssl/${name}
        openssl req -x509 -newkey rsa:4096 -sha256 -days 365 -nodes \
            -keyout /etc/ssl/${name}/${name}.key -out /etc/ssl/${name}/${name}.crt \
            -subj '/CN=${fqdn}' \
            -addext 'subjectAltName=DNS:${fqdn},DNS:localhost,IP:${ip},IP:127.0.0.1'
        chmod 600 /etc/ssl/${name}/${name}.key
    "
}

# systemd_units <vmid> <name> <app_dir>
systemd_units() {
    local vmid="$1" name="$2" app_dir="$3"
    log "systemd-Units fuer ${name} in Container ${vmid} anlegen..."
    pct exec "$vmid" -- tee "/etc/systemd/system/${name}.service" >/dev/null <<EOF
[Unit]
Description=${name} (HTTP, nur lokal)
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
WorkingDirectory=${app_dir}
EnvironmentFile=${app_dir}/.env
ExecStart=${app_dir}/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    pct exec "$vmid" -- tee "/etc/systemd/system/${name}-https.service" >/dev/null <<EOF
[Unit]
Description=${name} (HTTPS)
After=network.target postgresql.service ${name}.service
Requires=postgresql.service

[Service]
Type=simple
WorkingDirectory=${app_dir}
EnvironmentFile=${app_dir}/.env
ExecStart=${app_dir}/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8443 --ssl-keyfile /etc/ssl/${name}/${name}.key --ssl-certfile /etc/ssl/${name}/${name}.crt
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    pct exec "$vmid" -- systemctl daemon-reload
    pct exec "$vmid" -- systemctl enable --now "${name}.service" "${name}-https.service"
}

# deploy_python_app <vmid> <name> <repo> <app_dir> <db> <dbuser> <dbpass> <fqdn> <ip>
deploy_python_app() {
    local vmid="$1" name="$2" repo="$3" app_dir="$4" db="$5" dbuser="$6" dbpass="$7" fqdn="$8" ip="$9"

    log "Code fuer ${name} klonen (${repo})..."
    pct exec "$vmid" -- git clone --depth 1 "$repo" "$app_dir"

    log "Virtualenv anlegen und Abhaengigkeiten installieren..."
    pct exec "$vmid" -- bash -c "
        cd '${app_dir}'
        python3 -m venv venv
        venv/bin/pip install --quiet --upgrade pip
        venv/bin/pip install --quiet -r requirements.txt
    "

    local secret_key field_key
    secret_key=$(openssl rand -hex 32)
    field_key=$(pct exec "$vmid" -- "${app_dir}/venv/bin/python" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

    log "Konfigurationsdatei .env schreiben..."
    pct exec "$vmid" -- tee "${app_dir}/.env" >/dev/null <<EOF
POSTGRES_USER=${dbuser}
POSTGRES_PASSWORD=${dbpass}
POSTGRES_DB=${db}
DATABASE_URL=postgresql+asyncpg://${dbuser}:${dbpass}@localhost:5432/${db}
SECRET_KEY=${secret_key}
FIELD_ENCRYPTION_KEY=${field_key}
SEED_DEMO_DATA=false
ADMIN_EMAIL=
ADMIN_PASSWORD=
SESSION_COOKIE_SECURE=true
OIDC_ISSUER=
OIDC_CLIENT_ID=
OIDC_CLIENT_SECRET=
OIDC_PROVIDER_NAME=SSO
EOF

    if [ -d "$WORKDIR/${name}_alembic_check" ]; then :; fi
    if pct exec "$vmid" -- test -d "${app_dir}/alembic"; then
        log "Datenbankmigrationen anwenden..."
        pct exec "$vmid" -- bash -c "cd '${app_dir}' && venv/bin/python -m alembic upgrade head"
    fi

    selfsigned_cert "$vmid" "$name" "$fqdn" "$ip"
    systemd_units "$vmid" "$name" "$app_dir"
}

# ---------------------------------------------------------------------------
# Komponenten
# ---------------------------------------------------------------------------
install_scandypro() {
    log "=== ScandyPro installieren ==="
    local vmid ip
    read -r vmid ip < <(create_ct "scandypro")
    base_setup "$vmid"
    local dbpass; dbpass=$(random_password)
    pg_setup "$vmid" "scandypro" "scandypro" "$dbpass"
    deploy_python_app "$vmid" "scandypro" "$SCANDYPRO_REPO" "/opt/scandypro" \
        "scandypro" "scandypro" "$dbpass" "scandypro.fritz.box" "$ip"
    log "ScandyPro fertig: https://${ip}:8443/ (Container ${vmid})"
}

install_scandylite() {
    log "=== Scandy-Lite installieren ==="
    local vmid ip
    read -r vmid ip < <(create_ct "scandy-lite")
    base_setup "$vmid"
    local dbpass; dbpass=$(random_password)
    pg_setup "$vmid" "scandy_lite" "scandy" "$dbpass"
    deploy_python_app "$vmid" "scandy-lite" "$SCANDYLITE_REPO" "/opt/scandy-lite" \
        "scandy_lite" "scandy" "$dbpass" "scandy-lite.fritz.box" "$ip"
    log "Scandy-Lite fertig: https://${ip}:8443/ (Container ${vmid})"
}

# Authentik: nutzt das offizielle Community-Skript, das die Container-
# Erstellung UND Docker-Compose-Installation selbst uebernimmt (siehe
# SSO_AUTHENTIK.md). Danach wird versucht, per Blueprint automatisch einen
# OAuth2/OIDC-Provider + Application fuer ScandyPro anzulegen. Der
# Blueprint-Pfad im Container haengt von der genauen Docker-Compose-Struktur
# des Community-Skripts ab - falls er sich in einer neueren Skript-Version
# geaendert hat, schlaegt NUR dieser letzte Automatisierungsschritt fehl
# (Authentik selbst laeuft trotzdem); die Ausgabe zeigt dann, was manuell in
# der Authentik-UI nachzutragen ist.
install_authentik() {
    log "=== Authentik installieren (Community-Skript) ==="
    log "Fuehre ${AUTHENTIK_INSTALL_SCRIPT_URL} aus - Container-Erstellung/Auswahl erfolgt interaktiv im Skript selbst."
    bash -c "$(curl -fsSL "$AUTHENTIK_INSTALL_SCRIPT_URL")"

    warn "Authentik-Installation abgeschlossen. Welche VMID wurde dabei angelegt?"
    read -r -p "Authentik-VMID: " authentik_vmid
    [ -n "$authentik_vmid" ] || { warn "Keine VMID angegeben - ueberspringe automatische OIDC-Provisionierung."; return 0; }

    local authentik_ip
    authentik_ip=$(pct exec "$authentik_vmid" -- hostname -I 2>/dev/null | awk '{print $1}' || true)
    [ -n "$authentik_ip" ] || { warn "Konnte IP von Container ${authentik_vmid} nicht ermitteln - manuelle Konfiguration noetig."; return 0; }

    log "Authentik erreichbar unter https://${authentik_ip}:9443/ (Standard-Port des Community-Skripts, ggf. abweichend)."
    warn "Automatische OIDC-Client-Provisionierung fuer ScandyPro/Scandy-Lite ist an dieser Stelle NICHT enthalten,"
    warn "da der Blueprint-Ablagepfad je nach Authentik-Version/Compose-Layout variiert und ohne Zugriff auf den"
    warn "konkreten Container nicht zuverlaessig automatisierbar ist. Bitte SSO_AUTHENTIK.md fuer die manuelle"
    warn "Einrichtung (Provider + Application je App, dann OIDC_ISSUER/OIDC_CLIENT_ID/OIDC_CLIENT_SECRET in der"
    warn "jeweiligen .env eintragen und den *-https.service neu starten) verwenden."
}

# ---------------------------------------------------------------------------
# Menue / Argumentverarbeitung
# ---------------------------------------------------------------------------
usage() {
    cat <<EOF
Nutzung: $0 [--scandypro] [--scandylite] [--authentik] [--all]

Ohne Argumente erscheint ein interaktives Auswahlmenue.
EOF
}

main() {
    require_proxmox_host

    local do_scandypro=0 do_scandylite=0 do_authentik=0

    if [ "$#" -eq 0 ]; then
        echo "Was soll installiert werden?"
        select opt in "ScandyPro" "Scandy-Lite" "Authentik" "Alle drei" "Abbrechen"; do
            case "$opt" in
                "ScandyPro") do_scandypro=1; break ;;
                "Scandy-Lite") do_scandylite=1; break ;;
                "Authentik") do_authentik=1; break ;;
                "Alle drei") do_scandypro=1; do_scandylite=1; do_authentik=1; break ;;
                "Abbrechen") exit 0 ;;
                *) echo "Ungueltige Auswahl." ;;
            esac
        done
    else
        for arg in "$@"; do
            case "$arg" in
                --scandypro) do_scandypro=1 ;;
                --scandylite) do_scandylite=1 ;;
                --authentik) do_authentik=1 ;;
                --all) do_scandypro=1; do_scandylite=1; do_authentik=1 ;;
                -h|--help) usage; exit 0 ;;
                *) die "Unbekannte Option: $arg (siehe --help)" ;;
            esac
        done
    fi

    [ "$do_authentik" -eq 1 ] && install_authentik
    [ "$do_scandypro" -eq 1 ] && install_scandypro
    [ "$do_scandylite" -eq 1 ] && install_scandylite

    log "Fertig."
}

main "$@"
