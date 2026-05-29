"""webview-overlay — a generic frameless WebView2 dashboard overlay.

Public API:
    from webview_overlay import OverlayConfig, run
    run(OverlayConfig(app_name="myapp", port=8765, brand_text="myapp"))

The overlay renders session rows + an optional usage bar + an optional
project-supplied entity canvas, polling any HTTP endpoint that serves the
documented `/dashboard.json` contract. See README for the contract and the
frontend plugin hooks (window.OVERLAY_CONFIG).
"""
from .config import OverlayConfig

__version__ = "0.2.0"
__all__ = ["OverlayConfig", "run", "__version__"]


def run(config: "OverlayConfig") -> None:
    """Launch the overlay window (blocking). Imported lazily so the package
    imports cleanly on non-Windows hosts without pywebview installed."""
    from .app import run as _run
    _run(config)
