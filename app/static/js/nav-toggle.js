/*
 * Mobile-Kollaps der Topnav (siehe tasks/uiux-audit/UI-009.md): unterhalb
 * des Breakpoints in style.css sind Nav-Links + User-Chip standardmäßig
 * ausgeblendet und werden über diesen Button ein-/ausgeblendet. Oberhalb
 * des Breakpoints bleibt .nav-panel per CSS immer sichtbar, der Button
 * ist dann unsichtbar - dieses Skript betrifft nur den mobilen Zustand.
 */
(function () {
  const toggle = document.getElementById("nav-toggle");
  const panel = document.getElementById("nav-panel");
  if (!toggle || !panel) return;

  function schliessen() {
    panel.classList.remove("nav-panel--offen");
    toggle.setAttribute("aria-expanded", "false");
  }

  toggle.addEventListener("click", () => {
    const offen = panel.classList.toggle("nav-panel--offen");
    toggle.setAttribute("aria-expanded", String(offen));
  });

  panel.querySelectorAll("a").forEach((link) => link.addEventListener("click", schliessen));

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") schliessen();
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 720) schliessen();
  });
})();
