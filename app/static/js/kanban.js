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

  /*
   * Horizontales Scrollen der Board-Spalten: Fade-Kanten + Pfeil-Buttons
   * zeigen an, ob noch mehr Spalten folgen; zusätzlich Klick-und-Ziehen auf
   * dem leeren Spalten-Hintergrund (Trello-Stil), ohne die native
   * Karten-Drag&Drop-Funktion (draggable=true auf .karte) zu stören.
   */
  function initScrollUX() {
    document.querySelectorAll("[data-board-scroll]").forEach((wrap) => {
      const scroller = wrap.querySelector(".board-columns");
      if (!scroller) return;

      function updateEdges() {
        const max = scroller.scrollWidth - scroller.clientWidth;
        wrap.classList.toggle("can-scroll-left", scroller.scrollLeft > 24);
        wrap.classList.toggle("can-scroll-right", scroller.scrollLeft < max - 24);
      }
      scroller.scrollLeft = 0;
      updateEdges();
      scroller.addEventListener("scroll", updateEdges, { passive: true });
      window.addEventListener("resize", updateEdges);
      if (window.ResizeObserver) new ResizeObserver(updateEdges).observe(scroller);

      wrap.querySelectorAll(".board-scroll-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const richtung = parseInt(btn.dataset.scrollDir, 10);
          const spalte = scroller.querySelector(".board-column");
          const schritt = spalte ? spalte.getBoundingClientRect().width + 24 : 320;
          scroller.scrollBy({ left: richtung * schritt, behavior: "smooth" });
        });
      });

      let ziehtGerade = false;
      let startX = 0;
      let startScrollLeft = 0;
      scroller.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;
        if (e.target.closest("[data-karte-id], button, a, input, textarea, select, summary")) return;
        ziehtGerade = true;
        scroller.classList.add("board-columns--panning");
        startX = e.clientX;
        startScrollLeft = scroller.scrollLeft;
        e.preventDefault();
      });
      window.addEventListener("mousemove", (e) => {
        if (!ziehtGerade) return;
        scroller.scrollLeft = startScrollLeft - (e.clientX - startX);
      });
      window.addEventListener("mouseup", () => {
        if (!ziehtGerade) return;
        ziehtGerade = false;
        scroller.classList.remove("board-columns--panning");
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    init();
    initScrollUX();
  });
})();
