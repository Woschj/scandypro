/*
 * Interaktive Elemente im 5-Minuten-Tagebuch (siehe app/templates/wohlbefinden/
 * uebersicht.html, app/routers/wohlbefinden.py, app/core/tagesuebungen.py).
 * Rework nach tasks/ganzheitliche-verbesserungen/VB-018.md: statt vieler
 * Einzellösungen eine kleine Zahl wiederverwendbarer Interaktions-Primitive
 * - jede Übungsart nutzt eines davon: Spur ziehen (Atemübung), Leinwand
 * (Zeichnung/Mandala), Zone mit Halten-Timer (Körperscan), Karte umdrehen
 * (Stärken-Karte/Ruhe-Ort/Mini-Ziel), Karten wegwischen (Sorgen
 * loslassen/Erdung), Waage (Gedanken-Waage), Wort-Rad, Foto-Rahmen.
 *
 * Alle bewusst ohne serverseitige Zwischenspeicherung während der
 * Interaktion selbst - das Ergebnis landet erst beim regulären
 * Formular-Submit in den bestehenden Feldern. Reine Teilnahme statt
 * Bewertung (siehe CLAUDE.md §24/25): kein "richtig/falsch", meist zählt
 * nur der Abschluss-Zeitpunkt, nicht ein Ergebnis.
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
   * Körper-Scan: eine schematische Körpersilhouette (SVG) statt einer
   * abstrakten Button-Liste - Regionen leuchten beim Antippen auf und
   * zeigen bei "Halten"-Regionen einen kurzen Countdown, bevor die nächste
   * Region antippbar wird (siehe VB-018.md, Primitiv "Zone mit
   * Halten-Timer"). Visuell verortet statt als Liste, damit ein
   * Körper-Scan sich auch wie einer anfühlt.
   */
  function initKoerperscan() {
    document.querySelectorAll("[data-koerperscan]").forEach((wrapper) => {
      const zonen = [...wrapper.querySelectorAll("[data-koerperscan-zone]")];
      const hinweis = wrapper.querySelector("[data-koerperscan-hinweis]");
      const hiddenInput = wrapper.querySelector('input[name="koerperscan_erledigt"]');
      if (!hiddenInput || !zonen.length) return;

      let index = 0;
      let gesperrtBisMs = 0;

      if (hiddenInput.value === "true") {
        zonen.forEach((z) => z.classList.add("koerperscan-zone--erledigt"));
        if (hinweis) hinweis.textContent = "Schon gemacht - danke fürs Hineinspüren.";
        return;
      }

      function markiereAktiv() {
        zonen.forEach((z, i) => z.classList.toggle("koerperscan-zone--aktiv", i === index));
        if (hinweis) hinweis.textContent = zonen[index].dataset.hinweis || "Tippe auf die markierte Region.";
      }
      markiereAktiv();

      function haltenCountdown(zone, sekunden, weiter) {
        gesperrtBisMs = Date.now() + sekunden * 1000;
        let verbleibend = sekunden;
        if (hinweis) hinweis.textContent = `Halten … noch ${verbleibend}`;
        const intervall = setInterval(() => {
          verbleibend -= 1;
          if (verbleibend <= 0) {
            clearInterval(intervall);
            weiter();
            return;
          }
          if (hinweis) hinweis.textContent = `Halten … noch ${verbleibend}`;
        }, 1000);
      }

      zonen.forEach((zone, i) => {
        zone.classList.add("koerperscan-zone--gesperrt");
        zone.addEventListener("click", () => {
          if (i !== index || Date.now() < gesperrtBisMs) return;
          const sekunden = parseFloat(zone.dataset.halten || "0");
          const abschliessen = () => {
            zone.classList.remove("koerperscan-zone--aktiv");
            zone.classList.add("koerperscan-zone--erledigt");
            index += 1;
            if (index >= zonen.length) {
              hiddenInput.value = "true";
              if (hinweis) hinweis.textContent = "Geschafft - schön, dass du dir die Zeit genommen hast.";
            } else {
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

  /*
   * Wort-Rad: ein fächerartiges Feld sanfter Wörter statt einer starren
   * Button-Wolke - das gewählte Wort hebt sich sichtbar hervor (siehe
   * VB-018.md, Primitiv "Wort-Rad").
   */
  function initWortRad() {
    document.querySelectorAll("[data-wort-rad]").forEach((wrapper) => {
      const hiddenInput = wrapper.querySelector('input[name="wort_des_tages"]');
      const chips = [...wrapper.querySelectorAll("[data-wort-chip]")];
      if (!hiddenInput) return;
      function markiere() {
        chips.forEach((c) => c.classList.toggle("wort-rad-wort--aktiv", c.dataset.wortChip === hiddenInput.value));
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

  /*
   * Karte umdrehen: echte CSS-3D-Flip-Animation statt <details>-Akkordeon
   * (siehe VB-018.md, Primitiv "Karte umdrehen") - für Stärken-Karte,
   * Ruhe-Ort-Visualisierung und Mini-Ziel. Öffnet sich bewusst nur einmal
   * (kein Zurückklappen nötig, die Rückseite enthält die eigentlichen
   * Eingabefelder).
   */
  function initFlipKarten() {
    document.querySelectorAll("[data-flip-karte]").forEach((karte) => {
      if (karte.classList.contains("flip-karte--offen")) return;
      const vorne = karte.querySelector(".flip-karte-vorne");
      const feldName = karte.dataset.flipErledigtFeld;
      const hiddenInput = feldName ? karte.querySelector(`input[name="${feldName}"]`) : null;
      if (!vorne) return;
      vorne.addEventListener(
        "click",
        () => {
          karte.classList.add("flip-karte--offen");
          if (hiddenInput) hiddenInput.value = "true";
          const erstesFeld = karte.querySelector(".flip-karte-hinten input, .flip-karte-hinten textarea");
          if (erstesFeld) window.setTimeout(() => erstesFeld.focus(), 350);
        },
        { once: true }
      );
    });
  }

  /*
   * Karten wegwischen: generisches Primitiv für Sorgen-loslassen (eine
   * Karte) und Erdung 5-4-3-2-1 (fünf nacheinander erscheinende Karten,
   * eine pro Sinn) - echte Pointer-Drag-Wischgeste statt eines simplen
   * Buttons (siehe VB-018.md, Primitiv "Karten wegwischen"). Der Inhalt
   * der Sorgen-Karte wird bewusst nirgends gespeichert - das Loslassen
   * selbst ist der Zweck.
   */
  function initWischKarten() {
    document.querySelectorAll("[data-wisch-stapel]").forEach((stapel) => {
      const karten = [...stapel.querySelectorAll("[data-wisch-karte]")];
      const hiddenInput = stapel.querySelector("[data-wisch-erledigt]");
      const fertigText = stapel.querySelector("[data-wisch-fertig]");
      if (!karten.length) return;

      let anzahlWeg = 0;
      const SCHWELLE_PX = 90;

      // Manche Stapel (Erdung 5-4-3-2-1) speichern pro Karte ein eigenes
      // Feld (data-wisch-feld = Formularfeldname), andere (Sorgen
      // loslassen) nur ein gemeinsames Stapel-Feld, sobald alle weg sind.
      function abschliessenKarte(karte) {
        const eigenesFeldName = karte.dataset.wischFeld;
        if (eigenesFeldName) {
          const eigenesFeld = stapel.querySelector(`input[name="${eigenesFeldName}"]`);
          if (eigenesFeld) eigenesFeld.value = "true";
        }
        anzahlWeg += 1;
        if (anzahlWeg >= karten.length) {
          if (hiddenInput) hiddenInput.value = "true";
          if (fertigText) fertigText.style.display = "block";
        }
      }

      karten.forEach((karte) => {
        let startX = 0;
        let deltaX = 0;
        let ziehtGerade = false;

        karte.addEventListener("pointerdown", (evt) => {
          if (evt.target.closest("textarea, input")) return;
          ziehtGerade = true;
          startX = evt.clientX;
          karte.setPointerCapture(evt.pointerId);
        });
        karte.addEventListener("pointermove", (evt) => {
          if (!ziehtGerade) return;
          deltaX = evt.clientX - startX;
          karte.style.transform = `translateX(${deltaX}px) rotate(${deltaX / 18}deg)`;
        });
        function loslassen() {
          if (!ziehtGerade) return;
          ziehtGerade = false;
          if (Math.abs(deltaX) > SCHWELLE_PX) {
            karte.style.transform = `translateX(${deltaX > 0 ? 400 : -400}px) rotate(${deltaX > 0 ? 20 : -20}deg)`;
            karte.classList.add("wisch-karte--verlassen");
            const textarea = karte.querySelector("textarea");
            if (textarea) textarea.value = "";
            window.setTimeout(() => abschliessenKarte(karte), 50);
          } else {
            karte.style.transform = "";
          }
          deltaX = 0;
        }
        karte.addEventListener("pointerup", loslassen);
        karte.addEventListener("pointercancel", loslassen);

        // Tastatur-/Klick-Alternative zum Wischen (Barrierefreiheit).
        const button = karte.querySelector("[data-wisch-button]");
        if (button) {
          button.addEventListener("click", () => {
            karte.style.transform = "translateX(400px) rotate(20deg)";
            karte.classList.add("wisch-karte--verlassen");
            const textarea = karte.querySelector("textarea");
            if (textarea) textarea.value = "";
            window.setTimeout(() => abschliessenKarte(karte), 50);
          });
        }
      });
    });
  }

  /*
   * Gedanken-Waage: ein sichtbares Zwei-Schalen-Element, das sich neigt,
   * sobald beide Felder Text enthalten - macht die Metapher tatsächlich
   * sichtbar statt nur im Namen (siehe VB-018.md, Primitiv "Waage").
   */
  function initGedankenWaage() {
    document.querySelectorAll("[data-gedanken-waage]").forEach((wrapper) => {
      const belastend = wrapper.querySelector('textarea[name="gedanke_belastend"]');
      const ausgewogen = wrapper.querySelector('textarea[name="gedanke_ausgewogen"]');
      const balken = wrapper.querySelector("[data-waage-balken]");
      const schaleLinks = wrapper.querySelector("[data-waage-schale-links]");
      const schaleRechts = wrapper.querySelector("[data-waage-schale-rechts]");
      if (!belastend || !ausgewogen || !balken) return;

      function aktualisieren() {
        const a = belastend.value.trim().length;
        const b = ausgewogen.value.trim().length;
        const summe = a + b;
        // Neigt sich Richtung "ausgewogen", sobald dort mehr steht - bewusst
        // keine Aussage über "richtig/falsch", nur ob beide Seiten gefüllt
        // wirken.
        const neigungGrad = summe === 0 ? 0 : Math.max(-12, Math.min(12, ((b - a) / summe) * 12));
        balken.style.transform = `rotate(${neigungGrad}deg)`;
        if (schaleLinks) schaleLinks.style.transform = `translateY(${neigungGrad * -1.4}px)`;
        if (schaleRechts) schaleRechts.style.transform = `translateY(${neigungGrad * 1.4}px)`;
      }
      belastend.addEventListener("input", aktualisieren);
      ausgewogen.addEventListener("input", aktualisieren);
      aktualisieren();
    });
  }

  /*
   * Mandala als Leinwand: ein feines Mandala-Führungsmuster liegt als
   * SVG-Overlay hinter dem Canvas, frei übermalt wie bei der Zeichnung
   * (siehe VB-018.md, Primitiv "Leinwand") statt einzelner Klick-Segmente.
   */
  function initMandalaCanvas() {
    document.querySelectorAll("[data-mandala]").forEach((wrapper) => {
      const canvas = wrapper.querySelector("canvas");
      const hiddenInput = wrapper.querySelector('input[name="mandala_erledigt"]');
      const farbButtons = [...wrapper.querySelectorAll("[data-mandala-farbe]")];
      if (!canvas || !hiddenInput) return;
      const ctx = canvas.getContext("2d");
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.lineWidth = 6;
      let aktuelleFarbe = farbButtons[0] ? farbButtons[0].dataset.mandalaFarbe : "#e8a33d";
      ctx.strokeStyle = aktuelleFarbe;
      let zeichnet = false;

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
      });
      canvas.addEventListener("pointermove", (evt) => {
        if (!zeichnet) return;
        const p = position(evt);
        ctx.lineTo(p.x, p.y);
        ctx.stroke();
        hiddenInput.value = "true";
      });
      window.addEventListener("pointerup", () => {
        zeichnet = false;
      });

      farbButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
          aktuelleFarbe = btn.dataset.mandalaFarbe;
          ctx.strokeStyle = aktuelleFarbe;
          farbButtons.forEach((b) => b.classList.toggle("mandala-farbe--aktiv", b === btn));
        });
      });
      if (farbButtons[0]) farbButtons[0].classList.add("mandala-farbe--aktiv");
    });
  }

  /*
   * Foto-Rahmen: sofortige Sofortbild-Vorschau nach der Dateiauswahl statt
   * eines nackten Datei-Inputs (siehe VB-018.md, Primitiv "Foto-Rahmen").
   */
  function initFotoRahmen() {
    document.querySelectorAll("[data-foto-rahmen]").forEach((wrapper) => {
      const input = wrapper.querySelector('input[type="file"]');
      const bild = wrapper.querySelector("[data-foto-rahmen-bild]");
      const leer = wrapper.querySelector("[data-foto-rahmen-leer]");
      if (!input || !bild) return;
      input.addEventListener("change", () => {
        const datei = input.files && input.files[0];
        if (!datei) return;
        bild.src = URL.createObjectURL(datei);
        bild.style.display = "block";
        if (leer) leer.style.display = "none";
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
    initWortRad();
    initFlipKarten();
    initWischKarten();
    initGedankenWaage();
    initMandalaCanvas();
    initFotoRahmen();
  });
})();
