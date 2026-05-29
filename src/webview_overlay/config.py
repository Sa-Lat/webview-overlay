"""OverlayConfig — the single object a consuming project hands to run().

Pure data + a couple of derived helpers. No heavy / platform imports here so
this module (and the unit tests that exercise it) import on any OS.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def _default_themes() -> tuple[str, ...]:
    return ("light", "dark")


def _default_size_presets() -> tuple[int, ...]:
    return (140, 180, 240)


def _default_background_colors() -> dict[str, str]:
    return {"light": "#ffffff", "dark": "#101418"}


@dataclass
class OverlayConfig:
    # ── identity / persistence ────────────────────────────────────────────
    app_name: str                              # -> %APPDATA%\<app_name>\
    instance_id: str | None = None             # multi-instance identity; None => "default"
    window_title: str = "overlay"              # base title; made unique per instance at runtime
    env_prefix: str = "OVERLAY_"               # overlay.env key namespace

    # ── data source (the /dashboard.json producer) ───────────────────────
    # Built-in dashboard layer: poll /dashboard.json + render rows/usage/entity.
    # False => shell-only (no poll, no data source required); the consumer drives
    # the UI via its own assets + js_api. See README "Shell mode".
    builtin_dashboard: bool = True

    dashboard_path: str = "/dashboard.json"
    host: str | None = None                    # None => resolve WSL IP (dashboard mode)
    port: int = 8765
    url: str | None = None                     # full override; wins over host/port

    # ── window defaults (overridable per-machine via overlay.env) ─────────
    default_theme: str = "light"
    themes: tuple[str, ...] = field(default_factory=_default_themes)
    default_width: int = 180
    size_presets: tuple[int, ...] = field(default_factory=_default_size_presets)
    default_topmost: bool = True
    default_lift: bool = False
    default_hide_entity: bool = False
    initial_height: int = 420

    # ── frontend injection ────────────────────────────────────────────────
    brand_text: str = ""
    assets: list[str] = field(default_factory=list)       # extra css/js, ordered; may be UNC
    frontend_config: dict = field(default_factory=dict)   # merged into window.OVERLAY_CONFIG

    # Optional consumer bridge object. Its public methods are exposed to JS as
    # window.pywebview.api.<name>() (via window.expose). Method names must not
    # collide with the shell JsApi's own methods (see app.py reserved set).
    js_api: object | None = None

    # Python paints the window background BEFORE CSS loads (frameless window
    # would otherwise flash white). The package can't read CSS vars, so the
    # consumer supplies a hex per theme.
    background_colors: dict[str, str] = field(default_factory=_default_background_colors)

    # Font is a brand choice, not generic. None => base reset's system stack.
    font_href: str | None = None
    font_family: str | None = None

    # ── state semantics (consumed by overlay-base.js) ────────────────────
    ageless_states: tuple[str, ...] = ()       # show a label instead of an age
    pulse_states: tuple[str, ...] = ()         # render the live ripple on the dot
    state_labels: dict[str, str] = field(default_factory=dict)

    # ── asset delivery ────────────────────────────────────────────────────
    use_http_server: bool = False              # inline html= default; True = pywebview http_server (v0.2)

    def __post_init__(self):
        if not self.themes:
            raise ValueError("OverlayConfig.themes must be non-empty")
        if not self.size_presets:
            raise ValueError("OverlayConfig.size_presets must be non-empty")
        if self.default_theme not in self.themes:
            raise ValueError(
                f"default_theme {self.default_theme!r} not in themes {self.themes}")
        if self.default_width <= 0:
            raise ValueError("OverlayConfig.default_width must be > 0")

    # ── derived helpers ───────────────────────────────────────────────────
    @property
    def instance(self) -> str:
        return self.instance_id or "default"

    def env_key(self, name: str) -> str:
        return f"{self.env_prefix}{name}"

    @property
    def has_entity(self) -> bool:
        return bool(self.frontend_config.get("entityGlobal"))

    def background_for(self, theme: str) -> str:
        return self.background_colors.get(theme) or self.background_colors.get("light", "#ffffff")
