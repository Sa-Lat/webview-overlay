import pytest

from webview_overlay import OverlayConfig, assets
from webview_overlay.app import _expose_js_api


# ── config validation ──────────────────────────────────────────────────────
@pytest.mark.parametrize("kwargs", [
    {"themes": ()},
    {"size_presets": ()},
    {"default_theme": "nope"},
    {"default_width": 0},
])
def test_config_validation_raises(kwargs):
    with pytest.raises(ValueError):
        OverlayConfig(app_name="x", **kwargs)


def test_builtin_dashboard_default_true():
    assert OverlayConfig(app_name="x").builtin_dashboard is True


# ── payload + document ──────────────────────────────────────────────────────
def test_payload_has_builtin_dashboard_flag():
    on = assets.overlay_config_payload(OverlayConfig(app_name="x"))
    off = assets.overlay_config_payload(OverlayConfig(app_name="x", builtin_dashboard=False))
    assert on["builtinDashboard"] is True
    assert off["builtinDashboard"] is False


def test_shell_mode_document():
    c = OverlayConfig(app_name="tt", brand_text="", builtin_dashboard=False)
    doc = assets.build_inline_document(c, "light")
    assert "{{" not in doc
    assert 'id="overlay-slot"' in doc
    assert '<div class="brand" hidden>' in doc      # empty brand hidden
    assert '"builtinDashboard": false' in doc
    assert "overlay:ready" in doc                    # consumer mount hook present


def test_dashboard_mode_document_keeps_brand_and_poll():
    c = OverlayConfig(app_name="cube", brand_text="cube")
    doc = assets.build_inline_document(c, "light")
    assert "<span>cube</span>" in doc
    assert 'class="brand" hidden' not in doc
    assert '"builtinDashboard": true' in doc


def test_consumer_js_mounts_before_base(tmp_path):
    proj = tmp_path / "tt.js"
    proj.write_text("/* TT_WIDGET_MARKER */", encoding="utf-8")
    c = OverlayConfig(app_name="tt", builtin_dashboard=False, assets=[str(proj)])
    doc = assets.build_inline_document(c, "light")
    assert doc.index("TT_WIDGET_MARKER") < doc.index("generic render loop")


# ── js_api expose ───────────────────────────────────────────────────────────
class _FakeWindow:
    def __init__(self):
        self.exposed = []

    def expose(self, *fns):
        self.exposed.extend(fns)


class _GoodApi:
    def start_timer(self, task):
        return task

    def _private(self):
        pass


class _CollidingApi:
    def dashboard(self):  # shadows a reserved shell method
        pass


def test_expose_registers_public_methods_only():
    w = _FakeWindow()
    _expose_js_api(w, _GoodApi())
    assert [f.__name__ for f in w.exposed] == ["start_timer"]


def test_expose_rejects_reserved_name_collision():
    w = _FakeWindow()
    with pytest.raises(ValueError):
        _expose_js_api(w, _CollidingApi())
