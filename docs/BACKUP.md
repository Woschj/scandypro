# Backup und Wiederherstellung

> Umsetzung von PR-001 aus [`tasks/produktivreife`](../tasks/produktivreife/README.md).
> Vor dem Einsatz mit echten Teilnehmerdaten ist ein eingerichtetes **und
> mindestens einmal geprobtes** Backup Pflicht.

ScandyPro verarbeitet Gesundheitsdaten nach Art. 9 DSGVO. Ein Datenverlust
trifft hier keine Konfiguration, die man neu anlegen kann, sondern
Tagebücher, Bewerbungen und Wochenberichte von Menschen, die diese Daten
nicht ein zweites Mal erzeugen können.

---

## Was gesichert wird

| Bestandteil | Enthält | Verschlüsselt? |
|---|---|---|
| `datenbank.dump` | Alle Tabellen (pg_dump, Custom-Format) | Art.-9-Felder als Fernet-Ciphertext, **Stammdaten im Klartext** |
| `uploads.tar.gz` | Bewerbungsunterlagen, Fotos | ja, Fernet (siehe `app/core/uploads.py`) |
| `backup.info` | Zeitpunkt, Betriebsart, Quellhost | – |

**Wichtig:** Der Datenbank-Dump ist trotz feldweiser Verschlüsselung
*nicht* harmlos. Namen, E-Mail-Adressen, Rollen, Zuordnungen und die
bcrypt-Passworthashes liegen darin im Klartext. Deshalb verschlüsselt
`backup.sh` das gesamte Archiv – ohne gesetzte Passphrase bricht es ab,
statt still eine ungeschützte Datei zu schreiben.

---

## Einrichtung

### 1. Passphrase erzeugen

```bash
echo "BACKUP_PASSPHRASE=$(openssl rand -base64 48)" >> .env
```

Diese Passphrase **getrennt vom Backup** aufbewahren (Passwortmanager der
Einrichtung, versiegelter Umschlag im Tresor). Liegt sie nur auf demselben
Server wie das Backup, schützt sie im Ernstfall gegen nichts.

Dasselbe gilt für `FIELD_ENCRYPTION_KEY`: Ohne ihn lässt sich ein
wiederhergestelltes Backup zwar starten, aber alle Tagebucheinträge,
Bewerbungsnotizen und hochgeladenen Dateien bleiben unlesbar. **Beide
Schlüssel gehören zusammen gesichert.**

### 2. Zielverzeichnis wählen

```bash
echo "BACKUP_DIR=/mnt/backup/scandypro" >> .env
```

Das Ziel sollte **nicht auf demselben Datenträger** liegen wie die
Docker-Volumes. Ein Netzlaufwerk, ein zweiter Datenträger oder ein
gemounteter Objektspeicher – sonst nimmt derselbe Hardwaredefekt Original
und Sicherung mit.

### 3. Täglich per Cron

```bash
sudo crontab -e
```

```cron
# ScandyPro: täglich um 03:15 sichern, Ausgabe ins Journal
15 3 * * *  cd /opt/scandypro && ./scripts/backup.sh >> /var/log/scandypro-backup.log 2>&1
```

Bei der Docker-Installation muss der ausführende Benutzer Zugriff auf den
Docker-Socket haben (Gruppe `docker`) – sonst findet das Skript den
Datenbank-Container nicht und bricht mit einer entsprechenden Meldung ab.

### 4. Aufbewahrung

Voreinstellung: 7 tägliche, 4 wöchentliche (sonntags), 6 monatliche
(am Ersten) Stände. Wochen- und Monatsstände sind Hardlinks auf den
jeweiligen Tagesstand und kosten daher keinen zusätzlichen Speicherplatz,
bis der Tagesstand wegrotiert.

Anpassbar über `BEHALTE_TAEGLICH`, `BEHALTE_WOECHENTLICH`,
`BEHALTE_MONATLICH` in der `.env`.

Die drei Generationen rotieren getrennt. Das ist Absicht: fällt das Backup
still aus und läuft danach mehrfach hintereinander durch, rotieren nicht
innerhalb von Stunden alle Stände weg.

Wochen- und Monatsstände werden per Hardlink angelegt. Kann das Zielsystem
keine Hardlinks – bei SMB-/NFS-Freigaben durchaus üblich, und genau solche
Netzlaufwerke sind hier als Ablageort empfohlen – wird stattdessen kopiert
und das im Log vermerkt. Lieber doppelter Speicherverbrauch als eine
Generation, die es stillschweigend nie gab.

Die Rotationslogik lässt sich ohne Datenbank prüfen:

```bash
./scripts/tests/rotation_test.sh
```

---

## Wiederherstellung

### Erst prüfen, dann zurückspielen

```bash
./scripts/restore.sh --pruefen /mnt/backup/scandypro/scandypro-2026-08-12T03-15-00.tar.gz.enc
```

Entschlüsselt und entpackt das Archiv in ein temporäres Verzeichnis, zeigt
Inhalt und Größen an und **verändert nichts**. Das ist der Aufruf für die
regelmäßige Kontrolle.

### Echte Wiederherstellung

```bash
./scripts/restore.sh /mnt/backup/scandypro/scandypro-2026-08-12T03-15-00.tar.gz.enc
```

Das Skript hält die App an, ersetzt Datenbank und Uploads vollständig und
startet die App wieder (die dabei automatisch `alembic upgrade head`
ausführt, falls der Code neuer ist als das Backup). Zur Bestätigung muss
`WIEDERHERSTELLEN` eingetippt werden – bewusst kein einfaches „j".

**Alle Daten, die nach dem Backup entstanden sind, gehen dabei verloren.**

---

## Den Restore proben

Ein Backup, das nie zurückgespielt wurde, ist kein Backup, sondern eine
Vermutung. Der folgende Ablauf wurde in dieser Form durchgeführt und
sollte nach jeder Änderung an Schema oder Infrastruktur wiederholt werden:

1. Ausgangszustand festhalten:
   ```bash
   docker compose exec -T db psql -U scandypro -d scandypro -t -c \
     "select (select count(*) from \"user\"), (select count(*) from tagebucheintrag);"
   ```
2. Backup erstellen: `./scripts/backup.sh`
3. Eine erkennbare Änderung erzeugen, die im Backup **nicht** enthalten ist
   (z. B. ein Handlungsfeld „RESTORE-TESTMARKE" anlegen).
4. Restore fahren: `./scripts/restore.sh <archiv>`
5. Prüfen:
   - Die Zeilenzahlen aus Schritt 1 stimmen wieder.
   - Die Testmarke aus Schritt 3 ist **weg** – nur das belegt, dass wirklich
     zurückgespielt und nicht bloß „nichts kaputtgemacht" wurde.
   - Login funktioniert.
   - Ein Tagebucheintrag ist im Klartext lesbar und ein Bewerbungsdokument
     lässt sich herunterladen und öffnen. Das belegt, dass
     `FIELD_ENCRYPTION_KEY` zum Backup passt – der häufigste Grund für ein
     „erfolgreiches" Restore, nach dem trotzdem alle Inhalte unlesbar sind.

Ergebnis des letzten Probelaufs (0.1.44, Docker-Betriebsart): Zeilenzahlen
identisch (145 Nutzende, 282 Karten, 8174 Tagebucheinträge, 378
Bewerbungen), Testmarke entfernt, verschlüsselte Felder nach dem Restore
korrekt entschlüsselt, alle 4 Upload-Dateien vorhanden und weiterhin als
Fernet-Ciphertext auf der Platte.

---

## Schlüsselrotation und Backups

`FIELD_ENCRYPTION_KEY` darf mehrere kommagetrennte Schlüssel enthalten,
**neuester zuerst**. Verschlüsselt wird mit dem ersten, entschlüsselt mit
jedem. Ein einzelner Schlüssel (der Normalfall) verhält sich unverändert.

Ablauf – die Reihenfolge ist nicht verhandelbar:

```bash
# 1. Neuen Schlüssel VORNE anhängen. Altdaten bleiben lesbar.
#    FIELD_ENCRYPTION_KEY=<neu>,<alt>
python scripts/reencrypt.py --pruefen   # zeigt, was noch am alten hängt

# 2. Bestandsdaten umschreiben (Datenbank + Uploads)
python scripts/reencrypt.py

# 3. Erst wenn --pruefen 0 offene Einträge meldet:
python scripts/reencrypt.py --pruefen   # muss "Nichts hängt mehr..." sagen
#    dann den alten Schlüssel aus FIELD_ENCRYPTION_KEY entfernen
```

Danach die App neu starten (die Schlüssel werden beim Import gelesen).

> ⚠️ **Wer Schritt 3 vor Schritt 2 macht, verliert die Daten endgültig** –
> und das Backup rettet nichts, weil dort derselbe Ciphertext liegt. Genau
> deshalb gibt es `--pruefen`; es beendet sich mit Exit-Code 1, solange
> noch etwas offen ist, und lässt sich damit in ein Skript einbauen.

### Was das für die Backups bedeutet

| Archiv aus | Braucht zum Restore |
|---|---|
| vor der Rotation | den **alten** Schlüssel |
| während der Rotation | **beide** Schlüssel (gemischter Bestand) |
| nach der Rotation | den **neuen** Schlüssel |

Alte Schlüssel deshalb **nicht wegwerfen, solange noch Backups aus ihrer
Zeit aufbewahrt werden** – bei 6 Monatsständen also mindestens ein halbes
Jahr. Am einfachsten: im Passwortmanager beim Schlüssel notieren, ab wann
er gilt, und ihn erst löschen, wenn das letzte Archiv aus seiner Zeit
rotiert ist.

Praktisch bewährt: direkt nach Schritt 2 ein frisches Backup ziehen. Dann
gibt es einen sauberen Stand, der nur den neuen Schlüssel braucht.

---

## Was dieses Backup nicht abdeckt

- **Die `.env` selbst.** Sie enthält `SECRET_KEY`, `FIELD_ENCRYPTION_KEY`
  und `BACKUP_PASSPHRASE` und wird bewusst *nicht* mitgesichert – ein
  Archiv, das seinen eigenen Schlüssel enthält, ist nicht verschlüsselt.
  Die `.env` gehört in den Passwortmanager der Einrichtung.
- **Point-in-Time-Recovery.** Wiederherstellbar ist der Stand des letzten
  Laufs, nicht ein beliebiger Zeitpunkt. Für kürzere Intervalle als 24 h
  den Cron-Eintrag häufiger takten.
- **Automatische Auslagerung.** Das Skript schreibt dorthin, wohin
  `BACKUP_DIR` zeigt. Dass dieses Ziel den Host überlebt (Netzlaufwerk,
  Offsite-Sync), muss die Einrichtung sicherstellen.
- **Zustellung der Warnung.** `BACKUP_PING_URL` (siehe unten) meldet
  Ausfälle an einen Monitoring-Dienst, aber jemand muss dessen
  Benachrichtigungen auch tatsächlich empfangen und lesen.

---

## Merken, wenn das Backup ausfällt

Ein Backup, das stillschweigend nicht mehr läuft, ist schlimmer als keines:
es gibt Sicherheit vor, die nicht existiert. Cron schickt zwar eine Mail
bei Ausgabe auf stderr – aber nur, wenn ein MTA eingerichtet ist, und in
einem LXC-Container ist das selten der Fall.

```bash
echo "BACKUP_PING_URL=https://hc-ping.com/DEINE-UUID" >> .env
```

Das Skript ruft diese URL nach jedem erfolgreichen Lauf auf und im
Fehlerfall mit dem Suffix `/fail`. Funktioniert mit
[healthchecks.io](https://healthchecks.io), Uptime Kuma (Push-Monitor) und
jedem Dienst, der auf einen HTTP-Aufruf hin einen Timer zurücksetzt.

Der eigentliche Nutzen liegt im **ausbleibenden** Ping: Der Monitor schlägt
Alarm, wenn das Backup gar nicht erst startet – weil der Cron-Eintrag
gelöscht wurde, der Container nicht läuft oder der Host aus ist. Genau
diese Fälle kann eine Fehlermeldung aus dem Skript naturgemäß nie melden.

Abgedeckt sind:

| Situation | Ping |
|---|---|
| Lauf erfolgreich | `URL` |
| Passphrase fehlt, Ziel nicht beschreibbar, … | `URL/fail` |
| Abbruch mitten im Lauf (DB weg, Platte voll, `kill`) | `URL/fail` |
| Backup läuft überhaupt nicht mehr | *kein Ping* → Monitor alarmiert |

Im Ping stehen bewusst keine Inhalte: Die URL geht an einen Dritten, und
dorthin gehören keine Datenbanknamen, Pfade oder Hostnamen.
