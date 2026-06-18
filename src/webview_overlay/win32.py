"""Low-level Win32 helpers (ctypes). All window management routes through
SetWindowPos in physical pixels, bypassing EdgeChromium's logical-pixel
confusion under per-monitor DPI awareness.

`ctypes.windll` only exists on Windows and is touched lazily inside each
function, so this module imports cleanly on any OS (the unit tests rely on
that). `ctypes.wintypes` is import-safe everywhere.
"""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

# SetWindowPos flags / z-order
SWP_NOACTIVATE = 0x0010
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
HWND_TOP = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2

# Menu flags
MF_STRING = 0x0000
MF_POPUP = 0x0010
MF_SEPARATOR = 0x0800
MF_CHECKED = 0x0008
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002


def set_dpi_awareness() -> None:
    """Per-monitor DPI awareness so WebView2 renders crisp on >100% scaling."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def win32_move(hwnd, x=None, y=None, w=None, h=None, topmost=None) -> bool:
    """SetWindowPos in physical pixels. Skipping x/y or w/h sets the matching
    SWP_NO* flag so partial moves don't stomp the other axis."""
    if not hwnd:
        return False
    flags = SWP_NOACTIVATE
    if x is None or y is None:
        flags |= SWP_NOMOVE
        x = y = 0
    if w is None or h is None:
        flags |= SWP_NOSIZE
        w = h = 0
    if topmost is True:
        z = HWND_TOPMOST
    elif topmost is False:
        z = HWND_NOTOPMOST
    else:
        z = HWND_TOP
    return bool(ctypes.windll.user32.SetWindowPos(
        hwnd, z, int(x), int(y), int(w), int(h), flags))


def win32_get_rect(hwnd):
    if not hwnd:
        return None
    r = wintypes.RECT()
    if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return (r.left, r.top, r.right, r.bottom)
    return None


def get_dpi_for_window(hwnd) -> int:
    """Per-monitor DPI for the window. WebView2 / getBoundingClientRect report
    CSS (logical) pixels; SetWindowPos works in physical pixels. Callers convert
    via `physical = logical * dpi / 96`. Falls back to 96 (= 100% scaling) on any
    error so the math is a no-op."""
    if not hwnd:
        return 96
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
        if dpi:
            return int(dpi)
    except (AttributeError, OSError):
        pass
    try:
        hdc = ctypes.windll.user32.GetDC(hwnd)
        if hdc:
            LOGPIXELSX = 88
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX)
            ctypes.windll.user32.ReleaseDC(hwnd, hdc)
            if dpi:
                return int(dpi)
    except (AttributeError, OSError):
        pass
    return 96


def cursor_pos():
    p = wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(p)):
        return None
    return (p.x, p.y)


def _enum_pid_windows():
    user32 = ctypes.windll.user32
    pid = os.getpid()
    out = []

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

    @WNDENUMPROC
    def cb(hwnd, _):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value != pid:
            return 1
        if not user32.IsWindowVisible(hwnd):
            return 1
        title = ctypes.create_unicode_buffer(256)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        user32.GetClassNameW(hwnd, cls, 256)
        out.append((hwnd, title.value, cls.value))
        return 1

    user32.EnumWindows(cb, 0)
    return out


def find_hwnd(window, window_title):
    """pywebview's native form Handle first; on any failure, enumerate visible
    windows in our PID and prefer a title match (per-instance-unique title),
    falling back to the first visible window."""
    try:
        # pythonnet wraps Win32 HANDLE as System.IntPtr — ToInt64() unwraps it.
        h = int(window.native.Handle.ToInt64())
        if h:
            sys.stderr.write(f"hwnd via window.native.Handle: {h:#x}\n")
            return h
    except Exception as e:
        sys.stderr.write(f"window.native.Handle failed: {e}\n")
    candidates = _enum_pid_windows()
    sys.stderr.write(f"PID windows: {candidates}\n")
    for hwnd, title, _cls in candidates:
        if title == window_title:
            sys.stderr.write(f"hwnd via enum (title match): {hwnd:#x}\n")
            return hwnd
    if candidates:
        hwnd = candidates[0][0]
        sys.stderr.write(f"hwnd via enum (first visible): {hwnd:#x}\n")
        return hwnd
    sys.stderr.write("hwnd discovery: no candidates\n")
    return 0


def make_popup_menu(items):
    """items = list of (flags, item_id, text, submenu_handle). submenu_handle
    != 0 → popup (text is the label); else leaf. None entry = separator."""
    user32 = ctypes.windll.user32
    h = user32.CreatePopupMenu()
    for item in items:
        if item is None:
            user32.AppendMenuW(h, MF_SEPARATOR, 0, None)
            continue
        flags, item_id, text, sub = item
        if sub:
            user32.AppendMenuW(h, MF_POPUP | flags, sub, text)
        else:
            user32.AppendMenuW(h, MF_STRING | flags, item_id, text)
    return h


def track_popup_menu(root_menu, hwnd):
    """Show the popup at the cursor and return the chosen command id (0 if
    dismissed). Caller owns DestroyMenu."""
    user32 = ctypes.windll.user32
    cur = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(cur))
    # Without SetForegroundWindow the popup may not dismiss on outside-click.
    user32.SetForegroundWindow(hwnd)
    cmd_id = user32.TrackPopupMenu(
        root_menu, TPM_RETURNCMD | TPM_RIGHTBUTTON,
        cur.x, cur.y, 0, hwnd, None)
    user32.DestroyMenu(root_menu)
    return cmd_id
