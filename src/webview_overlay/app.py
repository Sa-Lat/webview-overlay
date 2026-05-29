"""run(config) — launch the overlay window (blocking). Generalized from the
cube overlay's main(): crash-log wiring, WSL-IP resolution, monitor-anchor
restore, and the WebView2/pywebview window are all driven by OverlayConfig.

Heavy imports (`webview`, `ctypes.windll` via the win32/layout modules) are
deferred to call time so the package imports on any OS.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

from . import assets, layout, net, win32
from .config import OverlayConfig
from .jsapi import JsApi
from .store import Store


def _wire_crash_log(config) -> None:
    """pythonw.exe (.pyw) has no console — route stderr to a per-instance log
    so silent startup crashes are debuggable."""
    if os.name != "nt":
        return
    try:
        inst = config.instance
        suffix = "" if inst == "default" else f"-{inst}"
        log_path = os.path.join(
            os.environ.get("TEMP", os.path.expanduser("~")),
            f"{config.app_name}-overlay{suffix}.log")
        sys.stderr = open(log_path, "a", buffering=1, encoding="utf-8", errors="replace")
        sys.stderr.write(f"\n--- start pid={os.getpid()} exe={sys.executable} ---\n")
        sys.stderr.write(f"app={config.app_name} instance={inst} argv={sys.argv}\n")

        import traceback

        def _excepthook(typ, val, tb):
            traceback.print_exception(typ, val, tb, file=sys.stderr)
            sys.stderr.flush()

        sys.excepthook = _excepthook
    except Exception:
        pass


def _resolve_mock_url(config) -> str | None:
    if config.url:
        return config.url
    if config.host:
        return f"http://{config.host}:{config.port}"
    if not config.builtin_dashboard:
        return None  # shell mode: no data source needed
    ip = net.resolve_wsl_ip()
    if not ip:
        sys.stderr.write(
            "Could not resolve WSL IP via `wsl.exe hostname -I`. "
            "Set OverlayConfig.host or .url explicitly.\n")
        return None
    return f"http://{ip}:{config.port}"


def _expose_js_api(window, obj) -> None:
    """Expose a consumer bridge object's public methods as window.pywebview.api.<name>.
    Reserved shell method names collide-fail so a consumer can't shadow them."""
    reserved = {n for n in dir(JsApi) if not n.startswith("_")}
    funcs = []
    for name in dir(obj):
        if name.startswith("_"):
            continue
        attr = getattr(obj, name)
        if not callable(attr):
            continue
        if name in reserved:
            raise ValueError(
                f"js_api method {name!r} collides with a reserved shell method")
        funcs.append(attr)
    if funcs:
        window.expose(*funcs)


def run(config: OverlayConfig) -> None:
    _wire_crash_log(config)
    win32.set_dpi_awareness()

    # Silence pywebview's pythonnet recursion-noise BEFORE importing webview.
    import logging
    logging.getLogger("pywebview").setLevel(logging.CRITICAL)
    import webview  # pip install pywebview

    store = Store(config)
    mock_url = _resolve_mock_url(config)
    if config.builtin_dashboard and not mock_url:
        sys.exit(2)

    api = JsApi(config, store, mock_url)

    # Layout fingerprint → window position. Restore saved anchor, else fall
    # back to bottom-right of the primary monitor.
    sw, sh = 1920, 1080  # only used by the fallback path
    lay = layout.detect_layout(sw, sh)
    fp = lay["fingerprint"]
    px, py, pw, ph = lay["primary"]
    api.fingerprint = fp
    api.primary_rect = (px, py, pw, ph)

    init_w = api.width
    init_h = config.initial_height

    layouts = store.load_layouts()
    if fp in layouts:
        anchor_r = int(layouts[fp].get("anchor_r", px + pw - 20))
        anchor_b = int(layouts[fp].get("anchor_b", py + ph - 20))
        if not layout.anchor_in_bounds(anchor_r, anchor_b, init_w, init_h, lay["primary"]):
            sys.stderr.write(
                f"saved anchor ({anchor_r},{anchor_b}) out of primary bounds "
                f"{lay['primary']}; resetting to bottom-right\n")
            anchor_r = px + pw - 20
            anchor_b = py + ph - 20
            store.save_layout_anchor(fp, anchor_r, anchor_b)
    else:
        anchor_r = px + pw - 20
        anchor_b = py + ph - 20
        store.save_layout_anchor(fp, anchor_r, anchor_b)

    x = anchor_r - init_w
    y = anchor_b - init_h
    api.anchor_r = anchor_r
    api.anchor_b = anchor_b

    # Unique window title per instance so concurrent processes never grab each
    # other's HWND (find_hwnd matches this exact title).
    instance_token = config.instance_id or os.getpid()
    win_title = f"{config.window_title}#{instance_token}"

    sys.stderr.write(
        f"mock={mock_url}  title={win_title}  layout={fp}  "
        f"primary={px},{py},{pw}x{ph}  anchor=br({anchor_r},{anchor_b})  "
        f"pos=+{x}+{y}  win={init_w}x{init_h}  theme={api.theme}\n")

    card_bg = config.background_for(api.theme)

    serve_dir = None
    create_kwargs = dict(
        title=win_title,
        js_api=api,
        x=x, y=y,
        width=init_w, height=init_h,
        min_size=(min(config.size_presets), 60),
        frameless=True,
        easy_drag=False,
        on_top=api.topmost,
        resizable=False,
        background_color=card_bg,
    )
    if config.use_http_server:
        serve_dir = assets.stage_assets(config, api.theme)
        window = webview.create_window(url=str(serve_dir / "index.html"), **create_kwargs)
    else:
        html_doc = assets.build_inline_document(config, api.theme)
        window = webview.create_window(html=html_doc, **create_kwargs)
    api.window = window

    if config.js_api is not None:
        _expose_js_api(window, config.js_api)

    def on_closed():
        try:
            api.save_anchor()
        except Exception as e:
            sys.stderr.write(f"save on close failed: {e}\n")
        if serve_dir is not None:
            shutil.rmtree(serve_dir, ignore_errors=True)

    window.events.closed += on_closed

    def on_loaded():
        # Hook DOM-ready, not webview.start's callback: on pywebview 6
        # EdgeChromium the start callback fires before window.native is wired,
        # so HWND discovery returns NULL. By `loaded` the form exists.
        sys.stderr.write(f"loaded; window.native = {window.native!r}\n")
        hwnd = win32.find_hwnd(window, win_title)
        if not hwnd:
            sys.stderr.write("HWND discovery failed at loaded event\n")
            return
        api.hwnd = hwnd
        win32.win32_move(hwnd, x, y, init_w, init_h, topmost=api.topmost)
        api._initialised = True
        sys.stderr.write(f"hwnd installed: {hwnd:#x}\n")

    window.events.loaded += on_loaded
    webview.start(debug=False)


# ── CLI (thin) ─────────────────────────────────────────────────────────────
_TOML_KEYS = {
    "app_name", "instance_id", "window_title", "env_prefix", "dashboard_path",
    "host", "port", "url", "default_theme", "themes", "default_width",
    "size_presets", "default_topmost", "default_lift", "default_hide_entity",
    "initial_height", "brand_text", "assets", "frontend_config",
    "background_colors", "font_href", "font_family", "ageless_states",
    "pulse_states", "state_labels", "use_http_server",
}


def cli() -> None:
    ap = argparse.ArgumentParser(prog="webview-overlay",
                                 description="Run a webview-overlay window from a TOML config.")
    ap.add_argument("--config", required=True, help="path to an overlay TOML config")
    args = ap.parse_args()

    import tomllib
    with open(args.config, "rb") as f:
        data = tomllib.load(f)
    unknown = set(data) - _TOML_KEYS
    if unknown:
        sys.stderr.write(f"ignoring unknown config keys: {sorted(unknown)}\n")
    kwargs = {k: data[k] for k in data if k in _TOML_KEYS}
    for tup in ("themes", "size_presets", "ageless_states", "pulse_states"):
        if tup in kwargs and isinstance(kwargs[tup], list):
            kwargs[tup] = tuple(kwargs[tup])
    run(OverlayConfig(**kwargs))


if __name__ == "__main__":
    cli()
