"""Monitor layout detection + anchor bounds checking.

`anchor_in_bounds` is pure math (unit-tested cross-platform). `detect_layout_win`
touches `ctypes.windll` lazily, so this module imports on any OS.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


def detect_layout_win():
    """EnumDisplayMonitors → {fingerprint, primary rect}. The fingerprint keys
    the saved anchor so each distinct monitor arrangement remembers its own
    bottom-right position."""
    user32 = ctypes.windll.user32

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    MONITORINFOF_PRIMARY = 0x00000001
    HMONITOR = getattr(wintypes, "HMONITOR", wintypes.HANDLE)
    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_int, HMONITOR, wintypes.HDC,
        ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
    )
    mons, primary = [], [None]

    def _cb(hmon, _hdc, _rect, _data):  # noqa: ARG001
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return 1
        r = mi.rcMonitor
        x, y = r.left, r.top
        w, h = r.right - r.left, r.bottom - r.top
        is_primary = bool(mi.dwFlags & MONITORINFOF_PRIMARY)
        mons.append((x, y, w, h, is_primary))
        if is_primary:
            primary[0] = (x, y, w, h)
        return 1

    try:
        user32.EnumDisplayMonitors(0, None, MonitorEnumProc(_cb), 0)
    except Exception as e:
        sys.stderr.write(f"detect_layout_win failed: {e}\n")
        return None
    if not mons:
        return None
    if primary[0] is None:
        zero_off = [m for m in mons if m[0] == 0 and m[1] == 0]
        primary[0] = (zero_off[0] if zero_off else sorted(mons)[0])[:4]
    mons_sorted = sorted(mons, key=lambda m: (m[0], m[1]))
    fp = f"mon{len(mons)}:" + ",".join(
        f"{w}x{h}+{x}+{y}" for x, y, w, h, _ in mons_sorted
    )
    return {
        "fingerprint": fp,
        "primary": primary[0],
        "monitors": [(x, y, w, h) for x, y, w, h, _ in mons_sorted],
    }


def detect_layout(sw, sh):
    return detect_layout_win() or {
        "fingerprint": f"fallback:{sw}x{sh}",
        "primary": (0, 0, sw, sh),
        "monitors": [(0, 0, sw, sh)],
    }


def anchor_in_bounds(anchor_r, anchor_b, w, h, primary) -> bool:
    """A saved bottom-right anchor must place the whole window within the
    given monitor rect. Returns False for stale anchors from a previous (larger)
    layout so the caller can fall back to bottom-right of current primary."""
    px, py, pw, ph = primary
    x = anchor_r - w
    y = anchor_b - h
    return (px <= x and x + w <= px + pw
            and py <= y and y + h <= py + ph)


def anchor_on_any_monitor(anchor_r, anchor_b, w, h, monitors) -> bool:
    """A saved anchor is valid if the window fits fully within *any* monitor —
    not just the primary. This is what lets the card stay on a secondary
    monitor across restarts/resizes instead of snapping back to primary."""
    return any(anchor_in_bounds(anchor_r, anchor_b, w, h, m) for m in monitors)


def monitor_containing(monitors, primary, x, y):
    """The monitor rect whose bounds contain point (x, y) — used to clamp a
    resize/move to the monitor the window actually sits on. Falls back to
    `primary` when the point is off every monitor (or none are known)."""
    for m in monitors or ():
        mx, my, mw, mh = m
        if mx <= x < mx + mw and my <= y < my + mh:
            return m
    return primary
