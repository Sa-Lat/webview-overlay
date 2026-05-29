import json

from webview_overlay import OverlayConfig, assets


def _extract_overlay_config(doc: str) -> dict:
    marker = "window.OVERLAY_CONFIG = "
    start = doc.index(marker) + len(marker)
    end = doc.index(";</script>", start)
    blob = doc[start:end].replace("<\\/", "</")
    return json.loads(blob)


def test_payload_merges_frontend_config():
    c = OverlayConfig(
        app_name="cube",
        ageless_states=("idle", "done"),
        pulse_states=("thinking",),
        frontend_config={"entityGlobal": "CubeEntity", "pollMs": 250},
    )
    p = assets.overlay_config_payload(c)
    assert p["agelessStates"] == ["idle", "done"]
    assert p["pulseStates"] == ["thinking"]
    assert p["entityGlobal"] == "CubeEntity"
    assert p["pollMs"] == 250  # frontend_config overrides the default 500


def test_inline_document_substitutions():
    c = OverlayConfig(app_name="cube", brand_text="cube",
                      background_colors={"light": "#fbe9f1"})
    doc = assets.build_inline_document(c, "light")
    assert "{{" not in doc                       # all placeholders filled
    assert doc.count('data-theme="light"') == 2  # <html> + #root
    assert "<span>cube</span>" in doc
    assert "webview-overlay — base structure" in doc  # base.css inlined
    assert "generic render loop" in doc               # overlay-base.js inlined
    cfg = _extract_overlay_config(doc)               # valid JSON
    assert cfg["defaultTheme"] == "light"


def test_project_js_before_base_js(tmp_path):
    proj = tmp_path / "entity.js"
    proj.write_text("/* PROJECT_ENTITY_MARKER */", encoding="utf-8")
    c = OverlayConfig(app_name="cube", assets=[str(proj)])
    doc = assets.build_inline_document(c, "dark")
    assert "PROJECT_ENTITY_MARKER" in doc
    # project asset must load before the base loop reads window[entityGlobal]
    assert doc.index("PROJECT_ENTITY_MARKER") < doc.index("generic render loop")


def test_brand_is_html_escaped():
    c = OverlayConfig(app_name="x", brand_text="<script>x</script>")
    doc = assets.build_inline_document(c, "light")
    assert "<script>x</script>" not in doc.split("window.OVERLAY_CONFIG")[0]
    assert "&lt;script&gt;" in doc
