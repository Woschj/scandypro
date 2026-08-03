/*
 * Interaktive Elemente im 5-Minuten-Tagebuch (siehe app/templates/wohlbefinden/
 * uebersicht.html, app/routers/wohlbefinden.py): eine Verbinde-die-Punkte-
 * Atemübung vor dem Schreiben und ein Freihand-Zeichenfeld für den Abend -
 * beide bewusst ohne serverseitige Zwischenspeicherung während der
 * Interaktion, das Ergebnis landet erst beim regulären Formular-Submit in
 * den bestehenden Feldern (atemuebung_erledigt/zeichnung_daten).
 *
 * Reine Teilnahme statt Bewertung (siehe CLAUDE.md §24/25): die Atemübung
 * hat kein "richtig/falsch", nur "gemacht oder nicht"; die Zeichnung wird
 * nie ausgewertet, nur gespeichert.
 */
(function () {
  function svgPunkt(svg, evt) {
    const punkt = svg.createSVGPoint();
    const quelle = evt.touches ? evt.touches[0] : evt;
    punkt.x = quelle.clientX;
    punkt.y = quelle.clientY;
    return punkt.matrixTransform(svg.getScreenCTM().inverse());
  }

  function initPunkteUebungen() {
    // Gemeinsames Widget fuer Atemuebung UND Koerper-Scan (siehe
    // app/core/punkte_layout.py) - welches versteckte Feld beim
    // Abschliessen gesetzt wird, steht in data-punkte-feld am Wrapper.
    document.querySelectorAll("[data-punkte-uebung]").forEach((wrapper) => {
      const svg = wrapper.querySelector("svg");
      const linie = wrapper.querySelector("[data-linie]");
      const kreise = [...wrapper.querySelectorAll("[data-punkt]")];
      const hinweis = wrapper.querySelector("[data-punkte-hinweis]");
      const feldName = wrapper.dataset.punkteFeld;
      const hiddenInput = feldName ? wrapper.querySelector(`input[name="${feldName}"]`) : null;
      if (!svg || !hiddenInput) return;

      const RADIUS_TREFFER = 22;
      let naechsterIndex = 0;
      let pfad = "";
      let aktiv = false;
      let gesperrtBisMs = 0;

      if (hiddenInput.value === "true") {
        kreise.forEach((k) => k.classList.add("atemuebung-punkt--erreicht"));
        naechsterIndex = kreise.length;
        if (hinweis) hinweis.textContent = "Schon gemacht - danke fürs Innehalten.";
      }

      function abstand(a, b) {
        return Math.hypot(a.x - b.x, a.y - b.y);
      }

      // "Halten"-Punkte (data-halten > 0) schalten nicht sofort weiter,
      // sondern zählen erst sinnvoll herunter (siehe Nutzer-Feedback: 5-6
      // Sekunden) - Fingerposition ist dabei egal, es ist eine bewusste
      // Pause, kein Präzisionstest.
      function starteHaltenCountdown(sekunden) {
        gesperrtBisMs = Date.now() + sekunden * 1000;
        let verbleibend = sekunden;
        if (hinweis) hinweis.textContent = `Halten … noch ${verbleibend}`;
        const intervall = setInterval(() => {
          verbleibend -= 1;
          if (verbleibend <= 0) {
            clearInterval(intervall);
            if (hinweis && naechsterIndex < kreise.length) hinweis.textContent = "Weiter, wenn du bereit bist.";
            return;
          }
          if (hinweis) hinweis.textContent = `Halten … noch ${verbleibend}`;
        }, 1000);
      }

      function pruefeTreffer(p) {
        if (naechsterIndex >= kreise.length) return;
        if (Date.now() < gesperrtBisMs) return;
        const zielKreis = kreise[naechsterIndex];
        const ziel = { x: parseFloat(zielKreis.getAttribute("cx")), y: parseFloat(zielKreis.getAttribute("cy")) };
        if (abstand(p, ziel) <= RADIUS_TREFFER) {
          zielKreis.classList.add("atemuebung-punkt--erreicht");
          naechsterIndex += 1;
          const haltenSekunden = parseFloat(zielKreis.dataset.halten || "0");
          if (naechsterIndex >= kreise.length) {
            hiddenInput.value = "true";
            if (hinweis) hinweis.textContent = "Geschafft - schön, dass du dir die Pause genommen hast.";
            aktiv = false;
          } else if (haltenSekunden > 0) {
            starteHaltenCountdown(haltenSekunden);
          }
        }
      }

      function weiterzeichnen(evt) {
        if (!aktiv || naechsterIndex >= kreise.length) return;
        const p = svgPunkt(svg, evt);
        pfad += ` L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
        linie.setAttribute("d", pfad);
        pruefeTreffer(p);
      }

      svg.addEventListener("pointerdown", (evt) => {
        if (naechsterIndex >= kreise.length) return;
        aktiv = true;
        const p = svgPunkt(svg, evt);
        pfad = `M ${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
        linie.setAttribute("d", pfad);
        // Der erste Punkt liegt meist direkt unter dem Startklick/-tipp -
        // ohne diese Prüfung hier würde er nie als erreicht zählen, da
        // "weiterzeichnen" erst ab der nächsten Bewegung greift.
        pruefeTreffer(p);
      });
      svg.addEventListener("pointermove", weiterzeichnen);
      window.addEventListener("pointerup", () => {
        aktiv = false;
      });
    });
  }

  function initZeichenfelder() {
    document.querySelectorAll("[data-zeichenfeld]").forEach((wrapper) => {
      const canvas = wrapper.querySelector("canvas");
      const form = wrapper.closest("form");
      const hiddenInput = wrapper.querySelector('input[name="zeichnung_daten"]');
      const entfernenInput = wrapper.querySelector('input[name="zeichnung_entfernen"]');
      const loeschenBtn = wrapper.querySelector("[data-zeichenfeld-loeschen]");
      const bestehendesBild = wrapper.querySelector("[data-zeichenfeld-bestehend]");
      if (!canvas || !form) return;
      const ctx = canvas.getContext("2d");
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.lineWidth = 3;
      ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--ink").trim() || "#1b1f1c";
      let zeichnet = false;
      let hatInhalt = false;

      function position(evt) {
        const rect = canvas.getBoundingClientRect();
        const quelle = evt.touches ? evt.touches[0] : evt;
        return {
          x: ((quelle.clientX - rect.left) / rect.width) * canvas.width,
          y: ((quelle.clientY - rect.top) / rect.height) * canvas.height,
        };
      }

      canvas.addEventListener("pointerdown", (evt) => {
        zeichnet = true;
        const p = position(evt);
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        if (bestehendesBild) bestehendesBild.style.display = "none";
      });
      canvas.addEventListener("pointermove", (evt) => {
        if (!zeichnet) return;
        const p = position(evt);
        ctx.lineTo(p.x, p.y);
        ctx.stroke();
        hatInhalt = true;
      });
      window.addEventListener("pointerup", () => {
        zeichnet = false;
      });

      if (loeschenBtn) {
        loeschenBtn.addEventListener("click", () => {
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          hatInhalt = false;
          if (entfernenInput) entfernenInput.value = "true";
          if (bestehendesBild) bestehendesBild.style.display = "none";
        });
      }

      form.addEventListener("submit", () => {
        if (hatInhalt) {
          hiddenInput.value = canvas.toDataURL("image/png");
          if (entfernenInput) entfernenInput.value = "";
        }
      });
    });
  }

  /*
   * Körper-Scan: bewusst eine lineare Liste antippbarer Körperregionen statt
   * des Verbinde-die-Punkte-Widgets der Atemübung - ein Körper-Scan bedeutet
   * nacheinander in Regionen hineinzuspüren, nicht eine Linie zwischen
   * abstrakten Punkten zu ziehen. Jede Region wird erst nach der vorigen
   * klickbar (serverseitig/client vorbereitet über [disabled]); ein Klick
   * auf "Halten"-Regionen zählt erst sinnvoll herunter, dann automatisch
   * weiter zur nächsten Region.
   */
  function initKoerperscan() {
    document.querySelectorAll("[data-koerperscan]").forEach((wrapper) => {
      const zonen = [...wrapper.querySelectorAll("[data-koerperscan-zone]")];
      const hiddenInput = wrapper.querySelector('input[name="koerperscan_erledigt"]');
      if (!hiddenInput || !zonen.length || hiddenInput.value === "true") return;

      let index = 0;
      let gesperrtBisMs = 0;

      function markiereAktiv() {
        zonen.forEach((z, i) => z.classList.toggle("koerperscan-zone--aktiv", i === index));
      }
      markiereAktiv();

      function haltenCountdown(zone, sekunden, weiter) {
        gesperrtBisMs = Date.now() + sekunden * 1000;
        const status = zone.querySelector("[data-koerperscan-status]");
        let verbleibend = sekunden;
        status.textContent = String(verbleibend);
        const intervall = setInterval(() => {
          verbleibend -= 1;
          if (verbleibend <= 0) {
            clearInterval(intervall);
            weiter();
            return;
          }
          status.textContent = String(verbleibend);
        }, 1000);
      }

      zonen.forEach((zone, i) => {
        zone.addEventListener("click", () => {
          if (i !== index || Date.now() < gesperrtBisMs) return;
          const sekunden = parseFloat(zone.dataset.halten || "0");
          const abschliessen = () => {
            zone.classList.remove("koerperscan-zone--aktiv");
            zone.classList.add("koerperscan-zone--erledigt");
            zone.querySelector("[data-koerperscan-status]").textContent = "✓";
            zone.disabled = true;
            index += 1;
            if (index >= zonen.length) {
              hiddenInput.value = "true";
            } else {
              zonen[index].disabled = false;
              markiereAktiv();
            }
          };
          if (sekunden > 0) {
            haltenCountdown(zone, sekunden, abschliessen);
          } else {
            abschliessen();
          }
        });
      });
    });
  }

  function initWortDesTages() {
    document.querySelectorAll("[data-wort-des-tages]").forEach((wrapper) => {
      const hiddenInput = wrapper.querySelector('input[name="wort_des_tages"]');
      const chips = [...wrapper.querySelectorAll("[data-wort-chip]")];
      if (!hiddenInput) return;
      function markiere() {
        chips.forEach((c) => c.classList.toggle("wort-chip--aktiv", c.dataset.wortChip === hiddenInput.value));
      }
      markiere();
      chips.forEach((chip) => {
        chip.addEventListener("click", () => {
          hiddenInput.value = hiddenInput.value === chip.dataset.wortChip ? "" : chip.dataset.wortChip;
          markiere();
        });
      });
    });
  }

  function initStaerkenKarte() {
    document.querySelectorAll("[data-staerken-karte]").forEach((details) => {
      const hiddenInput = details.querySelector('input[name="staerken_karte_erledigt"]');
      if (!hiddenInput) return;
      details.addEventListener("toggle", () => {
        if (details.open) hiddenInput.value = "true";
      });
    });
  }

  function initSorgenLoslassen() {
    document.querySelectorAll("[data-sorgen-loslassen]").forEach((wrapper) => {
      const textarea = wrapper.querySelector("textarea");
      const hiddenInput = wrapper.querySelector('input[name="sorgen_los_erledigt"]');
      const button = wrapper.querySelector("[data-sorgen-loslassen-button]");
      if (!textarea || !hiddenInput || !button) return;
      button.addEventListener("click", () => {
        if (!textarea.value.trim()) return;
        wrapper.classList.add("sorgen-loslassen--animiert");
        hiddenInput.value = "true";
        window.setTimeout(() => {
          textarea.value = "";
          wrapper.classList.remove("sorgen-loslassen--animiert");
        }, 500);
      });
    });
  }

  function initMandala() {
    const FARBEN = ["", "var(--mandala-1)", "var(--mandala-2)", "var(--mandala-3)", "var(--mandala-4)"];
    document.querySelectorAll("[data-mandala]").forEach((wrapper) => {
      const hiddenInput = wrapper.querySelector('input[name="mandala_erledigt"]');
      const segmente = [...wrapper.querySelectorAll("[data-mandala-segment]")];
      if (!hiddenInput) return;
      segmente.forEach((segment) => {
        let index = 0;
        segment.addEventListener("click", () => {
          index = (index + 1) % FARBEN.length;
          segment.setAttribute("fill", FARBEN[index] || "none");
          hiddenInput.value = "true";
        });
      });
    });
  }

  function initEnergieBatterien() {
    document.querySelectorAll("[data-energie-batterie]").forEach((wrapper) => {
      const hiddenInput = wrapper.querySelector('input[name="energie_level"]');
      const segmente = [...wrapper.querySelectorAll("[data-energie-segment]")];
      if (!hiddenInput) return;

      function anzeigen(level) {
        segmente.forEach((s, i) => s.classList.toggle("energie-segment--voll", i < level));
      }
      anzeigen(parseInt(hiddenInput.value, 10) || 0);

      segmente.forEach((segment, i) => {
        segment.addEventListener("click", () => {
          const neu = i + 1;
          const aktuellerLevel = parseInt(hiddenInput.value, 10) || 0;
          // Erneutes Antippen des obersten aktiven Segments leert die Auswahl
          // wieder - so bleibt "keine Angabe" jederzeit erreichbar.
          hiddenInput.value = aktuellerLevel === neu ? "" : String(neu);
          anzeigen(parseInt(hiddenInput.value, 10) || 0);
        });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initPunkteUebungen();
    initZeichenfelder();
    initEnergieBatterien();
    initKoerperscan();
    initWortDesTages();
    initStaerkenKarte();
    initSorgenLoslassen();
    initMandala();
  });
})();
