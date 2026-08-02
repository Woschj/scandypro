/*
 * Kanban-Drag&Drop: native HTML5-Drag&Drop-API, kein externes Framework
 * (Vorbild: Vanilla-JS + fetch() wie in wohlbefinden.js). Persistiert die
 * Kartenreihenfolge nach jedem Drop; bei Fehler wird neu geladen, damit
 * Server- und Client-Zustand nie dauerhaft auseinanderlaufen.
 *
 * Ruhiges "geschafft"-Feedback (siehe CLAUDE.md, Abschnitt 25 Bonus-
 * Features "positive Verstärkung"): jede Karten-Bewegung bekommt ein
 * kurzes Pop, eine Karte in die fest verankerte Erledigt-Spalte (siehe
 * app/models/kanban.py: Spalte.ist_system_erledigt - strukturell fixiert,
 * nicht per Positions-Heuristik erkannt) und das Abhaken der letzten
 * Unteraufgabe einer Karte lösen zusätzlich einen warmen Glow + kurzen
 * Stempel-Haken aus. Bewusst kein Konfetti/Punktesystem/Bestenliste - passt
 * nicht zum Reha-Kontext (siehe CLAUDE.md, "keine Leistungsbegriffe") und
 * soll bei häufigem Auslösen nicht überreizen.
 */
(function () {
  const FEIER_TEXTE = ["Geschafft ✓", "Erledigt – gut gemacht", "Fertig – schön, dass du dran geblieben bist"];

  function stempel(ursprungRect) {
    const el = document.createElement("span");
    el.className = "geschafft-stempel";
    el.textContent = "✓";
    el.style.left = ursprungRect.left + ursprungRect.width / 2 - 12 + "px";
    el.style.top = ursprungRect.top + "px";
    document.body.appendChild(el);
    el.addEventListener("animationend", () => el.remove());
  }

  function feiern(karte) {
    karte.classList.remove("karte--gefeiert");
    void karte.offsetWidth;
    karte.classList.add("karte--gefeiert");
    stempel(karte.getBoundingClientRect());
    zeigeKanbanToast(zufallsText());
  }

  function zeigeKanbanToast(text) {
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

  function zufallsText() {
    return FEIER_TEXTE[Math.floor(Math.random() * FEIER_TEXTE.length)];
  }

  function popAnimation(karte) {
    karte.classList.remove("karte--bewegt");
    // Reflow erzwingen, damit die Animation bei wiederholtem Drop erneut
    // startet (Klasse einfach erneut setzen würde sonst nichts tun, wenn
    // sie schon vorhanden war).
    void karte.offsetWidth;
    karte.classList.add("karte--bewegt");
    karte.addEventListener("animationend", () => karte.classList.remove("karte--bewegt"), { once: true });
  }

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

  async function persistiereReihenfolge(liste, karte, spalteGewechselt, startSpalte) {
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

      popAnimation(karte);
      if (spalteGewechselt) {
        const wirdErledigt = liste.dataset.istErledigtSpalte === "true";
        const warErledigt = startSpalte && startSpalte.dataset.istErledigtSpalte === "true";
        if (wirdErledigt) {
          // Karte wird jetzt gesperrt (siehe app/routers/kanban_karten.py:
          // _karte_ist_gesperrt) - Server-Markup neu laden, damit Bearbeiten-
          // Formulare tatsächlich verschwinden, aber erst nach dem kurzen
          // Feier-Moment, damit das Feedback sichtbar bleibt.
          feiern(karte);
          setTimeout(() => location.reload(), 900);
        } else if (warErledigt) {
          location.reload();
        }
      }
    } catch (err) {
      location.reload();
    }
  }

  function initDragUndDrop() {
    let startSpalte = null;

    document.querySelectorAll("[data-karte-id]").forEach((karte) => {
      karte.addEventListener("dragstart", () => {
        karte.classList.add("karte--dragging");
        if (karte.open) karte.open = false;
        startSpalte = karte.closest(".karten-liste");
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
        const karte = document.querySelector(".karte--dragging") || liste.querySelector("[data-karte-id]");
        const spalteGewechselt = startSpalte !== null && startSpalte !== liste;
        persistiereReihenfolge(liste, karte, spalteGewechselt, startSpalte);
      });
    });
  }

  /*
   * Unteraufgaben per fetch() umschalten statt vollem Seiten-Reload - nur
   * so ist Platz für eine kurze Puls-Animation. Fällt bei JS-Fehlern auf
   * die normale Formular-Submission zurück (kein preventDefault, wenn der
   * fetch() selbst nicht startet).
   */
  function initUnteraufgaben() {
    document.querySelectorAll(".unteraufgabe-umschalten-form").forEach((form) => {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const zeile = form.closest("[data-unteraufgabe-id]");
        const karte = form.closest("[data-karte-id]");
        const btn = form.querySelector(".unteraufgabe-toggle-btn");
        try {
          const antwort = await fetch(form.action, { method: "POST", credentials: "same-origin" });
          if (!antwort.ok) throw new Error("Umschalten fehlgeschlagen");
          const daten = await antwort.json();

          zeile.classList.toggle("unteraufgabe--erledigt", daten.erledigt);
          btn.textContent = daten.erledigt ? "✓" : "○";
          btn.classList.remove("unteraufgabe-toggle-btn--puls");
          void btn.offsetWidth;
          btn.classList.add("unteraufgabe-toggle-btn--puls");

          if (karte) {
            const alle = karte.querySelectorAll("[data-unteraufgabe-id]").length;
            const erledigt = karte.querySelectorAll("[data-unteraufgabe-id].unteraufgabe--erledigt").length;
            const text = karte.querySelector("[data-fortschritt-text]");
            const fuellung = karte.querySelector("[data-fortschritt-fuellung]");
            if (text) text.textContent = `${erledigt}/${alle} Unteraufgaben erledigt`;
            if (fuellung) fuellung.style.width = Math.round((erledigt / alle) * 100) + "%";
          }

          if (daten.karte_komplett) {
            stempel(btn.getBoundingClientRect());
          }
        } catch (err) {
          location.reload();
        }
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
    initDragUndDrop();
    initUnteraufgaben();
    initScrollUX();
  });
})();
