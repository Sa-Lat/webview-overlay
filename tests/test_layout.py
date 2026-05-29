from webview_overlay.layout import anchor_in_bounds

PRIMARY = (0, 0, 1920, 1080)


def test_anchor_within_bounds():
    # bottom-right anchor 20px from the edges, 180x420 window → fits
    assert anchor_in_bounds(1900, 1060, 180, 420, PRIMARY) is True


def test_anchor_off_screen_left():
    # anchor_r smaller than width pushes x negative
    assert anchor_in_bounds(100, 1060, 180, 420, PRIMARY) is False


def test_anchor_off_screen_bottom():
    # anchor_b beyond monitor height
    assert anchor_in_bounds(1900, 2000, 180, 420, PRIMARY) is False


def test_anchor_secondary_monitor_offset():
    secondary = (1920, 0, 1920, 1080)
    assert anchor_in_bounds(3820, 1060, 180, 420, secondary) is True
    assert anchor_in_bounds(1900, 1060, 180, 420, secondary) is False
