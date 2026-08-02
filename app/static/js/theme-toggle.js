/*
 * Manueller Dark-/Light-Mode-Umschalter, zusätzlich zur automatischen
 * Systemerkennung (prefers-color-scheme, siehe app/static/css/style.css).
 * Die eigentliche Anwendung des gespeicherten Werts passiert bereits ganz
 * früh in einem Inline-Script in app/templates/base.html (vor dem
 * Stylesheet, um ein kurzes Aufblitzen des falschen Farbschemas zu
 * vermeiden) - hier nur noch die Klick-Logik und der aria-Zustand.
 */
(function () {
  const SPEICHER_SCHLUESSEL = "scandypro-theme";

  function istAktuellDunkel() {
    const explizit = localStorage.getItem(SPEICHER_SCHLUESSEL);
    if (explizit) return explizit === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function aktualisiereButton(btn) {
    const dunkel = istAktuellDunkel();
    btn.setAttribute("aria-pressed", String(dunkel));
    btn.setAttribute("aria-label", dunkel ? "Zu hellem Modus wechseln" : "Zu dunklem Modus wechseln");
  }

  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;
    aktualisiereButton(btn);

    btn.addEventListener("click", () => {
      const neuesTheme = istAktuellDunkel() ? "light" : "dark";
      localStorage.setItem(SPEICHER_SCHLUESSEL, neuesTheme);
      document.documentElement.setAttribute("data-theme", neuesTheme);
      aktualisiereButton(btn);
    });
  });
})();
