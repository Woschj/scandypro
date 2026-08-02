/*
 * Client-seitige Größenprüfung für Datei-Uploads (siehe
 * app/core/uploads.py: MAX_DATEIGROESSE_BYTES) - verhindert, dass eine
 * zu große Datei erst vollständig hochgeladen wird, bevor der Server sie
 * ablehnt (siehe tasks/uiux-audit/UI-006.md). Ersetzt nicht die
 * serverseitige Prüfung, die bleibt das eigentliche Sicherheitsnetz.
 */
(function () {
  const MAX_BYTES = 10 * 1024 * 1024;

  function meldungZeigen(input, text) {
    let hinweis = input.parentElement.querySelector(".upload-fehler");
    if (!hinweis) {
      hinweis = document.createElement("p");
      hinweis.className = "upload-fehler form-error";
      hinweis.style.marginTop = "0.5rem";
      input.insertAdjacentElement("afterend", hinweis);
    }
    hinweis.textContent = text;
  }

  function meldungEntfernen(input) {
    const hinweis = input.parentElement.querySelector(".upload-fehler");
    if (hinweis) hinweis.remove();
  }

  document.addEventListener(
    "change",
    (e) => {
      const input = e.target;
      if (!(input instanceof HTMLInputElement) || input.type !== "file") return;
      const datei = input.files && input.files[0];
      if (!datei) {
        meldungEntfernen(input);
        return;
      }
      if (datei.size > MAX_BYTES) {
        meldungZeigen(input, `"${datei.name}" ist zu groß (max. 10 MB). Bitte eine kleinere Datei wählen.`);
        input.value = "";
      } else {
        meldungEntfernen(input);
      }
    },
    true
  );

  document.addEventListener("submit", (e) => {
    const formular = e.target;
    if (!(formular instanceof HTMLFormElement)) return;
    const zuGross = [...formular.querySelectorAll('input[type="file"]')].some(
      (input) => input.files && input.files[0] && input.files[0].size > MAX_BYTES
    );
    if (zuGross) e.preventDefault();
  });
})();
