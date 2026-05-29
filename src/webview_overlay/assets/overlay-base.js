/* webview-overlay — generic render loop.
 *
 * Polls window.pywebview.api.dashboard() every CFG.pollMs, diffs against the
 * last render and patches the DOM. State semantics (which states are ageless,
 * which pulse, their labels), usage thresholds and an optional entity renderer
 * are all supplied by window.OVERLAY_CONFIG, injected by the Python host.
 *
 * Falls back to CFG.sampleData when the pywebview API is absent so you can
 * preview the look by opening the page in any browser.
 */

const CFG = window.OVERLAY_CONFIG || {};
const POLL_MS = CFG.pollMs || 500;

const AGELESS = new Set(CFG.agelessStates || []);
const PULSE_STATES = new Set(CFG.pulseStates || []);
const STATE_LABELS = CFG.stateLabels || {};
const DEFAULT_EMOTION = CFG.defaultEmotion || "idle";
const SAMPLE_DATA = CFG.sampleData || { state: "idle", ts: 0, usage_5h_pct: null, sessions: [] };

function formatAge(s) {
  s = Math.floor(s || 0);
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "m";
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return m === 0 ? h + "h" : h + "h" + m + "m";
}

/* Threshold colours for the usage bar: [[pct, color], …] descending; first
   match wins. null = stay on palette default --bar-fill. */
function usageFill(pct) {
  if (pct == null) return null;
  for (const pair of (CFG.usageThresholds || [])) {
    if (pct >= pair[0]) return pair[1];
  }
  return null;
}

/* ───────────────────────────── DOM */
const root = document.getElementById("root");
const rowsEl = document.getElementById("rows");
const sessCountEl = document.getElementById("sess-count");
const dividerEl = document.querySelector(".divider");
const usageRowEl = document.getElementById("usage-row");
const usagePctEl = document.getElementById("usage-pct");
const barFillEl = document.getElementById("bar-fill");
const entityWrapEl = document.getElementById("entity-wrap");
const entityCanvasEl = document.getElementById("overlay-entity");

const last = {
  theme: null,
  rowSig: null,
  usagePct: undefined,
  entityEmotion: null,
};

function setTheme(theme) {
  if (!theme || theme === last.theme) return;
  document.documentElement.setAttribute("data-theme", theme);
  root.setAttribute("data-theme", theme);
  last.theme = theme;
}

/* ───────────────────────────── entity instance (optional)
 *
 * The project supplies a renderer by exporting a constructor on
 * window[CFG.entityGlobal]. When unset, the overlay runs with no canvas
 * (rows + usage only). The constructor must accept (canvasEl, {size, emotion})
 * and expose setEmotion/setSize/pause/resume. */
let entity = null;
function entityCtor() {
  return CFG.entityGlobal ? window[CFG.entityGlobal] : null;
}
function ensureEntity() {
  if (entity) return entity;
  const Ctor = entityCtor();
  if (!entityCanvasEl || typeof Ctor !== "function") return null;
  const wrap = document.querySelector(".wrap");
  const innerW = wrap ? wrap.clientWidth - 24 : 156;
  entity = new Ctor(entityCanvasEl, {
    size: Math.max(80, innerW),
    emotion: DEFAULT_EMOTION,
  });
  window.__overlayEntity = entity;  // expose for demo / debugging
  return entity;
}

function emotionFor(state) {
  const map = (CFG.stateToEmotionGlobal && window[CFG.stateToEmotionGlobal]) || {};
  return map[state] || DEFAULT_EMOTION;
}

function sublineText(s, cwdCounts) {
  if ((cwdCounts.get(s.cwd) || 0) <= 1) return "";
  return s.label || "";
}

function sigOfSessions(sessions, cwdCounts) {
  return sessions.map(s => {
    const sub = sublineText(s, cwdCounts);
    return AGELESS.has(s.state)
      ? `${s.cwd}|${s.state}|-|${sub}`
      : `${s.cwd}|${s.state}|${Math.floor((s.age_s || 0) / 30)}|${sub}`;
  }).join(",");
}

function renderRows(sessions) {
  const cwdCounts = new Map();
  for (const s of sessions) {
    cwdCounts.set(s.cwd, (cwdCounts.get(s.cwd) || 0) + 1);
  }

  const sig = sigOfSessions(sessions, cwdCounts);
  if (sig === last.rowSig) {
    for (let i = 0; i < sessions.length; i++) {
      const s = sessions[i];
      if (AGELESS.has(s.state)) continue;
      const metaEl = rowsEl.children[i]?.querySelector(".meta");
      if (metaEl) metaEl.textContent = formatAge(s.age_s);
    }
    return;
  }
  last.rowSig = sig;

  rowsEl.innerHTML = "";
  for (const s of sessions) {
    const block = document.createElement("div");
    block.className = "row-block";

    const row = document.createElement("div");
    row.className = "row";

    const dot = document.createElement("span");
    dot.className = "dot";
    dot.setAttribute("data-state", s.state);
    if (PULSE_STATES.has(s.state)) dot.setAttribute("data-live", "true");

    const cwd = document.createElement("span");
    cwd.className = "cwd";
    cwd.textContent = s.cwd || "—";

    const meta = document.createElement("span");
    meta.className = "meta";
    if (AGELESS.has(s.state)) {
      meta.setAttribute("data-ageless", "true");
      meta.textContent = STATE_LABELS[s.state] || s.state;
    } else {
      meta.textContent = formatAge(s.age_s);
    }

    row.appendChild(dot);
    row.appendChild(cwd);
    row.appendChild(meta);
    block.appendChild(row);

    const subTxt = sublineText(s, cwdCounts);
    if (subTxt) {
      const sub = document.createElement("div");
      sub.className = "subline";
      sub.textContent = subTxt;
      block.appendChild(sub);
    }

    rowsEl.appendChild(block);
  }
}

function renderUsage(pct) {
  const slim = !!ui.hide_entity;
  const sig = `${pct}|${slim ? 1 : 0}`;
  if (sig === last.usagePct) return;
  last.usagePct = sig;
  if (pct == null && !slim) {
    usageRowEl.hidden = true;
    if (dividerEl) dividerEl.hidden = true;
    return;
  }
  usageRowEl.hidden = false;
  if (dividerEl) dividerEl.hidden = slim;
  if (pct == null) {
    usagePctEl.textContent = "—";
    barFillEl.style.width = "0%";
    barFillEl.style.background = "";
  } else {
    usagePctEl.textContent = `${pct}%`;
    barFillEl.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    const override = usageFill(pct);
    barFillEl.style.background = override || "";
  }
}

function renderEntity(state) {
  const ent = ensureEntity();
  if (!ent) return;
  if (ui.hide_entity) {
    if (entityWrapEl) entityWrapEl.hidden = true;
    ent.pause();
    return;
  }
  if (entityWrapEl) entityWrapEl.hidden = false;
  ent.resume();
  const emo = emotionFor(state);
  if (emo !== last.entityEmotion) {
    ent.setEmotion(emo);
    last.entityEmotion = emo;
  }
}

function invalidateRender() {
  last.usagePct = undefined;
  last.entityEmotion = null;
}

function render(data) {
  if (!data) return;
  setTheme(data.theme);
  const sessions = data.sessions || [];
  if (sessCountEl) sessCountEl.textContent = String(sessions.length);
  renderRows(sessions);
  renderUsage(data.usage_5h_pct ?? null);
  renderEntity(data.state);
}

/* ───────────────────────────── poll loop */
async function poll() {
  let data = null;
  if (window.pywebview?.api?.dashboard) {
    try {
      data = await window.pywebview.api.dashboard();
    } catch (e) {
      console.warn("dashboard fetch failed", e);
    }
  } else {
    data = SAMPLE_DATA;  /* preview mode */
  }
  if (data) {
    if (typeof ui !== "undefined") {
      if (data.theme && data.theme !== ui.theme) { ui.theme = data.theme; applyUi(); }
      if (typeof data.locked === "boolean" && data.locked !== ui.locked) {
        ui.locked = data.locked;
        applyUi();
      }
      if (typeof data.hide_entity === "boolean" && data.hide_entity !== ui.hide_entity) {
        ui.hide_entity = data.hide_entity;
        invalidateRender();
      }
      maybeLift(data.state);
    }
  }
  render(data);
  setTimeout(poll, POLL_MS);
}

/* URL query lets a static preview pick a theme without pywebview:
   preview.html?theme=dark */
function applyQueryOverrides() {
  const q = new URLSearchParams(location.search);
  const theme = q.get("theme");
  if (theme) setTheme(theme);
}
applyQueryOverrides();

/* ───────────────────────────── client state */
const ui = {
  theme: CFG.defaultTheme || "light",
  width: CFG.defaultWidth || 180,
  locked: false,
  topmost: true,
  lift: false,
  size_presets: CFG.sizePresets || [140, 180, 240],
  hide_winner: null,
  hidden: false,
  hide_entity: false,
};
const api = () => window.pywebview && window.pywebview.api;

function applyUi() {
  setTheme(ui.theme);
  document.body.classList.toggle("draggable", !ui.locked);
}

/* ───────────────────────────── Drag */
const drag = { active: false };

function attachDrag() {
  const wrap = document.querySelector(".wrap");
  if (!wrap) return;

  wrap.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    if (ui.locked) return;
    if (e.target.closest(".ctx-menu")) return;
    drag.active = true;
    document.body.classList.add("dragging");
    /* Fire-and-forget. Python reads cursor pos via GetCursorPos so we don't
       pass screenX/Y (WebView2 reports logical px, mismatching SetWindowPos's
       physical-pixel space). */
    api()?.start_drag();
  });

  document.addEventListener("mousemove", () => {
    if (!drag.active) return;
    api()?.move_relative();
  });
  document.addEventListener("mouseup", () => {
    if (!drag.active) return;
    drag.active = false;
    document.body.classList.remove("dragging");
    api()?.end_drag();
  });
}

/* Menu is native Win32 (TrackPopupMenu) — frameless WebView2 clips DOM popups
   past its bounds, so hand off to the Python bridge. */
function attachContextMenu() {
  document.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    api()?.show_menu();
  });
}

/* Dynamic window height — report .wrap content height to Python on every DOM
   size change; Python resizes the OS window keeping the bottom-right anchor
   stable so the card grows upward. */
function attachAutoResize() {
  const wrap = document.querySelector(".wrap");
  if (!wrap || typeof ResizeObserver === "undefined") return;
  let lastH = 0, raf = 0;
  const ro = new ResizeObserver(() => {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      const h = Math.ceil(wrap.getBoundingClientRect().height);
      if (h && h !== lastH) {
        lastH = h;
        api()?.resize_height(h);
      }
      if (entity && entityCanvasEl) {
        const cssW = Math.round(entityCanvasEl.getBoundingClientRect().width);
        if (cssW && Math.abs(cssW - entity.size) > 2) entity.setSize(cssW);
      }
    });
  });
  ro.observe(wrap);
  if (entityCanvasEl) ro.observe(entityCanvasEl);
}

/* Lift on activity: ageless → pulse-state crossing brings the window to front
   so a long-idle overlay surfaces when work resumes. */
let activityState = { lastWinner: null };
function maybeLift(newWinner) {
  if (!ui.lift) {
    activityState.lastWinner = newWinner;
    return;
  }
  if (activityState.lastWinner
      && AGELESS.has(activityState.lastWinner)
      && PULSE_STATES.has(newWinner)) {
    api()?.bring_to_front();
  }
  activityState.lastWinner = newWinner;
}

async function bootstrap() {
  const bridge = api();
  if (bridge && bridge.initial_state) {
    try {
      Object.assign(ui, await bridge.initial_state());
    } catch (e) {
      console.warn("initial_state failed", e);
    }
  }
  applyUi();
  attachDrag();
  attachContextMenu();
  attachAutoResize();
  poll();
}

/* pywebview injects api asynchronously; listen for pywebviewready, plus a
   fallback timer for plain-browser preview mode. */
let _bootstrapped = false;
function _kick() {
  if (_bootstrapped) return;
  _bootstrapped = true;
  bootstrap();
}
window.addEventListener("pywebviewready", _kick);
setTimeout(_kick, 800);
