/*
 * Bewerbungen als Kanban-artiges Board: Drag&Drop zwischen Status-Spalten,
 * analog zu kanban.js. Bewusst OHNE Kartenreihenfolge-Persistenz - anders
 * als bei Kanban-Karten hat die Position einer Bewerbung innerhalb einer
 * Spalte keine Bedeutung, nur die Spalte selbst (= der Status) zählt. Die
 * Tastatur-Alternative zum Ziehen bleibt das "Verschieben"-Select in jeder
 * Karte (siehe app/templates/bewerbungen/uebersicht.html), das ganz ohne
 * JavaScript funktioniert.
 */
(function () {
  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  async function verschieben(bewerbungId, zielStatus) {
    try {
      const formData = new FormData();
      formData.append("status_wert", zielStatus);
      formData.append("csrf_token", csrfToken());
      const antwort = await fetch(`/bewerbungen/${bewerbungId}/verschieben`, {
        method: "POST",
        credentials: "same-origin",
        body: formData,
      });
      if (!antwort.ok) throw new Error("Verschieben fehlgeschlagen");
    } catch (err) {
      // Serverstand kann von der optimistisch verschobenen Karte abweichen
      // (z.B. Formularfehler) - Seite neu laden, damit nie stillschweigend
      // ein falscher Stand stehen bleibt.
    } finally {
      location.reload();
    }
  }

  function initDragUndDrop() {
    let startListe = null;

    document.querySelectorAll("[data-bewerbung-id]").forEach((karte) => {
      karte.addEventListener("dragstart", () => {
        karte.classList.add("karte--dragging");
        if (karte.open) karte.open = false;
        startListe = karte.closest(".karten-liste");
      });
      karte.addEventListener("dragend", () => karte.classList.remove("karte--dragging"));
    });

    document.querySelectorAll(".karten-liste[data-status]").forEach((liste) => {
      liste.addEventListener("dragover", (e) => {
        const dragging = document.querySelector(".karte--dragging");
        if (dragging) e.preventDefault();
      });
      liste.addEventListener("drop", (e) => {
        const karte = document.querySelector(".karte--dragging");
        if (!karte) return;
        e.preventDefault();
        if (startListe && startListe !== liste) {
          verschieben(karte.dataset.bewerbungId, liste.dataset.status);
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", initDragUndDrop);
})();
