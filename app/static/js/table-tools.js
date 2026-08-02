/*
 * Leichte, generische Sortier-/Filterfunktion für Verwaltungstabellen
 * (siehe tasks/uiux-audit/UI-020.md) - rein clientseitig, kein Framework,
 * kein Server-Roundtrip nötig bei der aktuellen Größenordnung einer
 * Einrichtung. Wirkt nur, wenn die entsprechenden data-Attribute im
 * Template gesetzt sind, sonst no-op.
 *
 * Filter:  <input data-table-filter="tabelle-id" placeholder="Suchen …">
 * Sortierung: <th data-sort> auf sortierbaren Spalten derselben Tabelle.
 */
(function () {
  function initFilter(input) {
    const tabelle = document.getElementById(input.dataset.tableFilter);
    if (!tabelle) return;
    const zeilen = [...tabelle.querySelectorAll("tbody tr")];
    input.addEventListener("input", () => {
      const suchtext = input.value.trim().toLowerCase();
      zeilen.forEach((zeile) => {
        const treffer = zeile.textContent.toLowerCase().includes(suchtext);
        zeile.style.display = treffer ? "" : "none";
      });
    });
  }

  function initSortierung(th) {
    const tabelle = th.closest("table");
    const index = [...th.parentElement.children].indexOf(th);
    let aufsteigend = true;
    th.style.cursor = "pointer";
    th.addEventListener("click", () => {
      const tbody = tabelle.querySelector("tbody");
      const zeilen = [...tbody.querySelectorAll("tr")];
      zeilen.sort((a, b) => {
        const wertA = a.children[index]?.textContent.trim().toLowerCase() || "";
        const wertB = b.children[index]?.textContent.trim().toLowerCase() || "";
        return aufsteigend ? wertA.localeCompare(wertB, "de") : wertB.localeCompare(wertA, "de");
      });
      aufsteigend = !aufsteigend;
      zeilen.forEach((zeile) => tbody.appendChild(zeile));
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("input[data-table-filter]").forEach(initFilter);
    document.querySelectorAll("th[data-sort]").forEach(initSortierung);
  });
})();
