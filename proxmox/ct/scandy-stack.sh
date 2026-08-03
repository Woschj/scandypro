#!/usr/bin/env bash
# ScandyPro/Scandy-Lite/Authentik - EIN Einstiegspunkt fuer den gesamten
# Stack auf Proxmox VE: Mehrfachauswahl (jede Kombination der drei
# Komponenten), installiert die gewaehlten nacheinander.
#
# Dupliziert bewusst KEINE Container-Erstellungs-Logik - ruft stattdessen
# nacheinander die bereits vorhandenen, einzeln getesteten Installer auf:
#   - proxmox/ct/scandypro.sh        (dieses Repo)
#   - proxmox/ct/scandy-lite.sh      (Schwestermodul-Repo)
#   - community-scripts ct/authentik.sh (offizielles Drittanbieter-Skript)
# Jeder ruft weiterhin sein eigenes whiptail-Menue auf (Hostname/Ressourcen/
# Storage) - dieses Skript uebernimmt nur die Auswahl UND Reihenfolge, nicht
# die einzelnen Installations-Dialoge.
#
# Authentik-Zusatzschritt (nur wenn Authentik UND mind. eine App gewaehlt
# wurde): versucht nach der Installation automatisch einen OAuth2/OIDC-
# Provider + Application je gewaehlter App in Authentik anzulegen (per
# `ak apply_blueprint`, siehe unten) und traegt OIDC_ISSUER/OIDC_CLIENT_ID/
# OIDC_CLIENT_SECRET direkt in deren .env ein. Das ist NICHT gegen eine
# echte Authentik-Installation getestet (der genaue Pfad des `ak`/
# manage.py-Kommandos haengt vom exakten Stand des Community-Skripts ab -
# wird zur Laufzeit gesucht, nicht hart codiert) - schlaegt dieser
# Automatisierungsschritt fehl, bricht NUR er ab (Installation selbst ist
# bereits abgeschlossen), mit Verweis auf die manuellen Schritte in
# SSO_AUTHENTIK.md.
#
# Aufruf auf dem Proxmox-Host (als root):
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Woschj/scandypro/main/proxmox/ct/scandy-stack.sh)"

set -Eeuo pipefail

SCANDYPRO_CT_URL="https://raw.githubusercontent.com/Woschj/scandypro/main/proxmox/ct/scandypro.sh"
SCANDYLITE_CT_URL="https://raw.githubusercontent.com/Woschj/scandy-lite/master/proxmox/ct/scandy-lite.sh"
AUTHENTIK_CT_URL="https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/ct/authentik.sh"

if [[ $EUID -ne 0 ]]; then
  echo "FEHLER: Bitte als root auf dem Proxmox-Host ausführen." >&2
  exit 1
fi
if ! command -v pct >/dev/null 2>&1; then
  echo "FEHLER: 'pct' wurde nicht gefunden - dieses Skript läuft nur auf einem Proxmox-VE-Host." >&2
  exit 1
fi

if ! command -v whiptail >/dev/null 2>&1; then
  apt-get update -qq >/dev/null 2>&1 || true
  apt-get install -y -qq whiptail >/dev/null 2>&1 || true
fi
HAVE_WHIPTAIL=0
command -v whiptail >/dev/null 2>&1 && HAVE_WHIPTAIL=1

echo "=== ScandyPro-Stack - Proxmox VE Installer ==="

# --- Auswahl: beliebige Kombination -----------------------------------------
DO_SCANDYPRO=0 DO_SCANDYLITE=0 DO_AUTHENTIK=0
if [[ "$HAVE_WHIPTAIL" -eq 1 ]]; then
  SELECTION="$(whiptail --title "ScandyPro-Stack" --checklist \
    "Was soll installiert werden? (Leertaste zum An-/Abwaehlen, Enter zum Bestaetigen)" \
    15 70 3 \
    scandypro "ScandyPro" ON \
    scandylite "Scandy-Lite" OFF \
    authentik "Authentik (SSO)" OFF \
    3>&1 1>&2 2>&3)" || { echo "Abgebrochen."; exit 0; }
  [[ "$SELECTION" == *scandypro* ]] && DO_SCANDYPRO=1
  [[ "$SELECTION" == *scandylite* ]] && DO_SCANDYLITE=1
  [[ "$SELECTION" == *authentik* ]] && DO_AUTHENTIK=1
else
  ask_yn() {
    local prompt="$1" answer
    while true; do
      read -r -p "${prompt} [j/n]: " answer
      case "$answer" in
        j|J|y|Y) return 0 ;;
        n|N) return 1 ;;
        *) echo "Bitte j oder n eingeben." ;;
      esac
    done
  }
  ask_yn "ScandyPro installieren?" && DO_SCANDYPRO=1
  ask_yn "Scandy-Lite installieren?" && DO_SCANDYLITE=1
  ask_yn "Authentik installieren?" && DO_AUTHENTIK=1
fi

if [[ "$DO_SCANDYPRO" -eq 0 && "$DO_SCANDYLITE" -eq 0 && "$DO_AUTHENTIK" -eq 0 ]]; then
  echo "Nichts ausgewählt - Abbruch."
  exit 0
fi

# snapshot_vmids / new_vmid_since: ermittelt die waehrend eines
# Installer-Laufs neu angelegte Container-ID, ohne dass die einzelnen
# Skripte ihre VMID selbst zurueckgeben muessten (tun sie nicht - sie sind
# fuer den eigenstaendigen Aufruf gedacht). Bei "Aktualisieren" statt
# Neuinstallation bleibt die Menge unveraendert - dann findet der
# Authentik-Verdrahtungsschritt spaeter keine neue VMID und wird
# uebersprungen (informative Meldung, kein Fehler).
snapshot_vmids() { pct list | tail -n +2 | awk '{print $1}' | sort; }
new_vmid_since() {
  local before="$1" after
  after="$(snapshot_vmids)"
  comm -13 <(echo "$before") <(echo "$after") | tail -n1
}

declare -A APP_VMID

if [[ "$DO_SCANDYPRO" -eq 1 ]]; then
  echo ""; echo "=== ScandyPro installieren ==="
  BEFORE="$(snapshot_vmids)"
  bash -c "$(curl -fsSL "$SCANDYPRO_CT_URL")"
  VMID="$(new_vmid_since "$BEFORE")"
  [[ -n "$VMID" ]] && APP_VMID[scandypro]="$VMID"
fi

if [[ "$DO_SCANDYLITE" -eq 1 ]]; then
  echo ""; echo "=== Scandy-Lite installieren ==="
  BEFORE="$(snapshot_vmids)"
  bash -c "$(curl -fsSL "$SCANDYLITE_CT_URL")"
  VMID="$(new_vmid_since "$BEFORE")"
  [[ -n "$VMID" ]] && APP_VMID[scandylite]="$VMID"
fi

if [[ "$DO_AUTHENTIK" -eq 1 ]]; then
  echo ""; echo "=== Authentik installieren (Community-Skript) ==="
  BEFORE="$(snapshot_vmids)"
  bash -c "$(curl -fsSL "$AUTHENTIK_CT_URL")"
  AUTHENTIK_VMID="$(new_vmid_since "$BEFORE")"

  if [[ -z "$AUTHENTIK_VMID" ]]; then
    echo "Konnte die neue Authentik-Container-ID nicht automatisch ermitteln (evtl. Aktualisierung statt Neuinstallation) - automatische OIDC-Verdrahtung wird übersprungen."
  elif [[ "${#APP_VMID[@]}" -eq 0 ]]; then
    echo "Keine ScandyPro/Scandy-Lite-Installation in diesem Lauf - keine OIDC-Verdrahtung noetig."
  else
    echo ""
    echo "=== Authentik-OIDC automatisch fuer ${!APP_VMID[*]} einrichten ==="
    echo "Dieser Schritt ist experimentell (nicht gegen eine echte Authentik-Instanz"
    echo "getestet) - schlaegt er fehl, ist die Installation selbst trotzdem fertig;"
    echo "die manuelle Einrichtung steht in SSO_AUTHENTIK.md Teil B."

    AUTHENTIK_IP="$(pct exec "$AUTHENTIK_VMID" -- hostname -I 2>/dev/null | awk '{print $1}' || true)"
    if [[ -z "$AUTHENTIK_IP" ]]; then
      echo "Konnte IP von Authentik-Container ${AUTHENTIK_VMID} nicht ermitteln - Automatisierung übersprungen."
    else
      # manage.py-Pfad wird gesucht statt hart codiert, da er vom genauen
      # Stand/Layout des Community-Skripts abhaengt (aktuell: /opt/authentik).
      # Aufruf explizit ueber den venv-Python (nicht "python manage.py"
      # direkt), da manage.py's Shebang "#!/usr/bin/env python" nur mit der
      # PATH-Umgebung des systemd-Dienstes korrekt auf den venv-Interpreter
      # zeigt, nicht in einem plain "pct exec".
      MANAGE_PY="$(pct exec "$AUTHENTIK_VMID" -- bash -c 'find / -maxdepth 6 -iname manage.py 2>/dev/null | grep -m1 authentik' || true)"
      if [[ -z "$MANAGE_PY" ]]; then
        echo "Konnte manage.py in Container ${AUTHENTIK_VMID} nicht finden - automatische OIDC-Verdrahtung übersprungen."
        echo "Bitte SSO_AUTHENTIK.md Teil B fuer die manuelle Einrichtung verwenden."
      else
        AK_DIR="$(dirname "$MANAGE_PY")"
        AK_PYTHON="$(pct exec "$AUTHENTIK_VMID" -- bash -c "command -v '${AK_DIR}/.venv/bin/python' 2>/dev/null || command -v '${AK_DIR}/venv/bin/python' 2>/dev/null" || true)"
        if [[ -z "$AK_PYTHON" ]]; then
          echo "Konnte venv-Python neben manage.py in Container ${AUTHENTIK_VMID} nicht finden - automatische OIDC-Verdrahtung übersprungen."
          echo "Bitte SSO_AUTHENTIK.md Teil B fuer die manuelle Einrichtung verwenden."
        else
        for app in "${!APP_VMID[@]}"; do
          app_vmid="${APP_VMID[$app]}"
          app_ip="$(pct exec "$app_vmid" -- hostname -I 2>/dev/null | awk '{print $1}' || true)"
          [[ -z "$app_ip" ]] && continue

          case "$app" in
            scandypro) app_name="ScandyPro"; app_dir="/opt/scandypro"; service_name="scandypro" ;;
            scandylite) app_name="Scandy-Lite"; app_dir="/opt/scandy-lite"; service_name="scandy-lite" ;;
          esac

          client_id="$(openssl rand -hex 16)"
          client_secret="$(openssl rand -hex 32)"
          redirect_uri="https://${app_ip}:8443/auth/oidc/callback"
          slug="${app}"

          echo "Lege OAuth2-Provider + Application fuer ${app_name} in Authentik an..."
          # apply_blueprint erwartet einen Pfad RELATIV zu blueprints_dir
          # (Standard: /opt/authentik/blueprints), kein beliebiger absoluter
          # Pfad ("Invalid blueprint path") - "local/" ist die uebliche
          # Authentik-Konvention fuer eigene Blueprints.
          blueprint_rel="local/${app}-oidc.yaml"
          blueprint_abs="${AK_DIR}/blueprints/${blueprint_rel}"
          pct exec "$AUTHENTIK_VMID" -- mkdir -p "${AK_DIR}/blueprints/local"
          pct exec "$AUTHENTIK_VMID" -- tee "$blueprint_abs" >/dev/null <<EOF
version: 1
metadata:
  name: ${app}-oidc-autoprovision
entries:
  - model: authentik_providers_oauth2.oauth2provider
    id: ${app}-provider
    identifiers:
      name: ${app_name}
    attrs:
      name: ${app_name}
      client_type: confidential
      client_id: ${client_id}
      client_secret: ${client_secret}
      redirect_uris:
        - matching_mode: strict
          url: "${redirect_uri}"
          redirect_uri_type: authorization
      authorization_flow: !Find [authentik_flows.flow, [slug, default-provider-authorization-implicit-consent]]
      invalidation_flow: !Find [authentik_flows.flow, [slug, default-provider-invalidation-flow]]
      signing_key: !Find [authentik_crypto.certificatekeypair, [name, authentik Self-signed Certificate]]
  - model: authentik_core.application
    identifiers:
      slug: ${slug}
    attrs:
      name: ${app_name}
      slug: ${slug}
      provider: !KeyOf ${app}-provider
EOF
          pct exec "$AUTHENTIK_VMID" -- chown authentik:authentik "$blueprint_abs" 2>/dev/null || true
          if pct exec "$AUTHENTIK_VMID" -- bash -c "cd '${AK_DIR}' && '${AK_PYTHON}' manage.py apply_blueprint '$blueprint_rel'" 2>&1; then
            echo "Provider/Application fuer ${app_name} angelegt. Trage OIDC_*-Werte in ${app}.env ein..."
            # Port 9443 ist der Standard-HTTPS-Port des community-scripts-
            # Authentik-Installers (AUTHENTIK_LISTEN__HTTPS) - bei
            # abweichender Authentik-Installation ggf. anpassen.
            pct exec "$app_vmid" -- bash -c "
              sed -i '/^OIDC_ISSUER=/d;/^OIDC_CLIENT_ID=/d;/^OIDC_CLIENT_SECRET=/d' '${app_dir}/.env'
              cat >> '${app_dir}/.env' <<ENVEOF
OIDC_ISSUER=https://${AUTHENTIK_IP}:9443/application/o/${slug}/
OIDC_CLIENT_ID=${client_id}
OIDC_CLIENT_SECRET=${client_secret}
ENVEOF
              systemctl restart ${service_name}-https 2>/dev/null || systemctl restart ${service_name} 2>/dev/null || true
            "
            echo "${app_name}: OIDC eingerichtet, Dienst neu gestartet."
          else
            echo "Blueprint-Anwendung fuer ${app_name} fehlgeschlagen - bitte SSO_AUTHENTIK.md Teil B manuell durchgehen."
          fi
        done
        fi
      fi
    fi
  fi
fi

echo ""
echo "=== Fertig ==="
for app in "${!APP_VMID[@]}"; do
  echo "${app}: Container ${APP_VMID[$app]}"
done
