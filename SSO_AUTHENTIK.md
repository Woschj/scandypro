# ScandyPro — SSO-Login über Authentik einrichten

Optionales Feature (siehe [CHANGELOG.md](CHANGELOG.md) 0.1.28): ein
zusätzlicher "Mit \<Provider\>-Login"-Button neben dem normalen
E-Mail/Passwort-Formular. Standardmäßig aus — erst aktiv, wenn die drei
`OIDC_*`-Variablen gesetzt sind (siehe Schritt 5). Ziel ist ein **gemeinsamer
Login für ScandyPro und das Schwestermodul
[Scandy-Lite](https://github.com/Woschj/scandy-lite)**, das dieselbe
Anbindung bereits produktiv nutzt — beide Apps werden dafür als **zwei
getrennte Applications/Provider** im selben Authentik registriert (eigene
Client-ID/Secret, eigene Redirect-URI je App), nicht als eine gemeinsame.

Ablauf danach (siehe Schritt 6): Erster Login einer neuen Person legt
automatisch ein Konto an, aber **gesperrt, ohne Rolle** — eine
Einrichtungs-Admin muss es unter **Benutzerverwaltung → "Wartet auf
Freischaltung"** erst freischalten (Rolle + Abteilung festlegen). Der
Identity-Provider klärt nur "wer ist das", nie "was darf die Person" — siehe
`app/core/oidc.py` und `docs/DATENSCHUTZ_UND_BERECHTIGUNGEN.md` §4.4.

Dieses Dokument deckt beides ab: **A)** Authentik selbst installieren, falls
noch keine Instanz existiert, und **B)** ScandyPro daran anbinden. Wer schon
eine laufende Authentik-Instanz hat (z. B. aus der Scandy-Lite-Installation),
kann direkt zu Teil B springen.

## Voraussetzungen

- Ein Server/Host für Authentik (kann derselbe Host wie ScandyPro sein, muss
  aber nicht — Authentik ist als **eigener, unabhängiger Dienst** gedacht,
  den sich mehrere Apps teilen)
- ScandyPro muss Authentik über das Netzwerk erreichen können (der
  App-Container ruft Authentik serverseitig auf, nicht nur der Browser der
  Nutzer:innen)
- **ScandyPro muss über HTTPS erreichbar sein**, bevor SSO produktiv genutzt
  wird — Authentik akzeptiert bei einem "Confidential"-Client i. d. R. keine
  reinen HTTP-Redirect-URIs. Gilt auch bei einem rein intern erreichbaren
  Server (kein öffentliches Internet, aber trotzdem HTTPS nötig). Umstellung
  von HTTP auf HTTPS: siehe README.md, Abschnitt "TLS (Produktivbetrieb)" —
  entweder mit echter Domain (`caddy/Caddyfile.domain-example`, Let's
  Encrypt) oder selbstsigniert fürs interne Netz ohne Domain
  (`caddy/Caddyfile.internal-tls-example`) — dort auch der Schritt,
  `SESSION_COOKIE_SECURE=true` zu setzen, was für SSO ebenfalls
  Voraussetzung ist. Bei selbstsigniertem Zertifikat zeigt der Browser beim
  ersten Aufruf von ScandyPro eine Warnung, die einmalig pro Gerät bestätigt
  werden muss - der SSO-Ablauf selbst funktioniert davon unabhängig.
- **Bei selbstsigniertem Zertifikat auf BEIDEN Seiten (ScandyPro/Scandy-Lite
  UND Authentik ohne echte Domain) muss ScandyPro dem Authentik-Zertifikat
  explizit vertrauen** - live getestet (2026-08-03, `proxmox/ct/scandy-stack.sh`
  gegen einen frisch installierten Authentik-Container): Authentiks
  Community-Skript generiert beim ersten Start ein generisches
  Selbstsigniert-Zertifikat (`CN=authentik default certificate`, **ohne**
  passenden SAN-Eintrag für die tatsächliche Server-IP/-Domain). Der
  serverseitige OIDC-Discovery-Aufruf von ScandyPro (`/auth/oidc/login` →
  `authlib` ruft `.well-known/openid-configuration` ab) schlägt dadurch
  IMMER fehl (`SSL: no alternative certificate subject name matches target
  ipv4 address ...`), selbst wenn die CA selbst als vertrauenswürdig
  eingetragen wurde. Zwei Wege, das zu beheben:
  1. **Empfohlen:** Authentik hinter einer echten Domain mit gültigem
     Zertifikat betreiben (Let's Encrypt) statt mit dem generischen
     Selbstsigniert-Zertifikat - dann entfällt dieser Schritt komplett.
  2. **Für rein interne Testumgebungen:** Authentiks Zertifikat manuell
     durch eines mit korrektem SAN ersetzen (analog zu
     `/etc/ssl/scandypro/scandypro.crt`, siehe README.md "TLS
     (Produktivbetrieb)") und/oder das Zertifikat in den
     ScandyPro-Container importieren:
     ```bash
     # Auf dem Proxmox-Host, <authentik-vmid> anpassen:
     pct exec <authentik-vmid> -- bash -c \
       "openssl s_client -connect 127.0.0.1:9443 -servername <authentik-ip> </dev/null 2>/dev/null | openssl x509" \
       > /root/authentik-ca.crt
     pct push <scandypro-vmid> /root/authentik-ca.crt /usr/local/share/ca-certificates/authentik-selfsigned.crt
     pct exec <scandypro-vmid> -- update-ca-certificates
     ```
     Behebt nur das CA-Vertrauen, NICHT den fehlenden SAN-Eintrag - für
     einen echten Fix muss das Authentik-Zertifikat selbst durch eines mit
     passendem SAN ersetzt werden (liegt außerhalb dieses Dokuments, siehe
     Authentik-eigene Doku zu `AUTHENTIK_WEB__CERTIFICATE`/eigenem Zertifikat).

---

## Teil A: Authentik installieren

Überspringen, falls bereits eine Authentik-Instanz läuft. Zwei gleichwertige
Wege, je nachdem wie ihr ScandyPro/Scandy-Lite selbst schon betreibt:

- **Option 1 (empfohlen bei Proxmox VE)**: natives LXC-Container über das
  Community-Skript — passt zum bestehenden Muster (`scandypro.sh`,
  `scandy-lite.sh`), ein Skript pro Dienst, alle drei einzeln snapshotbar.
- **Option 2**: Docker Compose — der von den Authentik-Entwicklern selbst
  offiziell dokumentierte und gepflegte Weg, unabhängig von Proxmox.

Beide Wege führen zum selben Ergebnis (Teil B braucht nur die erreichbare
URL, unabhängig davon, wie Authentik betrieben wird).

### Option 1: LXC-Container per Community-Skript

Das [community-scripts-Projekt](https://community-scripts.github.io/ProxmoxVE/)
(Nachfolger der bekannten tteck-Proxmox-Skripte) pflegt ein eigenes
Authentik-Skript: natives LXC mit PostgreSQL, Redis und dem Authentik-Build
selbst über systemd-Units — kein Docker im Container nötig.

**Wichtig, weil von Dritten gepflegt statt von Authentik selbst**: Versionen
folgen mit etwas Verzögerung, und bei Update-Problemen ist die
community-scripts-Community die erste Anlaufstelle, nicht die
Authentik-Doku. Vor dem Ausführen kurz reinschauen, wie bei jedem
Drittanbieter-Skript, das per `curl | bash` läuft:

```bash
# auf dem Proxmox-Host (als root) - Skript-Übersicht/Details:
# https://community-scripts.github.io/ProxmoxVE/scripts?id=authentik
bash -c "$(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/ct/authentik.sh)"
```

Legt einen eigenen LXC-Container an, installiert Authentik nativ und zeigt
am Ende die IP sowie die Erstzugangsdaten (`akadmin`) an. Danach weiter mit
**A.3 (Domain/HTTPS)** unten.

### Option 2: Docker Compose

Authentik lebt **nicht** in ScandyPros `compose.yaml` — es ist ein eigener,
von ScandyPro und Scandy-Lite unabhängiger Dienst. Eigenes Verzeichnis
anlegen, z. B. neben den beiden App-Installationen:

```bash
mkdir -p ~/authentik && cd ~/authentik
```

#### A.1 `.env` anlegen

```bash
cat > .env <<'EOF'
PG_PASS=change-me-postgres-passwort
AUTHENTIK_SECRET_KEY=change-me-langer-zufaelliger-string
AUTHENTIK_ERROR_REPORTING__ENABLED=false
EOF
```

Zufällige Werte erzeugen:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"   # für PG_PASS
python3 -c "import secrets; print(secrets.token_urlsafe(50))"  # für AUTHENTIK_SECRET_KEY
```

#### A.2 `compose.yaml` anlegen

```yaml
services:
  postgresql:
    image: docker.io/library/postgres:16-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -d $${POSTGRES_DB} -U $${POSTGRES_USER}"]
      start_period: 20s
      interval: 30s
      retries: 5
      timeout: 5s
    volumes:
      - database:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: ${PG_PASS}
      POSTGRES_USER: authentik
      POSTGRES_DB: authentik
    env_file:
      - .env

  redis:
    image: docker.io/library/redis:alpine
    command: --save 60 1 --loglevel warning
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "redis-cli ping | grep PONG"]
      start_period: 20s
      interval: 30s
      retries: 5
      timeout: 3s
    volumes:
      - redis:/data

  server:
    image: ghcr.io/goauthentik/server:2024.10
    restart: unless-stopped
    command: server
    environment:
      AUTHENTIK_REDIS__HOST: redis
      AUTHENTIK_POSTGRESQL__HOST: postgresql
      AUTHENTIK_POSTGRESQL__USER: authentik
      AUTHENTIK_POSTGRESQL__NAME: authentik
      AUTHENTIK_POSTGRESQL__PASSWORD: ${PG_PASS}
    volumes:
      - media:/media
      - custom-templates:/templates
    env_file:
      - .env
    ports:
      - "9000:9000"
      - "9443:9443"
    depends_on:
      - postgresql
      - redis

  worker:
    image: ghcr.io/goauthentik/server:2024.10
    restart: unless-stopped
    command: worker
    environment:
      AUTHENTIK_REDIS__HOST: redis
      AUTHENTIK_POSTGRESQL__HOST: postgresql
      AUTHENTIK_POSTGRESQL__USER: authentik
      AUTHENTIK_POSTGRESQL__NAME: authentik
      AUTHENTIK_POSTGRESQL__PASSWORD: ${PG_PASS}
    user: root
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - media:/media
      - certs:/certs
      - custom-templates:/templates
    env_file:
      - .env
    depends_on:
      - postgresql
      - redis

volumes:
  database:
  redis:
  media:
  certs:
  custom-templates:
```

Aktuelle Image-Version vor dem ersten Start prüfen unter
<https://docs.goauthentik.io/docs/install-config/install/docker-compose> —
`2024.10` oben ist ein Platzhalter für "eine funktionierende, zum
Erstellungszeitpunkt aktuelle Version", keine feste Empfehlung.

Starten:

```bash
docker compose up -d
```

Erststart dauert einen Moment (Datenbank-Migrationen). Fortschritt prüfen:

```bash
docker compose logs -f server
```

### A.3 Auf Domain/HTTPS bringen

Unabhängig von Option 1 oder 2 braucht Authentik selbst HTTPS mit eigener
Domain, sobald andere Apps produktiv dagegen laufen sollen (nicht nur
`:9000`/die Container-IP im lokalen Netz). Am einfachsten mit einem eigenen
Caddy davor:

```caddyfile
authentik.eure-domain.de {
    reverse_proxy localhost:9000
}
```

(Bei Option 1 läuft Authentik direkt im LXC auf Port 9000 - Caddy entweder
im selben Container oder in einem weiteren kleinen LXC/auf dem
Proxmox-Host selbst.)

### A.4 Ersteinrichtung (Setup-Wizard)

Im Browser `https://authentik.eure-domain.de/if/flow/initial-setup/` öffnen
(oder `http://<host>:9000/if/flow/initial-setup/` bei reinem Test ohne
Domain). Dort wird beim allerersten Aufruf ein `akadmin`-Konto mit Passwort
eurer Wahl angelegt (bei Option 1 zeigt das Skript ggf. schon fertige
Zugangsdaten an - dann diesen Schritt nur zur Kontrolle öffnen) — danach ist
die Instanz einsatzbereit für Teil B.

---

## Teil B: ScandyPro anbinden

### 1. Provider in Authentik anlegen

**Applications → Providers → Create**

| Feld | Wert |
|---|---|
| Provider-Typ | **OAuth2/OpenID Provider** |
| Name | z. B. `ScandyPro` |
| Authorization flow | eine vorhandene Consent-Flow (z. B. `default-provider-authorization-explicit-consent`) |
| Client type | **Confidential** (ScandyPro hält das Secret sicher serverseitig — **nicht** "Public" wählen) |
| Redirect URIs/Origins (Strict) | `https://<eure-scandypro-domain>/auth/oidc/callback` **exakt so, inkl. Pfad** |
| Scopes | die Standard-Mappings reichen: `openid`, `email`, `profile` |
| Signing Key | einen vorhandenen Zertifikatsschlüssel auswählen (Pflichtfeld) |

Speichern. Authentik zeigt danach **Client ID** und **Client Secret** an
(Provider-Detailseite bzw. beim Bearbeiten sichtbar) — beide sofort notieren,
das Secret wird später nicht mehr im Klartext angezeigt.

### 2. Application anlegen und verknüpfen

**Applications → Applications → Create**

| Feld | Wert |
|---|---|
| Name | z. B. `ScandyPro` |
| Slug | z. B. `scandypro` (landet in der Issuer-URL, siehe Schritt 3) |
| Provider | den in Schritt 1 angelegten Provider auswählen |
| Launch URL (optional) | `https://<eure-scandypro-domain>/` |

Speichern. Falls euer Authentik-Setup Zugriff über Gruppen/Policies steuert:
unter der Application die passenden Nutzer:innen/Gruppen freigeben, sonst
bekommen sie beim Login "Access denied", bevor sie überhaupt bei ScandyPro
ankommen.

### 3. Issuer-URL finden

Auf der Provider-Detailseite (Schritt 1) steht ein Link/Feld **"OpenID
Configuration URL"**, meist in der Form:

```
https://authentik.eure-domain.de/application/o/<slug>/.well-known/openid-configuration
```

Für ScandyPro braucht ihr davon nur den Teil **vor** `.well-known/...`, also:

```
https://authentik.eure-domain.de/application/o/<slug>/
```

(`<slug>` ist der Application-Slug aus Schritt 2.)

### 4. Zweite Application für Scandy-Lite (falls gewünscht)

Schritte 1–3 ein zweites Mal, mit eigenem Namen/Slug (z. B. `Scandy-Lite`)
und der Redirect-URI `https://<eure-scandy-lite-domain>/auth/oidc/callback`
— siehe [Scandy-Lites eigene SSO_AUTHENTIK.md](https://github.com/Woschj/scandy-lite/blob/main/SSO_AUTHENTIK.md).
Ergebnis: dieselbe Person meldet sich bei Authentik einmal an und bekommt
danach in beiden Apps Zugriff angeboten (nach jeweils eigener
Rollen-Freischaltung, siehe Schritt 6).

### 5. ScandyPro konfigurieren

Drei bzw. vier Umgebungsvariablen in ScandyPros `.env` setzen (siehe
`.env.example`):

| Variable | Wert |
|---|---|
| `OIDC_ISSUER` | die URL aus Schritt 3, **mit** abschließendem `/` |
| `OIDC_CLIENT_ID` | aus Schritt 1 |
| `OIDC_CLIENT_SECRET` | aus Schritt 1 |
| `OIDC_PROVIDER_NAME` | optional, Beschriftung des Buttons, z. B. `Authentik` (Default: `SSO`) |

```bash
docker compose up -d --build app
```

(Neustart reicht auch ohne `--build`, solange sich nur `.env` geändert hat —
`--build` nur nötig, falls parallel auch Code aktualisiert wurde.) Auf
`/login` erscheint danach unter dem normalen Formular ein zusätzlicher
Button "Mit \<OIDC_PROVIDER_NAME\> anmelden".

### 6. Testen

1. Ausloggen (oder privates Fenster), `/login` öffnen, auf den neuen Button
   klicken
2. Bei Authentik anmelden (+ ggf. Consent bestätigen)
3. Zurück bei ScandyPro: Seite **"Fast geschafft"** sollte erscheinen (bei
   **erstem** Login einer neuen Person) — die Person wartet jetzt auf
   Freischaltung
4. Als Einrichtungs-Admin einloggen (lokal, oder ein bereits freigeschaltetes
   Konto), zu **Benutzerverwaltung → Accounts** (`/admin/benutzer`)
5. Gruppe **"Wartet auf Freischaltung"** aufklappen, bei der neuen Person auf
   **"Rolle zuweisen"** klicken
6. Rolle (und bei Teilnehmer:innen die Abteilung) wählen, **Speichern**,
   danach **"Account reaktivieren"**
7. Die Person kann sich jetzt erneut über den Authentik-Button anmelden und
   kommt direkt durch

## Fehlerbehebung

| Symptom | Wahrscheinliche Ursache | Lösung |
|---|---|---|
| Button "Mit ... anmelden" erscheint nicht | `OIDC_ISSUER`/`OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` nicht (vollständig) gesetzt | alle drei in `.env` prüfen, `docker compose up -d app` erneut ausführen |
| Nach Klick auf den Button: Fehlerseite bei Authentik ("invalid redirect_uri" o. ä.) | Redirect-URI in Authentik weicht ab | in Authentik exakt `https://<domain>/auth/oidc/callback` eintragen (Schema, Domain, Pfad müssen exakt passen) |
| Nach Authentik-Login zurück bei ScandyPro: Fehlerseite/500 | `OIDC_ISSUER` falsch/unerreichbar, `OIDC_CLIENT_SECRET` falsch, oder Authentik nutzt ein selbstsigniertes Zertifikat, das der App-Container nicht vertraut | Werte prüfen; bei selbstsigniertem Zertifikat auf Authentik-Seite ein von der Umgebung vertrauenswürdiges Zertifikat verwenden (z. B. via Caddy/Let's Encrypt wie in Teil A.3) |
| Bei Authentik: "Access denied" vor der Weiterleitung | Nutzer:in/Gruppe hat in Authentik keinen Zugriff auf die Application | unter der Application in Authentik den Zugriff freigeben (siehe Schritt 2) |
| Konto bleibt dauerhaft auf "Wartet auf Freischaltung" | Noch niemand hat es freigeschaltet | als Admin unter Benutzerverwaltung freischalten (siehe Schritt 6) |
| "Bitte zuerst eine Rolle zuweisen und speichern." beim Aktivieren-Versuch | Rolle wurde noch nicht gespeichert, bevor auf "Account reaktivieren" geklickt wurde | zuerst Rolle wählen und **Speichern**, danach erst aktivieren (zwei getrennte Formulare, bewusst so - siehe `app/routers/admin.py:benutzer_aktiv_umschalten`) |
| Neue Person landet in der falschen/keiner Abteilung | Abteilung wird beim Freischalten bewusst erst dort festgelegt, nicht automatisch aus Authentik übernommen | beim Freischalten die richtige Abteilung wählen — danach wie gewohnt in der Benutzerverwaltung korrigierbar |
| Zwei Accounts für dieselbe Person (einer lokal, einer per SSO) | Die E-Mail-Adressen bei Authentik und im bereits existierenden ScandyPro-Account stimmen nicht exakt überein | in Authentik die E-Mail der Person korrigieren, oder in ScandyPro die E-Mail des lokalen Accounts anpassen — bei nächstem SSO-Login mit übereinstimmender E-Mail verknüpft ScandyPro automatisch (siehe `app/core/oidc.py:finde_oder_lege_an`), Duplikat danach manuell in der Benutzerverwaltung deaktivieren |
