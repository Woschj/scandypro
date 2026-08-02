/*
 * Einheitliches, gebrandetes Bestätigungs-Modal für destruktive Aktionen
 * statt des nativen, aus dem Layout fallenden confirm()-Popups (siehe
 * tasks/uiux-audit/UI-005.md). Jedes <form data-confirm="Frage?"> wird
 * beim Absenden abgefangen; erst nach Bestätigung im Modal wird das
 * Formular tatsächlich submitted.
 */
(function () {
  let aktuellesFormular = null;

  function modal() {
    return document.getElementById("confirm-modal");
  }

  function oeffneModal(formular) {
    aktuellesFormular = formular;
    const text = formular.dataset.confirm;
    modal().querySelector("#confirm-modal-text").textContent = text;
    modal().classList.add("sichtbar");
    modal().querySelector("[data-confirm-bestaetigen]").focus();
  }

  function schliesseModal() {
    aktuellesFormular = null;
    modal().classList.remove("sichtbar");
  }

  document.addEventListener("submit", (e) => {
    const formular = e.target;
    if (!(formular instanceof HTMLFormElement)) return;
    if (!formular.dataset.confirm) return;
    if (formular.dataset.confirmBestaetigt === "true") return;
    e.preventDefault();
    oeffneModal(formular);
  });

  document.addEventListener("DOMContentLoaded", () => {
    const m = modal();
    if (!m) return;
    m.querySelector("[data-confirm-abbrechen]").addEventListener("click", schliesseModal);
    m.querySelector("[data-confirm-bestaetigen]").addEventListener("click", () => {
      if (!aktuellesFormular) return;
      aktuellesFormular.dataset.confirmBestaetigt = "true";
      const formular = aktuellesFormular;
      schliesseModal();
      formular.requestSubmit();
    });
    m.addEventListener("click", (e) => {
      if (e.target === m) schliesseModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && m.classList.contains("sichtbar")) schliesseModal();
    });
  });
})();
