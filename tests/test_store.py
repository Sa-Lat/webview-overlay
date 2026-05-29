import os

from webview_overlay import OverlayConfig
from webview_overlay.store import Store


def test_env_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    c = OverlayConfig(app_name="cube", env_prefix="CUBE_OVERLAY_")
    st = Store(c)
    assert st.read_env() == {}
    st.write_env({"CUBE_OVERLAY_THEME": "dark", "CUBE_OVERLAY_WIDTH": "240"})
    assert st.read_env() == {"CUBE_OVERLAY_THEME": "dark", "CUBE_OVERLAY_WIDTH": "240"}
    # None removes a key
    st.write_env({"CUBE_OVERLAY_WIDTH": None})
    assert st.read_env() == {"CUBE_OVERLAY_THEME": "dark"}


def test_default_vs_instance_filenames(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    default = Store(OverlayConfig(app_name="cube"))
    inst = Store(OverlayConfig(app_name="cube", instance_id="mon2"))
    assert os.path.basename(default.env_path) == "overlay.env"
    assert os.path.basename(default.layouts_path) == "overlay-layouts.json"
    assert os.path.basename(inst.env_path) == "overlay.mon2.env"
    assert os.path.basename(inst.layouts_path) == "overlay-layouts.mon2.json"


def test_layout_anchor_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    st = Store(OverlayConfig(app_name="cube"))
    st.save_layout_anchor("mon1:1920x1080+0+0", 1900, 1060)
    assert st.load_layouts()["mon1:1920x1080+0+0"] == {"anchor_r": 1900, "anchor_b": 1060}


def test_concurrent_instances_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    a = Store(OverlayConfig(app_name="cube"))
    b = Store(OverlayConfig(app_name="cube", instance_id="mon2"))
    a.write_env({"K": "a"})
    b.write_env({"K": "b"})
    assert a.read_env()["K"] == "a"  # no clobber
    assert b.read_env()["K"] == "b"
