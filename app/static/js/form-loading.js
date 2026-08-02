/*
 * Globaler Lade-/Disabled-Zustand für Formular-Submits (siehe
 * tasks/uiux-audit/UI-007.md): verhindert Doppel-Submits (z.B. doppelt
 * angelegte Karten/Boards) und gibt sichtbares Feedback, dass eine Aktion
 * unterwegs ist - relevant, weil die App überwiegend klassische
 * Full-Page-POST-Formulare ohne HTMX/AJAX nutzt.
 *
 * e.defaultPrevented wird geprüft, damit Formulare, die von anderem Code
 * abgefangen werden (confirm.js vor Bestätigung, upload-check.js bei zu
 * großer Datei, die fetch()-basierte Unteraufgaben-Umschaltung in
 * kanban.js), NICHT dauerhaft deaktiviert werden - dort läuft die Seite
 * nicht weg, ein für immer deaktivierter Button wäre ein Bug.
 */
(function () {
  document.addEventListener("submit", (e) => {
    if (e.defaultPrevented) return;
    const formular = e.target;
    if (!(formular instanceof HTMLFormElement)) return;

    const buttons = formular.querySelectorAll(
      'button[type="submit"], button:not([type])'
    );
    buttons.forEach((btn) => {
      btn.disabled = true;
      btn.classList.add("btn--laedt");
      if (!btn.dataset.ladetext) {
        btn.dataset.ladetext = btn.textContent;
      }
    });
  });
})();
