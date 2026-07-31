/*
 * Interaktive Wohlbefinden-Zeitlinie.
 *
 * Rendert komplett aus den JSON-Daten (kein serverseitig vorgerendertes
 * SVG), damit die Koordinaten-Formeln nur an einer Stelle existieren und
 * Drag-Updates und Erstanzeige garantiert konsistent sind.
 */
(function () {
  const BREITE = 700;
  const HOEHE = 320;
  const PAD_LEFT = 46;
  const PAD_RIGHT = 20;
  const PAD_TOP = 60;
  const PAD_BOTTOM = 46;
  const PLOT_LEFT = PAD_LEFT;
  const PLOT_RIGHT = BREITE - PAD_RIGHT;
  const PLOT_TOP = PAD_TOP;
  const PLOT_BOTTOM = HOEHE - PAD_BOTTOM;
  const PLOT_WIDTH = PLOT_RIGHT - PLOT_LEFT;
  const PLOT_HEIGHT = PLOT_BOTTOM - PLOT_TOP;
  const SVG_NS = "http://www.w3.org/2000/svg";

  const SKALA_LABELS = { 1: "1 – niedrig", 2: "2", 3: "3 – mittel", 4: "4", 5: "5 – hoch" };

  function xFuerIndex(i) {
    return PLOT_LEFT + (i / 6) * PLOT_WIDTH;
  }
  function yFuerWert(w) {
    return PLOT_BOTTOM - ((w - 1) / 4) * PLOT_HEIGHT;
  }
  function wertFuerY(y) {
    const w = 1 + ((PLOT_BOTTOM - y) / PLOT_HEIGHT) * 4;
    return Math.min(5, Math.max(1, w));
  }
  function rundeAufHalbe(w) {
    return Math.round(w * 2) / 2;
  }
  function el(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    return node;
  }

  function init(root) {
    const svg = root.querySelector("#zeitlinie-svg");
    const dataScript = root.querySelector("#wochendaten-data");
    const daten = JSON.parse(dataScript.textContent);
    const toast = root.querySelector("#zeitlinie-toast");
    const kommentarPanel = root.querySelector("#kommentar-panel");
    const kommentarTitel = root.querySelector("#kommentar-titel");
    const kommentarText = root.querySelector("#kommentar-text");
    const kommentarSpeichern = root.querySelector("#kommentar-speichern");
    const kommentarSchliessen = root.querySelector("#kommentar-schliessen");

    let aktivenTagIndex = null;
    let zeigeToastTimeout = null;

    function svgYVon(clientY) {
      const rect = svg.getBoundingClientRect();
      const scale = HOEHE / rect.height;
      return (clientY - rect.top) * scale;
    }

    function zeigeToast(text) {
      toast.textContent = text;
      toast.classList.add("sichtbar");
      clearTimeout(zeigeToastTimeout);
      zeigeToastTimeout = setTimeout(() => toast.classList.remove("sichtbar"), 1400);
    }

    async function speichereTag(index) {
      const tag = daten[index];
      try {
        await fetch("/wohlbefinden/tag", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ datum: tag.datum, stimmung: tag.stimmung, belastbarkeit: tag.belastbarkeit }),
        });
        zeigeToast("Gespeichert ✓");
      } catch (err) {
        zeigeToast("Hat nicht geklappt – versuch's gleich nochmal");
      }
    }

    function pfadPunkte(serie) {
      return daten.map((tag, i) => `${xFuerIndex(i).toFixed(1)},${yFuerWert(tag[serie]).toFixed(1)}`).join(" ");
    }

    function aktualisierePfade() {
      svg.querySelector('[data-pfad="stimmung"]').setAttribute("points", pfadPunkte("stimmung"));
      svg.querySelector('[data-pfad="belastbarkeit"]').setAttribute("points", pfadPunkte("belastbarkeit"));
    }

    function aktualisierePin(index) {
      const gruppe = svg.querySelector(`[data-pin="${index}"]`);
      const hatKommentar = !!(daten[index].kommentar && daten[index].kommentar.trim());
      const kreis = gruppe.querySelector("circle");
      const titel = gruppe.querySelector("title");
      gruppe.classList.toggle("zeitlinie-pin--gesetzt", hatKommentar);
      kreis.setAttribute("fill", hatKommentar ? "var(--accent)" : "var(--bg-raised)");
      titel.textContent = hatKommentar
        ? `Kommentar (${daten[index].label}): ${daten[index].kommentar}`
        : `Kommentar zu ${daten[index].label} hinzufügen`;
    }

    function oeffneKommentar(index) {
      aktivenTagIndex = index;
      kommentarTitel.textContent = "Kommentar – " + daten[index].label;
      kommentarText.value = daten[index].kommentar || "";
      kommentarPanel.classList.add("sichtbar");
      kommentarText.focus();
    }

    kommentarSchliessen.addEventListener("click", () => kommentarPanel.classList.remove("sichtbar"));
    kommentarSpeichern.addEventListener("click", async () => {
      if (aktivenTagIndex === null) return;
      const tag = daten[aktivenTagIndex];
      tag.kommentar = kommentarText.value;
      await fetch("/wohlbefinden/tag/kommentar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ datum: tag.datum, kommentar: tag.kommentar }),
      });
      aktualisierePin(aktivenTagIndex);
      kommentarPanel.classList.remove("sichtbar");
      zeigeToast("Kommentar gespeichert ✓");
    });

    // Gridlines + Y-Achsen-Beschriftung
    for (let w = 1; w <= 5; w++) {
      const y = yFuerWert(w);
      svg.appendChild(el("line", { x1: PLOT_LEFT, y1: y, x2: PLOT_RIGHT, y2: y, stroke: "var(--line)", "stroke-width": 1 }));
      const label = el("text", { x: PLOT_LEFT - 8, y: y + 4, "text-anchor": "end", class: "zeitlinie-achse" });
      label.textContent = w;
      label.setAttribute("title", SKALA_LABELS[w]);
      svg.appendChild(label);
    }

    // Kopfzeile über der Pin-Reihe, damit klar ist, wofür die Symbole da sind
    const pinKopf = el("text", { x: PLOT_LEFT, y: 16, class: "zeitlinie-achse zeitlinie-pin-kopf" });
    pinKopf.textContent = "💬 Kommentar je Tag (antippen)";
    svg.appendChild(pinKopf);

    // Pfade (zuerst, damit Punkte optisch darüber liegen)
    svg.appendChild(el("polyline", { "data-pfad": "belastbarkeit", fill: "none", stroke: "var(--accent)", "stroke-width": 3, "stroke-linecap": "round", opacity: 0.85 }));
    svg.appendChild(el("polyline", { "data-pfad": "stimmung", fill: "none", stroke: "var(--brand)", "stroke-width": 3, "stroke-linecap": "round" }));

    daten.forEach((tag, i) => {
      const x = xFuerIndex(i);

      // Tageslabel (X-Achse)
      const label = el("text", { x, y: PLOT_BOTTOM + 22, "text-anchor": "middle", class: "zeitlinie-tag-label" });
      label.textContent = tag.label;
      svg.appendChild(label);

      // Vertikale Führungslinie
      svg.appendChild(el("line", { x1: x, y1: PLOT_TOP, x2: x, y2: PLOT_BOTTOM, stroke: "var(--line)", "stroke-width": 1, opacity: 0.5 }));

      // Kommentar-Pin oberhalb des Plots: Kreis mit Sprechblasen-Symbol,
      // deutlich größer als die reinen Datenpunkte und mit Tooltip, damit
      // die Funktion auch ohne Legende erkennbar ist.
      const pinY = 34;
      const pinGruppe = el("g", { "data-pin": i, class: "zeitlinie-pin" });
      pinGruppe.appendChild(el("circle", { cx: x, cy: pinY, r: 15, stroke: "var(--ink-soft)", "stroke-width": 1.5, fill: "var(--bg-raised)" }));
      const pinIcon = el("text", { x, y: pinY + 5, "text-anchor": "middle", class: "zeitlinie-pin-icon" });
      pinIcon.textContent = "💬";
      pinGruppe.appendChild(pinIcon);
      const titel = el("title", {});
      pinGruppe.appendChild(titel);
      pinGruppe.appendChild(el("line", { x1: x, y1: pinY + 13, x2: x, y2: PLOT_TOP, stroke: "var(--line)", "stroke-width": 1, "stroke-dasharray": "2 2" }));
      pinGruppe.addEventListener("click", () => oeffneKommentar(i));
      svg.appendChild(pinGruppe);

      ["belastbarkeit", "stimmung"].forEach((serie) => {
        const kreis = el("circle", {
          cx: x,
          cy: yFuerWert(tag[serie]),
          r: 11,
          "data-index": i,
          "data-serie": serie,
          class: "zeitlinie-punkt zeitlinie-punkt--" + serie + (tag.gesetzt ? "" : " zeitlinie-punkt--unset"),
        });
        kreis.addEventListener("pointerdown", (e) => startDrag(e, kreis, i, serie));
        svg.appendChild(kreis);
      });
    });
    aktualisierePfade();
    daten.forEach((_, i) => aktualisierePin(i));

    function startDrag(e, kreis, index, serie) {
      e.preventDefault();
      kreis.setPointerCapture(e.pointerId);
      kreis.classList.add("zeitlinie-punkt--aktiv");

      function onMove(ev) {
        const y = Math.min(PLOT_BOTTOM, Math.max(PLOT_TOP, svgYVon(ev.clientY)));
        const wert = rundeAufHalbe(wertFuerY(y));
        daten[index][serie] = wert;
        daten[index].gesetzt = true;
        kreis.setAttribute("cy", yFuerWert(wert));
        kreis.classList.remove("zeitlinie-punkt--unset");
        aktualisierePfade();
      }

      function onUp(ev) {
        onMove(ev);
        kreis.releasePointerCapture(e.pointerId);
        kreis.classList.remove("zeitlinie-punkt--aktiv");
        kreis.removeEventListener("pointermove", onMove);
        kreis.removeEventListener("pointerup", onUp);
        speichereTag(index);
      }

      kreis.addEventListener("pointermove", onMove);
      kreis.addEventListener("pointerup", onUp);
    }
  }

  document.querySelectorAll(".zeitlinie-widget").forEach(init);
})();
