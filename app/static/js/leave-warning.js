/*
 * Warnung vor Datenverlust beim Verlassen langer Formulare (siehe
 * tasks/uiux-audit/UI-021.md) - betrifft nur Formulare mit
 * data-warn-on-leave (Wochenbericht, neue Bewerbung). Warnt nur, wenn
 * tatsächlich etwas verändert wurde und das Formular nicht gerade
 * abgeschickt wird.
 */
(function () {
  let veraendert = false;

  document.querySelectorAll("form[data-warn-on-leave]").forEach((formular) => {
    formular.addEventListener("input", () => {
      veraendert = true;
    });
    formular.addEventListener("submit", () => {
      veraendert = false;
    });
  });

  window.addEventListener("beforeunload", (e) => {
    if (!veraendert) return;
    e.preventDefault();
    e.returnValue = "";
  });
})();
