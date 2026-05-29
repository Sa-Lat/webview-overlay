"""Assemble the overlay HTML document.

One template (`assets/index.html`) with placeholders, filled two ways:

* inline (default)  — base + project asset *contents* injected as <style>/
  <script> blocks; the result is passed to webview as html=. Proven, behaves
  exactly like the original cube overlay, sidesteps WebView2's UNC file://
  limitation.
* http_server (opt-in) — base + project files staged into one local temp dir
  with real <link>/<script src> tags; served by pywebview's built-in server.

Both share the same template and the same OVERLAY_CONFIG payload, so the
frontend can't tell them apart.
"""
from __future__ import annotations

import json
import os
import tempfile
from importlib.resources import files
from pathlib import Path

_PKG_ASSETS = files("webview_overlay") / "assets"
_BASE_CSS = "base.css"
_BASE_JS = "overlay-base.js"
_TEMPLATE = "index.html"


def _read_pkg(name: str) -> str:
    return (_PKG_ASSETS / name).read_text(encoding="utf-8")


def _esc_html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _split_assets(paths):
    css, js = [], []
    for p in paths:
        (css if str(p).lower().endswith(".css") else js).append(Path(p))
    return css, js


def overlay_config_payload(config) -> dict:
    """The window.OVERLAY_CONFIG object the frontend reads. frontend_config
    is merged last so a project can override or extend any key."""
    payload = {
        "pollMs": 500,
        "builtinDashboard": config.builtin_dashboard,
        "agelessStates": list(config.ageless_states),
        "pulseStates": list(config.pulse_states),
        "stateLabels": dict(config.state_labels),
        "defaultTheme": config.default_theme,
        "defaultWidth": config.default_width,
        "sizePresets": list(config.size_presets),
        "defaultEmotion": "idle",
    }
    payload.update(config.frontend_config or {})
    return payload


def _config_script(config) -> str:
    blob = json.dumps(overlay_config_payload(config))
    # Guard against "</script>" appearing inside any string value.
    blob = blob.replace("</", "<\\/")
    return f"<script>window.OVERLAY_CONFIG = {blob};</script>"


def _font_block(config) -> str:
    parts = []
    if config.font_href:
        parts.append(f'<link rel="stylesheet" href="{config.font_href}">')
    if config.font_family:
        fam = config.font_family.replace("</", "<\\/")
        parts.append(f"<style>:root {{ --overlay-font: {fam}; }}</style>")
    return "\n".join(parts)


def _fill_template(config, theme: str, font: str, head_css: str,
                   project_js: str, base_js: str) -> str:
    html = _read_pkg(_TEMPLATE)
    brand = _esc_html(config.brand_text)
    repl = {
        "{{THEME}}": theme,
        "{{BRAND}}": brand,
        "{{BRAND_HIDDEN}}": "" if config.brand_text else "hidden",
        "{{FONT}}": font,
        "{{HEAD_CSS}}": head_css,
        "{{CONFIG_JSON}}": _config_script(config),
        "{{PROJECT_JS}}": project_js,
        "{{BASE_JS}}": base_js,
    }
    for k, v in repl.items():
        html = html.replace(k, v)
    return html


# ── inline mode ───────────────────────────────────────────────────────────
def build_inline_document(config, theme: str) -> str:
    css_paths, js_paths = _split_assets(config.assets)
    head_css = [f"<style>\n{_read_pkg(_BASE_CSS)}\n</style>"]
    for p in css_paths:
        head_css.append(f"<style>\n{p.read_text(encoding='utf-8')}\n</style>")
    project_js = "\n".join(
        f"<script>\n{p.read_text(encoding='utf-8')}\n</script>" for p in js_paths)
    base_js = f"<script>\n{_read_pkg(_BASE_JS)}\n</script>"
    return _fill_template(config, theme, _font_block(config),
                          "\n".join(head_css), project_js, base_js)


# ── http_server mode (v0.2 opt-in) ─────────────────────────────────────────
def stage_assets(config, theme: str) -> Path:
    serve = Path(tempfile.mkdtemp(prefix=f"{config.app_name}-overlay-"))
    (serve / _BASE_CSS).write_text(_read_pkg(_BASE_CSS), encoding="utf-8")
    (serve / _BASE_JS).write_text(_read_pkg(_BASE_JS), encoding="utf-8")

    css_paths, js_paths = _split_assets(config.assets)
    css_links = [f'<link rel="stylesheet" href="{_BASE_CSS}">']
    for p in css_paths:
        (serve / p.name).write_bytes(p.read_bytes())
        css_links.append(f'<link rel="stylesheet" href="{p.name}">')
    project_js = []
    for p in js_paths:
        (serve / p.name).write_bytes(p.read_bytes())
        project_js.append(f'<script src="{p.name}"></script>')

    html = _fill_template(config, theme, _font_block(config),
                          "\n".join(css_links),
                          "\n".join(project_js),
                          f'<script src="{_BASE_JS}"></script>')
    (serve / _TEMPLATE).write_text(html, encoding="utf-8")
    return serve
