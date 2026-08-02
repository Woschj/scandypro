/*
 * "Mein Tag": kompakte Einzeltag-Ansicht - ein Regler-Paar für genau
 * einen Tag (Stimmung/Energie), Navigation wechselt per Seitenaufruf
 * zwischen Tagen (siehe app/routers/wohlbefinden.py:_tag_kontext).
 */
(function () {
  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  function init(root) {
    const tagDaten = JSON.parse(root.querySelector("#tag-data").textContent);
    const emojiListen = JSON.parse(root.querySelector("#emoji-daten").textContent);
    const toast = root.querySelector("#zeitlinie-toast");
    const kommentarPanel = root.querySelector("#kommentar-panel");
    const kommentarTitel = root.querySelector("#kommentar-titel");
    const kommentarText = root.querySelector("#kommentar-text");
    const kommentarSpeichern = root.querySelector("#kommentar-speichern");
    const kommentarSchliessen = root.querySelector("#kommentar-schliessen");

    let zeigeToastTimeout = null;

    function zeigeToast(text, dringlich) {
      // aria-live dynamisch umschalten: Erfolg "polite" (unterbricht
      // Screenreader nicht), Fehler "assertive" (Handlungsbedarf, siehe
      // tasks/uiux-audit/UI-008.md).
      toast.setAttribute("aria-live", dringlich ? "assertive" : "polite");
      toast.textContent = text;
      toast.classList.add("sichtbar");
      clearTimeout(zeigeToastTimeout);
      zeigeToastTimeout = setTimeout(() => toast.classList.remove("sichtbar"), 1400);
    }

    async function speichereTag() {
      try {
        await fetch("/wohlbefinden/tag", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
          body: JSON.stringify({
            datum: tagDaten.datum,
            stimmung: tagDaten.stimmung,
            belastbarkeit: tagDaten.belastbarkeit,
          }),
        });
        zeigeToast("Gespeichert ✓");
      } catch (err) {
        zeigeToast("Hat nicht geklappt – versuch's gleich nochmal", true);
      }
    }

    root.querySelectorAll(".emoji-slider").forEach((slider) => {
      const feld = slider.dataset.feld;
      const preview = root.querySelector(`[data-preview="${feld}"]`);
      const emojis = emojiListen[feld];

      slider.addEventListener("input", () => {
        const wert = parseInt(slider.value, 10);
        preview.textContent = emojis[wert - 1];
      });
      slider.addEventListener("change", () => {
        tagDaten[feld] = parseInt(slider.value, 10);
        tagDaten.gesetzt = true;
        speichereTag();
      });
    });

    function aktualisierePin() {
      const btn = root.querySelector("[data-kommentar-btn]");
      const hatKommentar = !!(tagDaten.kommentar && tagDaten.kommentar.trim());
      btn.classList.toggle("tag-kommentar-btn--gesetzt", hatKommentar);
      btn.title = hatKommentar ? `Kommentar: ${tagDaten.kommentar}` : "Kommentar hinzufügen";
    }

    function oeffneKommentar() {
      kommentarTitel.textContent = "Kommentar – " + tagDaten.label;
      kommentarText.value = tagDaten.kommentar || "";
      kommentarPanel.classList.add("sichtbar");
      kommentarText.focus();
    }

    root.querySelector("[data-kommentar-btn]").addEventListener("click", oeffneKommentar);

    kommentarSchliessen.addEventListener("click", () => kommentarPanel.classList.remove("sichtbar"));
    kommentarSpeichern.addEventListener("click", async () => {
      tagDaten.kommentar = kommentarText.value;
      await fetch("/wohlbefinden/tag/kommentar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
        body: JSON.stringify({ datum: tagDaten.datum, kommentar: tagDaten.kommentar }),
      });
      aktualisierePin();
      kommentarPanel.classList.remove("sichtbar");
      zeigeToast("Kommentar gespeichert ✓");
    });
  }

  document.querySelectorAll(".tage-widget").forEach(init);
})();
