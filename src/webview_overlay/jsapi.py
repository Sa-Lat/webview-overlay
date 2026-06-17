"""JsApi — methods exposed via window.pywebview.api in the WebView.

pywebview marshals these synchronously; JS sees a Promise. urllib + ctypes run
on the bridge thread, not the WebView UI thread, so the UI stays responsive.

Generalized from the cube overlay: env keys, themes, size presets and the
native menu are all driven by OverlayConfig, so any consuming project gets the
same window machinery without forking.
"""
from __future__ import annotations

import sys
import threading

from . import net, win32

# Fixed menu command ids (kept ≥100, clear of common WM_COMMAND territory).
# Theme/size items get dynamic ids derived from these bases.
_THEME_BASE = 100
_SIZE_BASE = 130
_POS_LOCK = 120
_POS_RESET = 121
_WIN_TOPMOST = 140
_WIN_LIFT = 141
_WIN_FRONT = 142
_WIN_ENTITY = 143
_HIDE = 150
_QUIT = 151


class JsApi:
    def __init__(self, config, store, mock_url):
        self.config = config
        self.store = store
        env = store.read_env()

        # network
        self.mock_url = mock_url
        self.port = config.port
        self.consecutive_failures = 0

        # user state from overlay.env (prefixed keys)
        ek = config.env_key
        self.theme = env.get(ek("THEME"), config.default_theme)
        if self.theme not in config.themes:
            self.theme = config.default_theme
        try:
            self.width = int(env.get(ek("WIDTH"), str(config.default_width)))
        except ValueError:
            self.width = config.default_width
        self.locked = env.get(ek("POSITION_LOCKED"), "0") == "1"
        self.topmost = env.get(ek("TOPMOST"), "1" if config.default_topmost else "0") == "1"
        self.lift_on_activity = env.get(ek("LIFT_ON_ACTIVITY"), "1" if config.default_lift else "0") == "1"
        self.hide_entity = env.get(ek("HIDE_ENTITY"), "1" if config.default_hide_entity else "0") == "1"

        self._ageless = set(config.ageless_states)

        # runtime (set after window creation)
        self.hwnd = None
        # MUST stay underscore-prefixed: pywebview's inject_pywebview() recursively
        # walks every non-_ attribute of the JsApi to enumerate exposable methods.
        # A public self.window would drag it into window.native (.NET BrowserForm)
        # → AccessibilityObject.Bounds.Empty.Empty… infinite recursion + COM spam.
        self._window = None
        self.fingerprint = None
        self.primary_rect = (0, 0, 1920, 1080)
        self.anchor_r = None
        self.anchor_b = None

        # hide/show + activity tracking
        self.hidden_by_user = False
        self.hide_winner = None
        self.last_winner = None

        # drag
        self.drag_origin = None
        self._initialised = False

    @property
    def _dashboard_url(self):
        return f"{self.mock_url}{self.config.dashboard_path}"

    # ── data ──────────────────────────────────────────────────────────────
    def _maybe_resolve_drift(self):
        # 3 consecutive misses → re-resolve WSL IP (NAT-mode IPs drift on
        # `wsl --shutdown`).
        if self.consecutive_failures < 3:
            return
        new_ip = net.resolve_wsl_ip(force=True)
        if not new_ip:
            return
        candidate = f"http://{new_ip}:{self.port}"
        if candidate != self.mock_url:
            sys.stderr.write(f"wsl-ip drift: {self.mock_url} -> {candidate}\n")
            self.mock_url = candidate

    def dashboard(self):
        try:
            d = net.fetch_json(self._dashboard_url, timeout=1)
            self.consecutive_failures = 0
        except Exception:
            self.consecutive_failures += 1
            self._maybe_resolve_drift()
            return None
        if not isinstance(d, dict):
            return None  # producer returned a list/scalar/null — nothing to render
        d["theme"] = self.theme
        d["locked"] = self.locked
        d["hide_entity"] = self.hide_entity
        state = d.get("state")
        if self.hidden_by_user and state != self.hide_winner and self._window:
            self.hidden_by_user = False
            self.hide_winner = None
            try:
                self._window.show()
            except Exception as e:
                sys.stderr.write(f"auto-unhide failed: {e}\n")
        if (self._initialised and self.lift_on_activity
                and self.last_winner in self._ageless
                and state and state not in self._ageless):
            self._bring_to_front_async()
        self.last_winner = state
        return d

    def initial_state(self):
        return {
            "theme": self.theme,
            "width": self.width,
            "locked": self.locked,
            "topmost": self.topmost,
            "lift": self.lift_on_activity,
            "hide_entity": self.hide_entity,
            "size_presets": list(self.config.size_presets),
        }

    # ── menu mutators ───────────────────────────────────────────────────
    def set_theme(self, name):
        if name not in self.config.themes:
            return None
        self.theme = name
        self.store.write_env({self.config.env_key("THEME"): name})
        return name

    def set_size(self, w):
        try:
            w = int(w)
        except (TypeError, ValueError):
            return None
        self.width = w
        self.store.write_env({self.config.env_key("WIDTH"): str(w)})
        rect = win32.win32_get_rect(self.hwnd)
        if rect:
            l, t, r, b = rect
            h = b - t
            anchor_r = self.anchor_r if self.anchor_r is not None else r
            anchor_b = self.anchor_b if self.anchor_b is not None else b
            new_x = anchor_r - w
            new_y = anchor_b - h
            px, py, pw, ph = self.primary_rect
            if new_x < px: new_x = px
            if new_x + w > px + pw: new_x = px + pw - w
            if new_y < py: new_y = py
            if new_y + h > py + ph: new_y = py + ph - h
            win32.win32_move(self.hwnd, new_x, new_y, w, h)
        return w

    def set_lock(self, on):
        self.locked = bool(on)
        self.store.write_env({self.config.env_key("POSITION_LOCKED"): "1" if self.locked else "0"})
        return self.locked

    def set_topmost(self, on):
        self.topmost = bool(on)
        self.store.write_env({self.config.env_key("TOPMOST"): "1" if self.topmost else "0"})
        win32.win32_move(self.hwnd, topmost=self.topmost)
        return self.topmost

    def set_lift(self, on):
        self.lift_on_activity = bool(on)
        self.store.write_env({self.config.env_key("LIFT_ON_ACTIVITY"): "1" if self.lift_on_activity else "0"})
        return self.lift_on_activity

    def set_hide_entity(self, on):
        self.hide_entity = bool(on)
        self.store.write_env({self.config.env_key("HIDE_ENTITY"): "1" if self.hide_entity else "0"})
        return self.hide_entity

    # ── window-management ───────────────────────────────────────────────
    def _bring_to_front_async(self):
        if not self.hwnd:
            return
        win32.win32_move(self.hwnd, topmost=True)
        if not self.topmost:
            threading.Timer(0.06, lambda: win32.win32_move(self.hwnd, topmost=False)).start()

    def bring_to_front(self):
        self._bring_to_front_async()

    def hide(self):
        if not self._window:
            return
        try:
            d = net.fetch_json(self._dashboard_url, timeout=1)
            self.hide_winner = d.get("state")
        except Exception:
            self.hide_winner = None
        self.hidden_by_user = True
        try:
            self._window.hide()
        except Exception as e:
            sys.stderr.write(f"hide failed: {e}\n")

    def show(self):
        """Un-hide the window. In shell mode (no dashboard heartbeat) there's no
        auto-unhide, so a consumer can call this from a custom button."""
        if not self._window:
            return
        self.hidden_by_user = False
        self.hide_winner = None
        try:
            self._window.show()
        except Exception as e:
            sys.stderr.write(f"show failed: {e}\n")

    def quit(self):
        if not self._window:
            return
        try:
            self._window.destroy()
        except Exception as e:
            sys.stderr.write(f"quit failed: {e}\n")

    # ── native popup menu ───────────────────────────────────────────────
    def show_menu(self):
        """TrackPopupMenu must run on the thread owning the HWND. JS bridge
        calls land on bridge threads — Invoke onto the WinForms UI thread."""
        if not self._window or not self.hwnd:
            return
        try:
            from System import Action  # pythonnet — provided by pywebview
            self._window.native.BeginInvoke(Action(self._open_native_menu))
        except Exception as e:
            sys.stderr.write(f"show_menu dispatch failed: {e}\n")
            try:
                self._open_native_menu()
            except Exception as e2:
                sys.stderr.write(f"show_menu direct call failed: {e2}\n")

    def _build_menu_model(self):
        """Returns (root_items, dispatch) where dispatch maps cmd_id -> callable.
        Theme + size submenus are derived from config; the entity toggle is
        present only when the project supplies an entity."""
        cfg = self.config
        MF_CHECKED = win32.MF_CHECKED
        dispatch = {}

        theme_items = []
        for i, name in enumerate(cfg.themes):
            cid = _THEME_BASE + i
            ck = MF_CHECKED if self.theme == name else 0
            theme_items.append((ck, cid, name.capitalize(), 0))
            dispatch[cid] = (lambda n: (lambda: self.set_theme(n)))(name)

        size_items = []
        for i, w in enumerate(cfg.size_presets):
            cid = _SIZE_BASE + i
            ck = MF_CHECKED if self.width == w else 0
            size_items.append((ck, cid, f"{w} px", 0))
            dispatch[cid] = (lambda px: (lambda: self.set_size(px)))(w)

        pos_items = [
            (MF_CHECKED if self.locked else 0, _POS_LOCK, "Locked", 0),
            (0, _POS_RESET, "Reset Position", 0),
        ]
        dispatch[_POS_LOCK] = lambda: self.set_lock(not self.locked)
        dispatch[_POS_RESET] = self.reset_position

        win_items = [
            (MF_CHECKED if self.topmost else 0, _WIN_TOPMOST, "Always on Top", 0),
        ]
        dispatch[_WIN_TOPMOST] = lambda: self.set_topmost(not self.topmost)
        # Lift-on-activity + Show-Animation are dashboard-driven (the poll loop is
        # their heartbeat) — hide them in shell mode where there's no poll.
        if cfg.builtin_dashboard:
            win_items.append(
                (MF_CHECKED if self.lift_on_activity else 0, _WIN_LIFT, "Lift on Activity", 0))
            dispatch[_WIN_LIFT] = lambda: self.set_lift(not self.lift_on_activity)
            if cfg.has_entity:
                win_items.append(
                    (MF_CHECKED if not self.hide_entity else 0, _WIN_ENTITY, "Show Animation", 0))
                dispatch[_WIN_ENTITY] = lambda: self.set_hide_entity(not self.hide_entity)
        win_items.append((0, _WIN_FRONT, "Bring to Front", 0))
        dispatch[_WIN_FRONT] = self.bring_to_front

        theme_m = win32.make_popup_menu(theme_items)
        pos_m = win32.make_popup_menu(pos_items)
        size_m = win32.make_popup_menu(size_items)
        win_m = win32.make_popup_menu(win_items)
        root_items = [
            (0, 0, "Theme", theme_m),
            (0, 0, "Position", pos_m),
            (0, 0, "Size", size_m),
            (0, 0, "Window", win_m),
            None,
            (0, _HIDE, "Hide", 0),
            (0, _QUIT, "Quit", 0),
        ]
        dispatch[_HIDE] = self.hide
        dispatch[_QUIT] = self.quit
        return root_items, dispatch

    def _open_native_menu(self):
        root_items, dispatch = self._build_menu_model()
        root_m = win32.make_popup_menu(root_items)
        cmd_id = win32.track_popup_menu(root_m, self.hwnd)
        if cmd_id and cmd_id in dispatch:
            dispatch[cmd_id]()

    def reset_position(self):
        if not self.hwnd:
            return
        px, py, pw, ph = self.primary_rect
        rect = win32.win32_get_rect(self.hwnd)
        h = (rect[3] - rect[1]) if rect else self.config.initial_height
        anchor_r = px + pw - 20
        anchor_b = py + ph - 20
        new_x = anchor_r - self.width
        new_y = anchor_b - h
        win32.win32_move(self.hwnd, new_x, new_y, self.width, h)
        self.anchor_r = anchor_r
        self.anchor_b = anchor_b
        self.store.save_layout_anchor(self.fingerprint, anchor_r, anchor_b)

    def save_anchor(self):
        rect = win32.win32_get_rect(self.hwnd)
        if not rect or not self.fingerprint:
            return
        l, t, r, b = rect
        self.anchor_r = r
        self.anchor_b = b
        self.store.save_layout_anchor(self.fingerprint, r, b)

    # ── drag ────────────────────────────────────────────────────────────
    def start_drag(self):
        if self.locked or not self.hwnd:
            return
        rect = win32.win32_get_rect(self.hwnd)
        cur = win32.cursor_pos()
        if not rect or not cur:
            return
        self.drag_origin = (cur[0], cur[1], rect[0], rect[1])

    def move_relative(self):
        if not self.drag_origin or self.locked or not self.hwnd:
            return
        cur = win32.cursor_pos()
        if not cur:
            return
        orig_cx, orig_cy, orig_x, orig_y = self.drag_origin
        win32.win32_move(self.hwnd, orig_x + cur[0] - orig_cx, orig_y + cur[1] - orig_cy)

    def end_drag(self):
        if not self.drag_origin:
            return
        self.drag_origin = None
        self.save_anchor()

    # ── dynamic height ──────────────────────────────────────────────────
    def resize_height(self, h):
        """JS ResizeObserver reports `.wrap` content height after every DOM
        mutation; resize the OS window to match, keeping the stored bottom-
        right anchor stable (physical px, bounds-checked) so the card grows
        upward and never locks off-screen."""
        if not self.hwnd:
            sys.stderr.write(f"resize_height({h}): no hwnd\n")
            return
        rect = win32.win32_get_rect(self.hwnd)
        if not rect:
            sys.stderr.write(f"resize_height({h}): no rect\n")
            return
        l, t, r, b = rect
        w = r - l
        cur_h = b - t
        try:
            new_h = max(60, int(h))
        except (TypeError, ValueError):
            sys.stderr.write(f"resize_height({h}): bad value\n")
            return
        if new_h == cur_h:
            return
        anchor_b = self.anchor_b if self.anchor_b is not None else b
        anchor_r = self.anchor_r if self.anchor_r is not None else r
        new_y = anchor_b - new_h
        new_x = anchor_r - w
        px, py, pw, ph = self.primary_rect
        if new_y < py: new_y = py
        if new_y + new_h > py + ph: new_y = py + ph - new_h
        if new_x < px: new_x = px
        if new_x + w > px + pw: new_x = px + pw - w
        win32.win32_move(self.hwnd, new_x, new_y, w, new_h)
