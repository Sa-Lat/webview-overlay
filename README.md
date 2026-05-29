# webview-overlay

A generic, frameless **WebView2 overlay** for Windows, driven by
[pywebview](https://pywebview.flowrl.com/). It renders a small always-on-top
card — session rows + an optional usage bar + an optional project-supplied
animation canvas — by polling any HTTP endpoint that serves the documented
`/dashboard.json` contract.

It is the reusable shell extracted from the *cube* Claude-Code status overlay:
window physics (DPI-aware `SetWindowPos`, per-monitor anchor persistence),
drag, a native Win32 right-click menu, WSL-IP resolution, and a 500 ms poll
loop. A consuming project supplies only its data source, theme, and (optionally)
an entity renderer.

## Install

```sh
py -3.13 -m pip install --user "webview-overlay @ git+https://github.com/Sa-Lat/webview-overlay.git"
```

Requires Windows + Python 3.13 (pywebview pulls `pythonnet`; WebView2 Runtime
ships with Win11). The package imports on any OS for testing, but `run()`
needs Windows.

## Use

```python
from pathlib import Path
from webview_overlay import OverlayConfig, run

H = Path(__file__).resolve().parent
run(OverlayConfig(
    app_name="myapp",              # -> %APPDATA%\myapp\
    brand_text="myapp",
    host="127.0.0.1", port=8765,   # or host=None to auto-resolve the WSL IP
    ageless_states=("idle", "done"),
    pulse_states=("thinking", "error"),
    state_labels={"idle": "idle", "done": "done"},
    background_colors={"light": "#e6eef2", "dark": "#0d1015"},
    assets=[str(H / "my-entity.js"), str(H / "my-theme.css")],   # optional
    frontend_config={"entityGlobal": "MyEntity",
                     "stateToEmotionGlobal": "MY_STATE_MAP",
                     "usageThresholds": [[80, "#e85555"], [50, "#d7a04a"]]},
))
```

See `examples/demo.py` for a self-contained runnable window.

## `/dashboard.json` contract

The overlay's Python bridge fetches this from your producer each poll:

```jsonc
{
  "state": "thinking",        // aggregated winner; drives the entity + lift
  "cwd": "myapp",             // winner label (informational)
  "ts": 1717000000.0,
  "usage_5h_pct": 42,         // number | null  (null -> "—", row hides)
  "sessions": [               // PRE-SORTED by the producer; not re-sorted here
    { "state": "thinking", "cwd": "proj", "age_s": 12,
      "session_id": "…", "label": "first user message" }
  ]
}
```

The bridge appends `theme`, `locked`, `hide_entity` at runtime — producers must
not send those.

## Frontend plugin hooks (`window.OVERLAY_CONFIG`)

The Python host injects `window.OVERLAY_CONFIG` before the base script. Keys:
`pollMs`, `agelessStates`, `pulseStates`, `stateLabels`, `usageThresholds`
(`[[pct,color],…]` descending), `defaultEmotion`, `sampleData`, and the two
optional entity hooks:

- `entityGlobal` — name of a `window.<Ctor>` constructed as
  `new Ctor(canvasEl, {size, emotion})` exposing `setEmotion/setSize/pause/resume`.
  Unset → the overlay runs with no canvas (rows + usage only).
- `stateToEmotionGlobal` — name of a `window.<map>` of `{ state: emotion }`.

Anything in `OverlayConfig.frontend_config` is merged into `OVERLAY_CONFIG`.

## Shell mode (custom interactive overlays)

The built-in `/dashboard.json` poll + rows/usage/entity render is just one app of
the window shell. Set `builtin_dashboard=False` to get the shell **without** it —
no poll, no data source required — and drive the UI yourself with your own assets
and custom bridge methods. This is how you build, say, a time-tracking overlay with
a `<select>` and Start/Stop buttons. See `examples/timetracker_demo.py`.

Three primitives:

- **`OverlayConfig.js_api`** — a bridge object whose public methods are exposed as
  `window.pywebview.api.<name>()`. Do your HTTP/API calls here in Python (no CORS,
  tokens stay server-side). Method names must not collide with the shell's own
  (`dashboard`, `set_theme`, `show`, `hide`, `quit`, drag/menu/window methods, …) —
  a collision raises at startup.
- **`#overlay-slot`** — an empty `<div>` in the card where your JS mounts widgets.
- **`overlay:ready` event** — fired on `document` once the shell is wired, with
  `{detail: {root, api}}` (`api` is `null` in browser-preview mode — guard it).

```python
class TimerApi:
    def start_timer(self, task): ...   # POST to your backend here
    def stop_timer(self, task): ...

run(OverlayConfig(app_name="tt", brand_text="track", builtin_dashboard=False,
                  js_api=TimerApi(), assets=[str(H/"tt.js"), str(H/"tt.css")]))
```
```js
document.addEventListener("overlay:ready", ({detail: {api}}) => {
  document.getElementById("overlay-slot").innerHTML = `<select>…</select><button id="go">Start</button>`;
  go.onclick = () => api.start_timer(taskId);   // → Python
});
```

In shell mode the dashboard-driven menu items (Lift on Activity, Show Animation) are
hidden and auto-unhide is inert — call `api.show()` from your own UI to un-hide.
You still get drag, the native menu (theme/size/position/quit), anchor persistence,
multi-instance, and DPI handling for free. Preview it in a browser via
`tests/preview/preview-shell.html`.

## Theming

`assets/base.css` is structure-only; every colour reads `var(--token, fallback)`
so the overlay renders monochrome on its own. Ship a theme stylesheet (via
`assets=[...]`) that **defines** the tokens (`--card --text --acc-* --brand
--bar-fill …`) to paint your palette. `background_colors` gives Python a per-
theme hex to paint the window before CSS loads (no white flash).

## Multiple instances

An instance is one process running `run(config)`. Concurrent overlays are
isolated by `(app_name, instance_id)`: per-instance window title (no HWND cross-
grab), per-instance `overlay.env` / `overlay-layouts.json`, and per-instance
crash log. The default instance keeps unsuffixed filenames. No single-instance
lock — launch as many as you like. **For two instances of the same `app_name`,
give each a distinct `instance_id`** — otherwise they share the same `overlay.env`
/ `overlay-layouts.json` and last-writer-wins on position.

## Asset delivery

`use_http_server=False` (default) inlines all assets into a single `html=`
document — proven, sidesteps WebView2's UNC `file://` limitation.
`use_http_server=True` stages assets into a temp dir served by pywebview's
built-in HTTP server (cleaner, real load order).

## License

MIT
