/*
 * "Mein Tag": ein Regler pro Feld (Stimmung/Energie) mit genau einer
 * großen Emoji-Vorschau statt einer Reihe aus 10 Buttons - bewusst
 * reduziert, damit die Seite auch mit zwei Reglern pro Tag nicht
 * überladen wirkt (Zielgruppe: möglichst wenig kognitive Last).
 */
(function () {
  function init(root) {
    const dataScript = root.querySelector("#wochendaten-data");
    const daten = JSON.parse(dataScript.textContent);
    const datenByDatum = Object.fromEntries(daten.map((tag) => [tag.datum, tag]));
    const emojiListen = JSON.parse(root.querySelector("#emoji-daten").textContent);
    const toast = root.querySelector("#zeitlinie-toast");
    const kommentarPanel = root.querySelector("#kommentar-panel");
    const kommentarTitel = root.querySelector("#kommentar-titel");
    const kommentarText = root.querySelector("#kommentar-text");
    const kommentarSpeichern = root.querySelector("#kommentar-speichern");
    const kommentarSchliessen = root.querySelector("#kommentar-schliessen");

    let aktivesDatum = null;
    let zeigeToastTimeout = null;

    function zeigeToast(text) {
      toast.textContent = text;
      toast.classList.add("sichtbar");
      clearTimeout(zeigeToastTimeout);
      zeigeToastTimeout = setTimeout(() => toast.classList.remove("sichtbar"), 1400);
    }

    async function speichereTag(datum) {
      const tag = datenByDatum[datum];
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

    root.querySelectorAll(".emoji-slider").forEach((slider) => {
      const tagEintrag = slider.closest("[data-datum]");
      const datum = tagEintrag.dataset.datum;
      const feld = slider.dataset.feld;
      const preview = tagEintrag.querySelector(`[data-preview="${feld}"]`);
      const emojis = emojiListen[feld];

      slider.addEventListener("input", () => {
        const wert = parseInt(slider.value, 10);
        preview.textContent = emojis[wert - 1];
      });
      slider.addEventListener("change", () => {
        const wert = parseInt(slider.value, 10);
        datenByDatum[datum][feld] = wert;
        datenByDatum[datum].gesetzt = true;
        speichereTag(datum);
      });
    });

    function aktualisierePin(datum) {
      const btn = root.querySelector(`[data-kommentar-btn="${datum}"]`);
      const hatKommentar = !!(datenByDatum[datum].kommentar && datenByDatum[datum].kommentar.trim());
      btn.classList.toggle("tag-kommentar-btn--gesetzt", hatKommentar);
      btn.title = hatKommentar
        ? `Kommentar: ${datenByDatum[datum].kommentar}`
        : "Kommentar hinzufügen";
    }

    function oeffneKommentar(datum) {
      aktivesDatum = datum;
      const tag = datenByDatum[datum];
      kommentarTitel.textContent = "Kommentar – " + tag.label;
      kommentarText.value = tag.kommentar || "";
      kommentarPanel.classList.add("sichtbar");
      kommentarText.focus();
    }

    root.querySelectorAll("[data-kommentar-btn]").forEach((btn) => {
      btn.addEventListener("click", () => oeffneKommentar(btn.dataset.kommentarBtn));
    });

    kommentarSchliessen.addEventListener("click", () => kommentarPanel.classList.remove("sichtbar"));
    kommentarSpeichern.addEventListener("click", async () => {
      if (aktivesDatum === null) return;
      const tag = datenByDatum[aktivesDatum];
      tag.kommentar = kommentarText.value;
      await fetch("/wohlbefinden/tag/kommentar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ datum: tag.datum, kommentar: tag.kommentar }),
      });
      aktualisierePin(aktivesDatum);
      kommentarPanel.classList.remove("sichtbar");
      zeigeToast("Kommentar gespeichert ✓");
    });
  }

  document.querySelectorAll(".tage-widget").forEach(init);
})();
