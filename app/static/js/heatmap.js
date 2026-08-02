/*
 * Touch-Zugriff auf die Mood-Heatmap ("Dein Verlauf"): der Wert einer
 * Kachel wird bisher primär über Farbe vermittelt, textuelle Details nur
 * per title-Tooltip (Hover) - auf Touch-Geräten nicht erreichbar (siehe
 * tasks/uiux-audit/UI-012.md). Tippen/Klicken auf eine Kachel zeigt den
 * Text zusätzlich in einem kurzen Toast.
 */
(function () {
  function zeigeToast(text) {
    const bestehender = document.querySelector(".kanban-toast");
    if (bestehender) bestehender.remove();
    const toast = document.createElement("div");
    toast.className = "kanban-toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    toast.textContent = text;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("kanban-toast--sichtbar"));
    setTimeout(() => {
      toast.classList.remove("kanban-toast--sichtbar");
      setTimeout(() => toast.remove(), 300);
    }, 1800);
  }

  document.addEventListener("click", (e) => {
    const tag = e.target.closest(".heatmap-tag[data-heatmap-label]");
    if (!tag) return;
    zeigeToast(tag.dataset.heatmapLabel);
  });
})();
