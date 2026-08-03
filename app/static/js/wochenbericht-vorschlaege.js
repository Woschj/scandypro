/*
 * Optionale Übernahme von in dieser Woche abgeschlossenen Kanban-Karten in
 * die Tätigkeiten-Felder des "Neuer Wochenbericht"-Formulars (siehe
 * app/routers/wochenberichte.py:_erledigte_kanban_karten_diese_woche,
 * app/templates/wochenberichte/teilnehmer_uebersicht.html) - überschreibt
 * nie, hängt nur an (mit Zeilenumbruch, falls das Feld schon Text enthält).
 */
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-vorschlag-chips]").forEach((liste) => {
      const ziel = document.getElementById(liste.dataset.vorschlagChips);
      if (!ziel) return;
      liste.querySelectorAll("[data-vorschlag-text]").forEach((chip) => {
        chip.addEventListener("click", () => {
          const text = chip.dataset.vorschlagText;
          ziel.value = ziel.value.trim() ? `${ziel.value.trim()}\n${text}` : text;
        });
      });
    });
  });
})();
