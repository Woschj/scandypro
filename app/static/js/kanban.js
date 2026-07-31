/*
 * Kanban-Drag&Drop: native HTML5-Drag&Drop-API, kein externes Framework
 * (Vorbild: Vanilla-JS + fetch() wie in wohlbefinden.js). Persistiert die
 * Kartenreihenfolge nach jedem Drop; bei Fehler wird neu geladen, damit
 * Server- und Client-Zustand nie dauerhaft auseinanderlaufen.
 */
(function () {
  function getDragAfterElement(container, y) {
    const elemente = [...container.querySelectorAll("[data-karte-id]:not(.karte--dragging)")];
    return elemente.reduce(
      (closest, kind) => {
        const box = kind.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) {
          return { offset, element: kind };
        }
        return closest;
      },
      { offset: -Infinity, element: null }
    ).element;
  }

  async function persistiereReihenfolge(liste) {
    const spalteId = liste.dataset.spalteId;
    const kartenIds = [...liste.querySelectorAll("[data-karte-id]")].map((el) =>
      parseInt(el.dataset.karteId, 10)
    );
    try {
      const antwort = await fetch(`/kanban/spalten/${spalteId}/reihenfolge`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ karten_ids: kartenIds }),
      });
      if (!antwort.ok) throw new Error("Speichern fehlgeschlagen");
    } catch (err) {
      location.reload();
    }
  }

  function init() {
    document.querySelectorAll("[data-karte-id]").forEach((karte) => {
      karte.addEventListener("dragstart", () => {
        karte.classList.add("karte--dragging");
        if (karte.open) karte.open = false;
      });
      karte.addEventListener("dragend", () => karte.classList.remove("karte--dragging"));
    });

    document.querySelectorAll(".karten-liste").forEach((liste) => {
      liste.addEventListener("dragover", (e) => {
        e.preventDefault();
        const dragging = document.querySelector(".karte--dragging");
        if (!dragging) return;
        const nachElement = getDragAfterElement(liste, e.clientY);
        if (nachElement == null) {
          liste.appendChild(dragging);
        } else {
          liste.insertBefore(dragging, nachElement);
        }
      });
      liste.addEventListener("drop", (e) => {
        e.preventDefault();
        persistiereReihenfolge(liste);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
