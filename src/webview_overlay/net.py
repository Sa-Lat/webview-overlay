"""Network helpers: WSL-IP resolution + dashboard JSON fetch.

The overlay typically runs on a Windows host and polls a producer inside WSL.
`wsl.exe hostname -I` yields the current WSL IP (which drifts on
`wsl --shutdown`); the result is cached and re-resolved on demand.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

_WSL_IP_CACHE = {"ip": None, "ts": 0.0}


def resolve_wsl_ip(force: bool = False):
    if not force and _WSL_IP_CACHE["ip"]:
        return _WSL_IP_CACHE["ip"]
    try:
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        out = subprocess.run(["wsl.exe", "hostname", "-I"],
                             capture_output=True, text=True, timeout=3,
                             creationflags=flags)
        if out.returncode == 0 and out.stdout.strip():
            ip = out.stdout.strip().split()[0]
            _WSL_IP_CACHE["ip"] = ip
            return ip
    except Exception as e:
        sys.stderr.write(f"resolve_wsl_ip failed: {e}\n")
    return None


def fetch_json(url: str, timeout: float = 1.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())
