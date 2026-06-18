"""Windows-System-Tray-Icon fürs Overlay (opt-in via OverlayConfig.tray_icon).

Reines Lazy-Wiring: pystray + Pillow werden NUR importiert, wenn config.tray_icon
True ist. Fehlt eine Dep → stderr-Hinweis, Overlay läuft normal weiter (ohne
Tray). Cube und andere Consumer ohne Tray-Bedarf zahlen keine Importkosten.

Funktion: Default-Linksklick aufs Icon = show(); Rechtsklick = Menü
(Anzeigen / Ausblenden / Beenden). Hide aus dem Overlay-Kontextmenü versteckt
das Fenster, das Tray-Icon bleibt der einzige Restore-Weg — sonst wäre die
Karte „weg" bis zum nächsten Pulse-Wechsel.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path


def start_tray(config, jsapi) -> threading.Thread | None:
    """Startet einen Daemon-Thread mit dem Tray-Icon. None wenn Deps fehlen
    oder config.tray_icon = False — in beiden Fällen läuft das Overlay normal."""
    if not getattr(config, "tray_icon", False):
        return None
    try:
        import pystray  # type: ignore
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError as e:
        sys.stderr.write(
            f"tray-icon deaktiviert: {e.name or e!r} fehlt — "
            f"`pip install pystray pillow` und neu starten.\n")
        return None

    image = _load_image(config, Image, ImageDraw)
    tooltip = config.tray_tooltip or config.window_title or config.app_name

    def on_show(_icon, _item):
        jsapi.show()

    def on_hide(_icon, _item):
        jsapi.hide()

    def on_quit(icon, _item):
        icon.stop()
        jsapi.quit()

    menu = pystray.Menu(
        pystray.MenuItem("Anzeigen", on_show, default=True),  # Default = Linksklick
        pystray.MenuItem("Ausblenden", on_hide),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Beenden", on_quit),
    )
    icon = pystray.Icon(config.app_name, image, tooltip, menu)

    def run():
        try:
            icon.run()
        except Exception as e:
            sys.stderr.write(f"tray-icon thread crashed: {e!r}\n")

    t = threading.Thread(target=run, name=f"{config.app_name}-tray", daemon=True)
    t.start()
    return t


def _load_image(config, Image, ImageDraw):
    """Pfad laden oder Fallback-Kreis malen. Fehler beim Laden → Fallback (statt
    Crash) — kosmetisches Detail soll nichts blockieren."""
    path = config.tray_icon_path
    if path:
        try:
            return Image.open(path)
        except Exception as e:
            sys.stderr.write(
                f"tray-icon path {path!r} not loadable ({e!r}); using fallback\n")
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((6, 6, 58, 58), fill=config.tray_icon_color)
    return img
