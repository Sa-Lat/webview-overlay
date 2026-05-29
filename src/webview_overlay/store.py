"""Per-machine persistence: overlay.env (user prefs) + overlay-layouts.json
(per-monitor bottom-right anchor), under %APPDATA%\\<app_name>\\.

Keyed by (app_name, instance_id) so concurrent instances don't clobber each
other. The default instance keeps the unsuffixed filenames for back-compat;
non-default instances get an `.<instance>` suffix. All writes are atomic
(temp + os.replace).
"""
from __future__ import annotations

import json
import os


class Store:
    def __init__(self, config):
        self.config = config
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        self.config_dir = os.path.join(appdata, config.app_name)
        inst = config.instance
        suffix = "" if inst == "default" else f".{inst}"
        self.env_path = os.path.join(self.config_dir, f"overlay{suffix}.env")
        self.layouts_path = os.path.join(self.config_dir, f"overlay-layouts{suffix}.json")

    # ── overlay.env ───────────────────────────────────────────────────────
    def read_env(self) -> dict:
        d = {}
        try:
            with open(self.env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    d[k.strip()] = v.strip()
        except OSError:
            pass
        return d

    def write_env(self, updates: dict) -> None:
        cur = self.read_env()
        for k, v in updates.items():
            if v is None:
                cur.pop(k, None)
            else:
                cur[k] = str(v)
        os.makedirs(self.config_dir, exist_ok=True)
        tmp = self.env_path + ".tmp"
        with open(tmp, "w") as f:
            for k, v in cur.items():
                f.write(f"{k}={v}\n")
        os.replace(tmp, self.env_path)

    # ── overlay-layouts.json ──────────────────────────────────────────────
    def load_layouts(self) -> dict:
        try:
            with open(self.layouts_path) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_layout_anchor(self, fp, anchor_r, anchor_b) -> None:
        layouts = self.load_layouts()
        layouts[fp] = {"anchor_r": int(anchor_r), "anchor_b": int(anchor_b)}
        os.makedirs(self.config_dir, exist_ok=True)
        tmp = self.layouts_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(layouts, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, self.layouts_path)
