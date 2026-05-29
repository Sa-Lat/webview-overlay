"""Standalone real-window smoke test — no WSL, no project producer.

Spins up a tiny HTTP server that returns sample dashboard data, then launches
the overlay against it. Run on Windows with pywebview installed:

    py -3.13 examples/demo.py

Pass --instance to launch a second, independent window (separate position
memory + crash log) to verify multi-instance isolation.
"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from webview_overlay import OverlayConfig, run

PORT = 8799

SAMPLE = {
    "state": "thinking",
    "cwd": "demo",
    "ts": 0,
    "usage_5h_pct": 42,
    "sessions": [
        {"state": "permission", "cwd": "navigatoren", "age_s": 12,
         "session_id": "a", "label": "Fix the auth middleware bug"},
        {"state": "thinking", "cwd": "demo", "age_s": 184,
         "session_id": "b", "label": "Extract overlay package"},
        {"state": "idle", "cwd": "backend-api", "age_s": 0,
         "session_id": "c", "label": "Investigate slow endpoint"},
    ],
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/dashboard.json":
            self.send_error(404)
            return
        body = json.dumps(SAMPLE).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def serve(port):
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", default=None, help="instance id for a second window")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()

    threading.Thread(target=serve, args=(args.port,), daemon=True).start()

    run(OverlayConfig(
        app_name="overlay-demo",
        instance_id=args.instance,
        window_title="overlay-demo",
        host="127.0.0.1",
        port=args.port,
        brand_text="demo",
        ageless_states=("idle", "done", "start"),
        pulse_states=("permission", "error", "compact", "alert", "thinking"),
        state_labels={"idle": "idle", "done": "done", "start": "start"},
        background_colors={"light": "#e6eef2", "dark": "#0d1015"},
        frontend_config={"usageThresholds": [[80, "#e85555"], [50, "#d7a04a"]]},
    ))


if __name__ == "__main__":
    main()
