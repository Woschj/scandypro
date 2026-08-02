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

  function initAtemuebungen() {
    document.querySelectorAll("[data-atemuebung]").forEach((wrapper) => {
      const svg = wrapper.querySelector("svg");
      const linie = wrapper.querySelector("[data-linie]");
      const kreise = [...wrapper.querySelectorAll("[data-punkt]")];
      const hinweis = wrapper.querySelector("[data-atemuebung-hinweis]");
      const hiddenInput = wrapper.querySelector('input[name="atemuebung_erledigt"]');
      if (!svg || !hiddenInput) return;

      const RADIUS_TREFFER = 22;
      let naechsterIndex = 0;
      let pfad = "";
      let aktiv = false;

      if (hiddenInput.value === "true") {
        kreise.forEach((k) => k.classList.add("atemuebung-punkt--erreicht"));
        naechsterIndex = kreise.length;
        if (hinweis) hinweis.textContent = "Schon gemacht - danke fürs Innehalten.";
      }

      function abstand(a, b) {
        return Math.hypot(a.x - b.x, a.y - b.y);
      }

      function pruefeTreffer(p) {
        if (naechsterIndex >= kreise.length) return;
        const zielKreis = kreise[naechsterIndex];
        const ziel = { x: parseFloat(zielKreis.getAttribute("cx")), y: parseFloat(zielKreis.getAttribute("cy")) };
        if (abstand(p, ziel) <= RADIUS_TREFFER) {
          zielKreis.classList.add("atemuebung-punkt--erreicht");
          naechsterIndex += 1;
          if (naechsterIndex >= kreise.length) {
            hiddenInput.value = "true";
            if (hinweis) hinweis.textContent = "Geschafft - schön, dass du dir die Pause genommen hast.";
            aktiv = false;
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
    initAtemuebungen();
    initZeichenfelder();
    initEnergieBatterien();
  });
})();
