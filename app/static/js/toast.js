/*
 * Gemeinsame sanfte Toast-Benachrichtigung für positive Rückmeldungen
 * (siehe CLAUDE.md Abschnitt 25 "positive Verstärkung") - wird von
 * app/static/js/kanban.js UND app/static/js/tagebuch-interaktiv.js genutzt,
 * damit im ganzen Projekt dasselbe ruhige visuelle Vokabular gilt statt
 * mehrerer separat gepflegter Toast-Implementierungen. Muss vor beiden
 * Skripten geladen werden (siehe app/templates/base.html).
 */
(function () {
  function zeigeToast(text) {
    const bestehender = document.querySelector(".toast");
    if (bestehender) bestehender.remove();
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    toast.textContent = text;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("toast--sichtbar"));
    setTimeout(() => {
      toast.classList.remove("toast--sichtbar");
      setTimeout(() => toast.remove(), 300);
    }, 1800);
  }

  window.zeigeToast = zeigeToast;
})();
