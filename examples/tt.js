/* Time-tracker widget — mounted by webview-overlay's "overlay:ready" event.
 * Builds a <select> + Start/Stop into #overlay-slot and calls the custom
 * Python bridge (window.pywebview.api.*) exposed via OverlayConfig.js_api. */
document.addEventListener("overlay:ready", ({ detail: { api } }) => {
  const slot = document.getElementById("overlay-slot");
  slot.innerHTML = `
    <select id="tt-task" class="tt-select">
      <option value="proj-a">Project A</option>
      <option value="proj-b">Project B</option>
      <option value="proj-c">Project C</option>
    </select>
    <div class="tt-row">
      <button id="tt-start" class="tt-btn tt-go">Start</button>
      <button id="tt-stop" class="tt-btn">Stop</button>
      <span id="tt-elapsed" class="tt-elapsed">00:00</span>
    </div>`;

  const sel = document.getElementById("tt-task");
  const elapsedEl = document.getElementById("tt-elapsed");
  let startedAt = null;

  const fmt = (ms) => {
    const s = Math.floor(ms / 1000);
    return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  };
  (function tick() {
    if (startedAt != null) elapsedEl.textContent = fmt(Date.now() - startedAt);
    requestAnimationFrame(tick);
  })();

  document.getElementById("tt-start").onclick = () => {
    startedAt = Date.now();
    api?.start_timer?.(sel.value);   // bridge → Python (which would POST to a backend)
  };
  document.getElementById("tt-stop").onclick = () => {
    startedAt = null;
    elapsedEl.textContent = "00:00";
    api?.stop_timer?.(sel.value);
  };
  sel.onchange = () => api?.switch_task?.(sel.value);
});
