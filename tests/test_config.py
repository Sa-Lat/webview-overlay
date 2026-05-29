from webview_overlay import OverlayConfig


def test_defaults():
    c = OverlayConfig(app_name="x")
    assert c.instance == "default"
    assert c.port == 8765
    assert c.use_http_server is False  # inline is the proven default
    assert c.themes == ("light", "dark")
    assert c.size_presets == (140, 180, 240)
    assert c.has_entity is False


def test_instance_and_env_key():
    c = OverlayConfig(app_name="cube", instance_id="mon2", env_prefix="CUBE_OVERLAY_")
    assert c.instance == "mon2"
    assert c.env_key("THEME") == "CUBE_OVERLAY_THEME"


def test_has_entity_and_background():
    c = OverlayConfig(
        app_name="cube",
        frontend_config={"entityGlobal": "CubeEntity"},
        background_colors={"light": "#fff", "dark": "#000"},
    )
    assert c.has_entity is True
    assert c.background_for("dark") == "#000"
    assert c.background_for("unknown") == "#fff"  # falls back to light
