"""Shell-mode example — a time-tracking overlay, no /dashboard.json.

Demonstrates the interactive (non-dashboard) use of webview-overlay: the
consumer ships its own JS/CSS that mounts a <select> + Start/Stop buttons into
#overlay-slot, and a custom js_api whose methods are callable from JS. Run on
Windows with pywebview installed:

    py -3.13 examples/timetracker_demo.py

In a real app start_timer/stop_timer would POST to your backend (do it here, in
Python — no CORS, tokens stay server-side). This demo just prints.
"""
from __future__ import annotations

from pathlib import Path

from webview_overlay import OverlayConfig, run

H = Path(__file__).resolve().parent


class TimerApi:
    """Exposed to JS as window.pywebview.api.{start_timer,stop_timer,switch_task}."""

    def start_timer(self, task):
        print(f"[timer] start {task}")
        return {"ok": True}

    def stop_timer(self, task):
        print(f"[timer] stop {task}")
        return {"ok": True}

    def switch_task(self, task):
        print(f"[timer] switch {task}")
        return {"ok": True}


def main():
    run(OverlayConfig(
        app_name="timetracker-demo",
        window_title="timetracker",
        builtin_dashboard=False,        # shell mode: no poll, no data source
        brand_text="track",
        background_colors={"light": "#f4f4f5", "dark": "#18181b"},
        js_api=TimerApi(),
        assets=[str(H / "tt.js"), str(H / "tt.css")],
    ))


if __name__ == "__main__":
    main()
